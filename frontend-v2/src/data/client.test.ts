import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReadClient } from './client'
import {
  captureReceipt,
  localReceipts,
  mergeReceipts,
  receiptKey,
} from './receipts'

const json = (body: unknown, init?: ResponseInit) =>
  new Response(JSON.stringify(body), {
    status: 200,
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
afterEach(() => vi.useRealTimers())
describe('dual-mode read transport', () => {
  it('positively identifies cloud and never falls back on an unavailable probe', async () => {
    expect(
      await new ReadClient(
        vi.fn().mockResolvedValue(json({ registrationOpen: false })),
      ).detect(),
    ).toBe('cloud')
    const unavailable = new ReadClient(
      vi.fn().mockResolvedValue(json({}, { status: 503 })),
    )
    await expect(unavailable.detect()).rejects.toThrow('无法确认运行模式')
    expect(unavailable.mode).toBeNull()
    expect(
      await new ReadClient(
        vi.fn().mockResolvedValue(json({}, { status: 404 })),
      ).detect(),
    ).toBe('home')
  })
  it('coalesces pending envelopes and never delivers 202 as business data', async () => {
    const network = vi
      .fn()
      .mockResolvedValueOnce(json({ queued: true }, { status: 202 }))
      .mockResolvedValueOnce(json({ queued: true }, { status: 202 }))
      .mockResolvedValueOnce(json({ selectedDate: '10.19' }))
    const client = new ReadClient(network)
    client.mode = 'cloud'
    vi.spyOn(client, 'wait').mockResolvedValue()
    const first = client.read('/api/dashboard'),
      second = client.read('/api/dashboard')
    expect(first).toBe(second)
    expect(await first).toEqual({ selectedDate: '10.19' })
    expect(network).toHaveBeenCalledTimes(3)
    for (const [, init] of network.mock.calls) {
      expect(init.method).toBeUndefined()
      expect(init.headers.get('X-Ops-Page-Visible')).toBe('true')
    }
    client.stop()
  })
  it('uses ETag/304 without losing cloud source-age metadata', async () => {
    const network = vi
      .fn()
      .mockResolvedValueOnce(
        json(
          { items: [] },
          {
            headers: {
              ETag: 'tag1',
              'X-Cache-Age-Seconds': '2',
              'X-Source-Health': '{"scanAgeSeconds":7}',
            },
          },
        ),
      )
      .mockResolvedValueOnce(
        new Response(null, {
          status: 304,
          headers: {
            ETag: 'tag1',
            'X-Cache-Age-Seconds': '1',
            'X-Source-Health': '{"scanAgeSeconds":3}',
          },
        }),
      )
    const client = new ReadClient(network)
    client.mode = 'cloud'
    const first = await client.read('/api/dashboard')
    expect(await client.read('/api/dashboard')).toBe(first)
    expect(network.mock.calls[1][1].headers.get('If-None-Match')).toBe('tag1')
    expect(client.samples.get('/api/dashboard')).toMatchObject({
      age: 1,
      sourceAge: 3,
    })
    client.stop()
  })
  it('redirects expired cloud sessions and keeps untrusted destinations out', async () => {
    const redirect = vi.fn(),
      network = vi.fn().mockResolvedValue(json({}, { status: 401 }))
    const client = new ReadClient(network, redirect)
    client.mode = 'cloud'
    await expect(client.read('/api/dashboard', 0)).rejects.toThrow('请重新登录')
    expect(redirect).toHaveBeenCalledOnce()
    await expect(
      client.request('https://100.92.17.9:8765/api/dashboard'),
    ).rejects.toThrow('同源')
    await expect(client.request('//100.92.17.9/api/dashboard')).rejects.toThrow(
      '同源',
    )
    expect(network).toHaveBeenCalledOnce()
  })
  it('times out an individual HTTP request and aborts in-flight work on unmount', async () => {
    vi.useFakeTimers()
    const network = vi.fn(
      (_url: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) =>
          init!.signal!.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          ),
        ),
    )
    const client = new ReadClient(network)
    const request = client.read('/api/dashboard', 0, 8000)
    const checked = expect(request).rejects.toThrow('Aborted')
    await vi.advanceTimersByTimeAsync(8000)
    await checked
    const second = client.read('/api/safety', 0),
      cancelled = expect(second).rejects.toThrow('Aborted')
    client.stop()
    await cancelled
    expect(network).toHaveBeenCalledTimes(2)
  })
  it('keeps malformed source age unknown rather than showing cached data as live', async () => {
    const client = new ReadClient(
      vi
        .fn()
        .mockResolvedValue(
          json(
            {},
            {
              headers: {
                'X-Cache-Age-Seconds': '1',
                'X-Source-Health': 'broken',
              },
            },
          ),
        ),
    )
    client.mode = 'cloud'
    await client.read('/api/dashboard')
    expect(client.samples.get('/api/dashboard')?.sourceAge).toBeNull()
  })
})
describe('read-only persisted receipt compatibility', () => {
  it('retains pending local identities across reload and deduplicates server records', () => {
    localStorage.setItem(
      receiptKey,
      JSON.stringify([
        {
          requestId: 'request',
          fingerprint: 'fingerprint',
          path: '/api/control-commands',
          state: 'submitting',
        },
        null,
        { secret: 'invalid fixture' },
      ]),
    )
    expect(localReceipts()).toHaveLength(1)
    const updated = captureReceipt(localReceipts()[0], {
      state: 'completed',
      cloudCommandId: 'cloud',
      result: {
        kind: 'http',
        bodyBase64: btoa('{"commandId":"original-home-command"}'),
      },
    })
    expect(updated.homeCommandId).toBe('original-home-command')
    expect(
      mergeReceipts(
        [updated],
        [
          { cloudCommandId: 'cloud' },
          {
            cloudCommandId: 'another',
            target: '/api/batches/validate',
            state: 'completed',
          },
        ],
      ),
    ).toHaveLength(2)
  })
})
