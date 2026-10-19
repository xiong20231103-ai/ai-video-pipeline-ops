import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  cleanup,
  waitFor,
} from "@testing-library/react";
import {
  SafeContinue,
  continuePhases,
  expectedContinueTarget,
  safeContinueFor,
} from "@/data/safe-continue";
import { ReadClient } from "@/data/client";
import { UploadWriter } from "@/data/upload-writer";
import { CommandAdmin } from "@/data/command-admin";
import { localReceipts, saveReceipts } from "@/data/receipts";
import ContinueActions from "@/components/views/ContinueActions";
import type { Row, Snapshot } from "@/data/types";
const ready = { canContinue: true, executorAvailable: true, homeReady: true };
const base: Row = {
  controls: { continue: { state: "idle", allowed: true } },
  currentTaskBox: {
    batchId: "batch",
    current: { taskId: "task", attemptId: "attempt" },
  },
  services: [],
};
const json = (v: unknown, status = 200) =>
  new Response(JSON.stringify(v), {
    status,
    headers: { "Content-Type": "application/json" },
  });
function setup(
  mode: "home" | "cloud" = "cloud",
  network = vi
    .fn()
    .mockResolvedValue(json({ commandId: "home-command", state: "persisted" })),
) {
  let clock = 0;
  const reader = new ReadClient(network);
  reader.mode = mode;
  vi.spyOn(reader, "wait").mockResolvedValue();
  const controller = new SafeContinue(reader, () => clock);
  controller.observe({ state: "idle", allowed: true }, ready);
  return { reader, controller, network, tick: (n: number) => (clock = n) };
}
const receipt = (state = "completed"): Row => ({
  path: "/api/control-commands",
  requestId: "request-original",
  fingerprint: "fingerprint",
  state,
  cloudCommandId: "cloud-original",
  homeCommandId: "home-original",
});
beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});
describe("continue gates match home and cloud contracts", () => {
  it("expectedTarget keeps only nonempty string batch/task/attempt fields", () => {
    expect(expectedContinueTarget(base)).toEqual({
      batchId: "batch",
      taskId: "task",
      attemptId: "attempt",
    });
    expect(
      expectedContinueTarget({
        currentTaskBox: { batchId: 1, current: { taskId: "", attemptId: "a" } },
      }),
    ).toEqual({ attemptId: "a" });
    expect(expectedContinueTarget({})).toEqual({});
  });
  for (const mode of ["home", "cloud"] as const) {
    for (const state of continuePhases)
      it(mode + " locks " + state, () => {
        const f = setup(mode),
          result = { state, allowed: true };
        f.controller.observe(result, ready);
        expect(
          f.controller.state({ ...base, controls: { continue: result } }, ready)
            .clickable,
        ).toBe(false);
      });
    it(
      mode + " locks working runtime but does not invent offline runtime busy",
      () => {
        const f = setup(mode);
        const working = {
          ...base,
          services: [
            { key: "workbench", online: true },
            { key: "capcut", online: true },
          ],
        };
        expect(f.controller.state(working, ready)).toMatchObject({
          clickable: false,
          label: "流水线正在运行，无需点击",
        });
        expect(
          f.controller.state(
            {
              ...base,
              services: [{ key: "workbench", online: false }],
              currentProjectStatus: { state: "running" },
            },
            ready,
          ).runtimeBusy,
        ).toBe(false);
      },
    );
    it(
      mode +
        " two status failures lock until successful status response; dashboard alone cannot unlock",
      () => {
        const f = setup(mode);
        f.controller.failed();
        expect(f.controller.state(base, ready).clickable).toBe(true);
        f.controller.failed();
        expect(f.controller.state(base, ready)).toMatchObject({
          clickable: false,
          label: "状态服务离线，正在重连…",
        });
        f.controller.observe({ state: "idle", allowed: true }, ready);
        expect(f.controller.state(base, ready).clickable).toBe(false);
        f.controller.observe({ state: "idle", allowed: true }, ready, true);
        expect(f.controller.state(base, ready).clickable).toBe(true);
      },
    );
    it(mode + " cancel confirmation sends nothing", async () => {
      const f = setup(mode);
      expect(await f.controller.submit(base, ready, () => false)).toBeNull();
      expect(f.network).not.toHaveBeenCalled();
    });
  }
  it("cloud eligibility expires after ten seconds, including time spent in confirm", async () => {
    const f = setup();
    f.tick(10000);
    expect(f.controller.state(base, ready).clickable).toBe(true);
    f.tick(10001);
    expect(f.controller.state(base, ready).clickable).toBe(false);
    f.tick(0);
    f.controller.observe({ state: "idle", allowed: true }, ready);
    await expect(
      f.controller.submit(base, ready, () => {
        f.tick(10001);
        return true;
      }),
    ).rejects.toThrow("确认期间");
    expect(f.network).not.toHaveBeenCalled();
  });
  it("eligibility is keyed by command id, not borrowed from another command", () => {
    const f = setup();
    f.controller.observe({ commandId: "A", allowed: true }, ready);
    expect(
      f.controller.state(
        { ...base, controls: { continue: { commandId: "B", allowed: true } } },
        ready,
      ).clickable,
    ).toBe(false);
  });
  for (const health of [
    { ...ready, canContinue: false },
    { ...ready, homeReady: false },
    { ...ready, executorAvailable: false },
    { ...ready, commandBlocker: {} },
  ])
    it("cloud unhealthy gate rejects", async () => {
      const f = setup();
      await expect(
        f.controller.submit(base, health, () => true),
      ).rejects.toThrow("尚未提交");
      expect(f.network).not.toHaveBeenCalled();
    });
  it("unknown can never be retried even if current payload advertises retry", () => {
    const f = setup();
    saveReceipts([receipt("unknown")]);
    f.controller.observe({ allowed: true, continueCanRetry: true }, ready);
    expect(f.controller.state(base, ready).clickable).toBe(false);
    expect(f.controller.target()).toBeNull();
  });
  it("persisted receipt pins original command id; unrelated current status cannot create eligibility", () => {
    const f = setup();
    saveReceipts([receipt()]);
    expect(f.controller.target()).toBe("/api/control-commands/home-original");
    const value = f.controller.observe(
      { commandId: "other", state: "completed", allowed: true },
      ready,
    );
    expect(value).toMatchObject({
      commandId: "home-original",
      state: "persisted",
      allowed: false,
    });
    expect(
      f.controller.state({ ...base, controls: { continue: value } }, ready)
        .clickable,
    ).toBe(false);
    const actual = f.controller.observe(
      { commandId: "home-original", state: "completed", allowed: true },
      ready,
      true,
    );
    expect(actual.allowed).toBe(true);
    f.tick(10001);
    expect(
      f.controller.observe({ commandId: "other", allowed: true }, ready)
        .allowed,
    ).toBe(false);
  });
});
describe("single receive and cross-reload query-only", () => {
  it("home includes exact expectedTarget and clientRequestId in one POST; duplicate during send is blocked", async () => {
    let finish!: (v: Response) => void;
    const network = vi
        .fn()
        .mockReturnValue(new Promise<Response>((r) => (finish = r))),
      f = setup("home", network);
    const work = f.controller.submit(base, ready, () => true);
    await expect(f.controller.submit(base, ready, () => true)).rejects.toThrow(
      "尚未提交",
    );
    expect(network).toHaveBeenCalledTimes(1);
    const body = JSON.parse(network.mock.calls[0][1].body);
    expect(body.expectedTarget).toEqual(expectedContinueTarget(base));
    expect(typeof body.clientRequestId).toBe("string");
    finish(json({ commandId: "home-command", state: "persisted" }));
    expect((await work)?.commandId).toBe("home-command");
  });
  for (const lost of [false, true])
    it(
      "cloud " +
        (lost ? "lost receipt" : "202 receipt") +
        " persists same body/header request id and never resends across reload",
      async () => {
        const body64 = Buffer.from(
          JSON.stringify({ commandId: "home-original", state: "persisted" }),
        ).toString("base64");
        const network = vi.fn().mockImplementation(async (url, init) =>
          String(url) === "/auth/session"
            ? json({ csrf: "synthetic" })
            : init?.method === "POST"
              ? lost
                ? Promise.reject(Error("lost"))
                : json(
                    {
                      cloudCommand: true,
                      state: "queued",
                      cloudCommandId: "cloud-original",
                    },
                    202,
                  )
              : json({
                  state: "completed",
                  cloudCommandId: "cloud-original",
                  result: {
                    kind: "http",
                    httpStatus: 200,
                    bodyBase64: body64,
                  },
                }),
        );
        const f = setup("cloud", network);
        await f.controller.submit(base, ready, () => true);
        const call = network.mock.calls.find((c) => c[1]?.method === "POST")!,
          body = JSON.parse(call[1].body);
        expect(body.clientRequestId).toBe(
          call[1].headers["X-Client-Request-ID"],
        );
        expect(body.expectedTarget).toEqual(expectedContinueTarget(base));
        expect(localReceipts()[0].homeCommandId).toBe("home-original");
        const after = vi.fn().mockResolvedValue(
            json({
              state: "completed",
              cloudCommandId: "cloud-original",
              result: { kind: "http", httpStatus: 200, bodyBase64: body64 },
            }),
          ),
          reader = new ReadClient(after);
        reader.mode = "cloud";
        await new UploadWriter(reader, () => ready).post(
          "/api/control-commands",
          { ...body, clientRequestId: "different-random-id" },
        );
        expect(after.mock.calls.every((c) => !c[1]?.method)).toBe(true);
        expect(
          network.mock.calls.filter((c) => c[1]?.method === "POST"),
        ).toHaveLength(1);
      },
    );
  it("home 409 target changed error is preserved", async () => {
    const f = setup(
      "home",
      vi.fn().mockResolvedValue(json({ detail: "目标已变化" }, 409)),
    );
    await expect(f.controller.submit(base, ready, () => true)).rejects.toThrow(
      "目标已变化",
    );
  });
});
describe("manual receipt administration never retries business command", () => {
  it("unknown requires two manual prompts and exact confirmation; sends only resolve", async () => {
    const network = vi
      .fn()
      .mockResolvedValueOnce(json({ csrf: "synthetic" }))
      .mockResolvedValueOnce(
        json({ state: "resolved_unknown", cloudCommandId: "cloud-original" }),
      );
    const f = setup("cloud", network),
      prompt = vi
        .fn()
        .mockReturnValueOnce("模拟人工已核对原请求停止")
        .mockReturnValueOnce("CONFIRMED_HOME_REQUEST_STOPPED");
    saveReceipts([receipt("unknown")]);
    await new CommandAdmin(f.reader, () => true, prompt).resolve(
      receipt("unknown"),
    );
    expect(
      network.mock.calls
        .filter((c) => c[1]?.method === "POST")
        .map((c) => c[0]),
    ).toEqual(["/console/commands/cloud-original/resolve"]);
    expect(localReceipts()[0].state).toBe("resolved_unknown");
  });
  it("cancelled prompt never posts resolve; unfinished receipt cannot be finished", async () => {
    const f = setup();
    const admin = new CommandAdmin(
      f.reader,
      () => true,
      () => null,
    );
    expect(await admin.resolve(receipt("unknown"))).toBeNull();
    expect(() => admin.finish(receipt("unknown"))).toThrow("未决");
    expect(f.network).not.toHaveBeenCalled();
  });
  it("cancel uses original request id vs remote command id; sent cannot cancel", async () => {
    const f = setup(
        "cloud",
        vi
          .fn()
          .mockImplementation(async (url) =>
            String(url) === "/auth/session"
              ? json({ csrf: "synthetic" })
              : json({ state: "cancelled" }),
          ),
      ),
      admin = new CommandAdmin(f.reader);
    await admin.cancel(receipt("queued"));
    await admin.cancel({ ...receipt("leased"), remote: true });
    await expect(admin.cancel(receipt("sent"))).rejects.toThrow("发送前");
    expect(
      f.network.mock.calls
        .filter((c) => c[1]?.method === "POST")
        .map((c) => c[0]),
    ).toEqual([
      "/console/commands/request/request-original/cancel",
      "/console/commands/cloud-original/cancel",
    ]);
  });
  it("ending terminal receipt is explicit and does no HTTP; cancellation uses typed submitter id", async () => {
    const f = setup(
        "cloud",
        vi
          .fn()
          .mockImplementation(async (url) =>
            String(url) === "/auth/session"
              ? json({ csrf: "synthetic" })
              : json({ state: "cancelled" }),
          ),
      ),
      admin = new CommandAdmin(f.reader, () => true);
    saveReceipts([receipt()]);
    expect(admin.finish(receipt())).toBe(true);
    expect(localReceipts()).toEqual([]);
    expect(f.network).not.toHaveBeenCalled();
    await admin.cancelSubmission(" office-id ");
    expect(f.network.mock.calls[1][0]).toBe(
      "/console/submission-requests/office-id/cancel",
    );
  });
});
it("UI locks when proof ages out without another network response", async () => {
  const f = setup(),
    controller = safeContinueFor(f.reader);
  controller.observe({ state: "idle", allowed: true }, ready);
  const snapshot = { dashboard: base, status: ready } as unknown as Snapshot;
  const now = vi.spyOn(performance, "now");
  let clock = 0;
  now.mockImplementation(() => clock);
  controller.observe({ state: "idle", allowed: true }, ready);
  render(
    <ContinueActions
      snapshot={snapshot}
      reader={f.reader}
      refresh={vi.fn()}
      onResult={vi.fn()}
    />,
  );
  expect(
    screen.getByRole("button", { name: "安全继续当前项目" }),
  ).toBeEnabled();
  clock = 10001;
  await waitFor(
    () =>
      expect(
        screen.getByRole("button", { name: "安全继续当前项目" }),
      ).toBeDisabled(),
    { timeout: 2000 },
  );
  fireEvent.click(screen.getByRole("button", { name: "安全继续当前项目" }));
  expect(f.network).not.toHaveBeenCalled();
});

