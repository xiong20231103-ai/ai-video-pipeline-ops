import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { CloudCleanup } from "@/data/cloud-cleanup";
import { cleanupSpecs, type CleanupKind } from "@/data/home-cleanup";
import { ReadClient } from "@/data/client";
import { UploadWriter } from "@/data/upload-writer";
import { localReceipts, saveReceipts } from "@/data/receipts";
import FileManagers from "@/components/views/FileManagers";
import type { Row, Snapshot } from "@/data/types";
const json = (v: unknown, status = 200) =>
  new Response(JSON.stringify(v), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const ready = { canCleanup: true, executorAvailable: true, homeReady: true };
function fixture(
  kind: CleanupKind | "pending" = "audio",
  ids: string[] = kind === "pending" ? [] : ["server-object"],
) {
  let clock = 0,
    health: Row = { ...ready };
  const reader = new ReadClient(vi.fn());
  reader.mode = "cloud";
  const writer = new UploadWriter(reader, () => health);
  const value: Row = {
    kind,
    ids,
    ticket: "synthetic-ticket",
    expiresAt: 2000000000,
    snapshotToken: "synthetic-snapshot",
    deletableCount: 1,
  };
  const post = vi.spyOn(writer, "post").mockImplementation(async (path) =>
    path.endsWith("/preview")
      ? { ...value }
      : {
          state: "partial_failed",
          message: "模拟部分失败",
          results: [{ reason: "lease-active" }],
        },
  );
  const confirm = vi.fn().mockReturnValue(true),
    prompt = vi
      .fn()
      .mockReturnValue(
        kind === "pending"
          ? "EMPTY_PENDING_DELETE_NOW"
          : cleanupSpecs[kind].confirmation,
      );
  const service = new CloudCleanup(
    reader,
    writer,
    confirm,
    prompt,
    () => clock,
  );
  return {
    reader,
    writer,
    post,
    value,
    confirm,
    prompt,
    service,
    tick: (n: number) => {
      clock = n;
    },
    health: (v: Row) => {
      health = v;
    },
  };
}
beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});
describe("cloud cleanup ticket parity; no live requests", () => {
  for (const kind of ["drafts", "audio", "production"] as const)
    it(
      kind + ": exact original queue bodies and confirmation sequence",
      async () => {
        const f = fixture(kind);
        f.value.containsManualOrUnknown = kind === "drafts";
        f.value.containsTestFiles = kind === "production";
        await f.service.preview(kind, ["server-object"]);
        const result = await f.service.execute(kind, ["server-object"]);
        expect(f.post.mock.calls).toEqual([
          [
            "/api/controls/cloud-cleanup/preview",
            { kind, ids: ["server-object"], includeUnknown: kind === "drafts" },
          ],
          [
            "/api/controls/cloud-cleanup/execute",
            {
              kind,
              ids: ["server-object"],
              includeUnknown: kind === "drafts",
              snapshotToken: "synthetic-snapshot",
              ticket: "synthetic-ticket",
              expiresAt: 2000000000,
              confirm: cleanupSpecs[kind].confirmation,
            },
          ],
        ]);
        expect(result?.state).toBe("partial_failed");
        expect(f.prompt).toHaveBeenCalledTimes(1);
        expect(f.confirm.mock.calls.map((c) => c[0])).toEqual(
          kind === "drafts"
            ? [
                "本次选择是否包含人工或来源不明草稿？选“取消”将保护这类草稿。",
                "包含人工或来源不明草稿，请再次确认所选对象。",
                "所选对象将移入待删区，保留3天后清除。是否继续？",
              ]
            : kind === "production"
              ? [
                  "包含测试文件，请再次确认所选对象。",
                  "所选对象将移入待删区，保留3天后清除。是否继续？",
                ]
              : ["所选对象将移入待删区，保留3天后清除。是否继续？"],
        );
      },
    );
  it("pending always previews fresh, exact two typed confirmations", async () => {
    const f = fixture("pending");
    await f.service.execute("pending", []);
    expect(f.post.mock.calls[0][1]).toEqual({
      kind: "pending",
      ids: [],
      includeUnknown: false,
    });
    expect(f.prompt.mock.calls).toEqual([
      ["请输入 EMPTY_PENDING_DELETE_NOW 确认本次操作"],
      ["再次输入 EMPTY_PENDING_DELETE_NOW 确认永久清除"],
    ]);
  });
  for (const [label, health] of Object.entries({
    disabled: { ...ready, canCleanup: false },
    offline: { ...ready, homeReady: false },
    executor: { ...ready, executorAvailable: false },
    blocked: { ...ready, commandBlocker: { id: "x" } },
  }))
    it(label + " gate sends no command", async () => {
      const f = fixture();
      f.health(health);
      await expect(
        f.service.preview("audio", ["server-object"]),
      ).rejects.toThrow("尚未提交");
      expect(f.post).not.toHaveBeenCalled();
    });
  it("pending local receipt and home mode both fail closed", async () => {
    const f = fixture();
    saveReceipts([
      { path: "/x", requestId: "x", fingerprint: "x", state: "unknown" },
    ]);
    await expect(f.service.preview("audio", ["server-object"])).rejects.toThrow(
      "尚未提交",
    );
    localStorage.clear();
    f.reader.mode = "home";
    await expect(f.service.preview("audio", ["server-object"])).rejects.toThrow(
      "尚未提交",
    );
    expect(f.post).not.toHaveBeenCalled();
  });
  for (const field of ["kind", "ids", "ticket", "expiresAt"])
    it("invalid returned " + field + " rejects preview", async () => {
      const f = fixture();
      f.value[field] = null;
      await expect(
        f.service.preview("audio", ["server-object"]),
      ).rejects.toThrow("预览契约不完整");
      await expect(
        f.service.execute("audio", ["server-object"]),
      ).rejects.toThrow("重新预览");
      expect(f.post).toHaveBeenCalledTimes(1);
    });
  it("changed IDs/order, exact expiry, reload and manual invalidation reject execute", async () => {
    const f = fixture();
    await f.service.preview("audio", ["server-object"]);
    await expect(f.service.execute("audio", ["different"])).rejects.toThrow(
      "选择已变化",
    );
    f.tick(120000);
    await expect(f.service.execute("audio", ["server-object"])).rejects.toThrow(
      "预览已过期",
    );
    f.tick(0);
    await f.service.preview("audio", ["server-object"]);
    f.service.invalidate();
    await expect(f.service.execute("audio", ["server-object"])).rejects.toThrow(
      "预览已过期",
    );
    const fresh = new CloudCleanup(f.reader, f.writer);
    await expect(fresh.execute("audio", ["server-object"])).rejects.toThrow(
      "页面已重载",
    );
    expect(f.post.mock.calls.every((c) => c[0].endsWith("/preview"))).toBe(
      true,
    );
  });
  for (const stage of [
    "confirm",
    "prompt",
    "expiry-during-prompt",
    "second-pending-prompt",
  ] as const)
    it("cancel or expiry at " + stage + " never executes", async () => {
      const pending = stage === "second-pending-prompt",
        f = fixture(pending ? "pending" : "audio");
      if (stage === "confirm") f.confirm.mockReturnValue(false);
      if (stage === "prompt") f.prompt.mockReturnValue(null);
      if (stage === "expiry-during-prompt")
        f.prompt.mockImplementation(() => {
          f.tick(120001);
          return "RECYCLE_SELECTED_AUDIO_FILES";
        });
      if (pending)
        f.prompt
          .mockReturnValueOnce("EMPTY_PENDING_DELETE_NOW")
          .mockReturnValueOnce(null);
      if (!pending) await f.service.preview("audio", ["server-object"]);
      const work = f.service.execute(
        pending ? "pending" : "audio",
        pending ? [] : ["server-object"],
      );
      if (stage === "expiry-during-prompt")
        await expect(work).rejects.toThrow("确认期间");
      else expect(await work).toBeNull();
      expect(
        f.post.mock.calls.filter((c) => c[0].endsWith("/execute")),
      ).toHaveLength(0);
    });
});
describe("cloud transport uses one receive POST and original identity only", () => {
  function pipeline(lost = false) {
    let sequence = 0;
    const network = vi.fn().mockImplementation(async (url, init) => {
      if (String(url) === "/auth/session")
        return json({ csrf: "fixture-only" });
      if (init?.method === "POST") {
        sequence++;
        if (lost) throw Error("lost receipt");
        return json(
          {
            cloudCommand: true,
            state: "queued",
            cloudCommandId: "synthetic-" + sequence,
          },
          202,
        );
      }
      return json({
        cloudCommand: true,
        state: "completed",
        cloudCommandId: "synthetic-" + sequence,
        result: {
          kind: "http",
          httpStatus: 200,
          bodyBase64: Buffer.from(
            JSON.stringify({
              kind: "audio",
              ids: ["server-object"],
              ticket: "synthetic-ticket",
              expiresAt: 2000000000,
              snapshotToken: "snapshot",
              deletableCount: 1,
            }),
          ).toString("base64"),
        },
      });
    });
    const reader = new ReadClient(network);
    reader.mode = "cloud";
    vi.spyOn(reader, "wait").mockResolvedValue();
    return {
      network,
      reader,
      writer: new UploadWriter(reader, () => ({ ...ready })),
    };
  }
  it("terminal preview is discarded before next preview; pending preview remains query-only", async () => {
    const f = pipeline();
    const body = {
      kind: "audio",
      ids: ["server-object"],
      includeUnknown: false,
    };
    await f.writer.post("/api/controls/cloud-cleanup/preview", body);
    await f.writer.post("/api/controls/cloud-cleanup/preview", body);
    expect(
      f.network.mock.calls.filter((c) => c[1]?.method === "POST"),
    ).toHaveLength(2);
    expect(localReceipts()).toHaveLength(1);
    const headers = f.network.mock.calls.find(
      (c) => c[1]?.method === "POST",
    )![1].headers;
    expect(headers["X-CSRF-Token"]).toBe("fixture-only");
    expect(headers["X-Client-Request-ID"]).toBeTruthy();
  });
  it("execute lost reply and same body after reload only GET, no repeated POST", async () => {
    const f = pipeline(true),
      body = {
        kind: "audio",
        ids: ["server-object"],
        ticket: "synthetic-ticket",
      };
    await f.writer.post("/api/controls/cloud-cleanup/execute", body);
    const second = pipeline();
    await second.writer.post("/api/controls/cloud-cleanup/execute", body);
    expect(
      f.network.mock.calls.filter((c) => c[1]?.method === "POST"),
    ).toHaveLength(1);
    expect(second.network.mock.calls.every((c) => !c[1]?.method)).toBe(true);
  });
  it("unknown preview keeps original receipt and issues no new POST", async () => {
    const f = pipeline();
    await f.writer.post("/api/controls/cloud-cleanup/preview", {
      kind: "audio",
    });
    const r = localReceipts()[0];
    saveReceipts([{ ...r, state: "unknown" }]);
    f.network.mockImplementation(async () =>
      json({ state: "unknown", cloudCommandId: r.cloudCommandId }),
    );
    await expect(
      f.writer.post("/api/controls/cloud-cleanup/preview", { kind: "audio" }),
    ).rejects.toThrow("结果不明");
    expect(
      f.network.mock.calls.filter((c) => c[1]?.method === "POST"),
    ).toHaveLength(1);
  });
});
it("cloud UI remains locked when cleanup switch is false and only requests capabilities while manager open", async () => {
  const network = vi
      .fn()
      .mockImplementation(async (url) =>
        json(
          String(url).endsWith("capabilities")
            ? { protocol: 1 }
            : { items: [{ audioId: "server-object", name: "模拟音频" }] },
        ),
      ),
    reader = new ReadClient(network);
  reader.mode = "cloud";
  const snapshot = {
    mode: "cloud",
    status: { ...ready, canCleanup: false },
    pendingDelete: { count: 1, sizeBytes: 1000 },
  } as unknown as Snapshot;
  render(
    <FileManagers reader={reader} snapshot={snapshot} refresh={vi.fn()} />,
  );
  expect(network).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: /立即清空待删区/ })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "管理 音频文件" }));
  await screen.findByRole("checkbox", { name: "选择 模拟音频" });
  fireEvent.click(screen.getByRole("checkbox", { name: "选择 模拟音频" }));
  expect(screen.getByRole("button", { name: "预览删除" })).toBeDisabled();

  await waitFor(() =>
    expect(
      network.mock.calls.some((c) => String(c[0]).endsWith("/capabilities")),
    ).toBe(true),
  );
  expect(network.mock.calls.every((c) => !c[1]?.method)).toBe(true);
});
