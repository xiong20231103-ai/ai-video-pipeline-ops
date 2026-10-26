// Every request is fulfilled from local files/fixtures or aborted. No real HTTP.
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path')
const { chromium } = require(process.env.OPS_UI_PLAYWRIGHT || 'playwright')
const fixture = require('../src/test/fixture.json')
const root = path.resolve(__dirname, '../../static/v2'), evidence = process.env.V2_EVIDENCE_DIR
if (evidence) fs.mkdirSync(evidence, { recursive: true })
const csp = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'"
const requests = [], errors = [], violations = [], screenshots = []
async function run() {
  const browser = await chromium.launch({ executablePath: process.env.OPS_UI_BROWSER_PATH, headless: true })
  try {
    for (const mode of ['home', 'cloud']) for (const [width, height] of [[1920, 1080], [1440, 900], [1366, 768], [375, 812]]) {
      // Exercise the actual home-host mode decision. ALL requests are fulfilled;
      // route.continue() is never used, including for static assets.
      const origin = mode === 'home' ? 'http://100.92.17.9:8765' : 'https://cloud-fixture.invalid'
      const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 })
      let sourceAge = 7
      await context.route('**/*', async route => {
        const request = route.request(), url = new URL(request.url())
        requests.push({ mode, method: request.method(), path: url.pathname, intercepted: true })
        assert.equal(url.origin, origin); assert.equal(request.method(), 'GET', 'V2-1 must never write')
        if (url.pathname.startsWith('/static/v2/')) {
          const file = path.resolve(root, decodeURIComponent(url.pathname.slice('/static/v2/'.length)))
          assert(file.startsWith(root + path.sep)); assert(fs.statSync(file).isFile())
          return route.fulfill({ status: 200, headers: { 'Content-Security-Policy': csp }, contentType: { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' }[path.extname(file)] || 'text/plain', body: fs.readFileSync(file) })
        }
        const key = url.pathname
        const body = key === '/auth/options' ? { registrationOpen: false } : key === '/auth/session' ? { username: '隔离账号', csrf: 'synthetic-fixture-only' } : key === '/console/status' ? fixture.status : key === '/console/commands' ? fixture.commands : key === '/console/backups' ? fixture.backups : key === '/api/controls/pending-delete' ? fixture.pendingDelete : key === '/api/safety' ? fixture.safety : key.startsWith('/api/dashboard') ? fixture.dashboard : key === '/api/control-commands/current' ? fixture.dashboard.controls.continue : key === '/api/health' ? { ok: true } : null
        assert(body, `Unmodeled request: ${key}`)
        return route.fulfill({ json: body, headers: mode === 'cloud' ? { 'X-Cache-Age-Seconds': '2', 'X-Source-Scanned-At': '2026-10-19T12:00:00+08:00', 'X-Source-Health': JSON.stringify({ scanAgeSeconds: sourceAge }), 'X-Cache-Version': '1', ETag: 'fixture-etag' } : {} })
      })
      const page = await context.newPage()
      page.on('pageerror', error => errors.push(error.message))
      page.on('console', entry => { if (entry.type() === 'error') errors.push(entry.text()) })
      await page.exposeFunction('recordCspViolation', value => violations.push(value))
      await page.addInitScript(() => document.addEventListener('securitypolicyviolation', event => window.recordCspViolation({ directive: event.violatedDirective, blocked: event.blockedURI })))
      await page.goto(origin + '/static/v2/index.html', { waitUntil: 'networkidle' })
      await page.locator('[data-legacy="heroTitle"]').waitFor()
      for (const theme of ['dark', 'light']) {
        if (theme === 'light') await page.getByRole('button', { name: '切换到浅色主题' }).click()
        await page.mouse.move(0, 0)
        const measured = await page.evaluate(() => ({ theme: document.documentElement.dataset.theme, overflow: document.documentElement.scrollWidth > window.innerWidth, inlineScripts: document.querySelectorAll('script:not([src])').length }))
        assert.equal(measured.overflow, false, `${mode}/${theme}/${width} overflow`); assert.equal(measured.inlineScripts, 0)
        const name = `${mode}-${theme}-${width}x${height}.png`
        if (evidence) await page.screenshot({ path: path.join(evidence, name), animations: 'disabled' })
        screenshots.push({ name, ...measured })
      }
      for (const view of ['tasks', 'uploads', 'files', 'commands', 'health']) {
        await page.goto(origin + '/static/v2/index.html#' + view, { waitUntil: 'networkidle' })
        await page.locator('.data-panel').first().waitFor()
        assert.equal(await page.locator('[data-v2-write]:not(:disabled)').count(), 0)
        if (mode === 'cloud' && view === 'health') {
          await page.getByRole('button', { name: '刷新列表', exact: true }).click()
          await page.getByText('查看备份状态与已完成备份包').click()
          await page.getByText('家里备份：最近一次已上传。云端已登记公钥。', { exact: true }).waitFor()
        }
        if (width === 1440 && evidence) await page.screenshot({ path: path.join(evidence, `${mode}-light-${view}-1440.png`), animations: 'disabled' })
      }
      if (mode === 'cloud' && width === 1440) for (const [age, name] of [[200, 'warning'], [650, 'stale']]) {
        sourceAge = age
        await page.reload({ waitUntil: 'networkidle' })
        await page.getByText('页面数据可能已过期，按 Ctrl+F5 刷新', { exact: true }).waitFor()
        if (evidence) await page.screenshot({ path: path.join(evidence, `cloud-freshness-${name}.png`), animations: 'disabled' })
      }
      await context.close()
    }
    assert.deepEqual(errors, []); assert.deepEqual(violations, [])
    const result = { verified: true, productionAccess: false, allRequestsIntercepted: true, csp, screenshots, requests, errors, violations }
    if (evidence) fs.writeFileSync(path.join(evidence, 'browser-result.json'), JSON.stringify(result, null, 2))
    console.log(JSON.stringify({ verified: true, productionAccess: false, interceptedGETs: requests.length, screenshots: screenshots.length, errors, violations }))
  } finally { await browser.close() }
}
run().catch(error => { console.error(error); process.exitCode = 1 })