it("home HTTP fallback creates original dashboard request id when randomUUID is unavailable", async () => {
  const original = Object.getOwnPropertyDescriptor(crypto, "randomUUID");
  Object.defineProperty(crypto, "randomUUID", {
    configurable: true,
    value: undefined,
  });
  try {
    const f = setup("home");
    await f.controller.submit(base, ready, () => true);
    expect(JSON.parse(f.network.mock.calls[0][1].body).clientRequestId).toMatch(
      /^dashboard-\d+-/,
    );
  } finally {
    if (original) Object.defineProperty(crypto, "randomUUID", original);
    else delete (crypto as unknown as Record<string, unknown>).randomUUID;
  }
});
it("home timeout leaves no automatic business retry and preserves timeout message", async () => {
  const f = setup(
    "home",
    vi.fn().mockRejectedValue(new DOMException("deadline", "AbortError")),
  );
  await expect(f.controller.submit(base, ready, () => true)).rejects.toThrow(
    "已等待 10 秒",
  );
  expect(f.network).toHaveBeenCalledTimes(1);
});
it("manual resolve never auto-confirms wrong typed phrase", async () => {
  const f = setup(),
    prompt = vi
      .fn()
      .mockReturnValueOnce("模拟已核实原请求停止")
      .mockReturnValueOnce("wrong");
  expect(
    await new CommandAdmin(f.reader, () => true, prompt).resolve(
      receipt("unknown"),
    ),
  ).toBeNull();
  expect(f.network).not.toHaveBeenCalled();
});
it("cloud failed qualification cannot call home directly", async () => {
  const f = setup();
  f.controller.observe({ state: "blocked", allowed: false }, ready);
  await expect(
    f.controller.submit(
      { ...base, controls: { continue: { allowed: false, state: "blocked" } } },
      ready,
      () => true,
    ),
  ).rejects.toThrow("尚未提交");
  expect(f.network).not.toHaveBeenCalled();
});
