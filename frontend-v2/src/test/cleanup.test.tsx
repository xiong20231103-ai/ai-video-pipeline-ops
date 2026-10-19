import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  HomeCleanup,
  cleanupSpecs,
  type CleanupKind,
} from "@/data/home-cleanup";
import { ReadClient } from "@/data/client";
import FileManagers from "@/components/views/FileManagers";
import type { Row, Snapshot } from "@/data/types";
const kinds: CleanupKind[] = ["drafts", "audio", "production"];
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const previewFor = (kind: CleanupKind): Row => ({
  deletableCount: 1,
  blockedCount: 1,
  sizeBytes: 1024,
  snapshotToken: "synthetic-snapshot",
  deletable: [{ [cleanupSpecs[kind].id]: "server-object", name: "普通文件" }],
  blocked: [{ name: "受保护文件", reason: "lease-active" }],
  message: "隔离预览",
});
beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});
describe("home cleanup exact contracts without real files", () => {
  for (const kind of kinds) {
    it(`${kind}: preview uses only server object IDs and 60s timeout`, async () => {
      const network = vi.fn().mockResolvedValue(json(previewFor(kind))),
        reader = new ReadClient(network);
      reader.mode = "home";
      const timer = vi.spyOn(globalThis, "setTimeout");
      const service = new HomeCleanup(reader, () => true);
      await service.preview(kind, ["server-object"]);
      expect(network.mock.calls[0][0]).toBe(
        "/api/controls/" + cleanupSpecs[kind].endpoint + "/preview",
      );
      expect(JSON.parse(network.mock.calls[0][1].body)).toEqual({
        [cleanupSpecs[kind].ids]: ["server-object"],
      });
      expect(timer.mock.calls.some((call) => call[1] === 60000)).toBe(true);
    });
    it(`${kind}: execute uses preview deletable IDs, exact token, confirmation and original timeout`, async () => {
      const network = vi
          .fn()
          .mockResolvedValue(
            json({
              state: "partial_failed",
              message: "部分失败",
              results: [
                { name: "fixture", state: "failed", reason: "mock-locked" },
              ],
            }),
          ),
        reader = new ReadClient(network);
      reader.mode = "home";
      const confirm = vi.fn().mockReturnValue(true),
        timer = vi.spyOn(globalThis, "setTimeout"),
        service = new HomeCleanup(reader, confirm);
      const value = await service.execute(kind, previewFor(kind));
      expect(value?.state).toBe("partial_failed");
      const [url, init] = network.mock.calls[0];
      expect(url).toBe(
        "/api/controls/" +
          cleanupSpecs[kind].endpoint +
          "/" +
          cleanupSpecs[kind].action,
      );
      const expected: Row = {
        [cleanupSpecs[kind].ids]: ["server-object"],
        snapshotToken: "synthetic-snapshot",
        confirm: cleanupSpecs[kind].confirmation,
      };
      if (kind === "drafts") expected.includeUnknown = false;
      expect(JSON.parse(init.body)).toEqual(expected);
      expect(confirm.mock.calls[0][0]).toContain(
        "保留 3 天后自动清除，期间可恢复",
      );
      expect(
        timer.mock.calls.some(
          (call) => call[1] === (kind === "production" ? 900000 : 10000),
        ),
      ).toBe(true);
    });
    it(`${kind}: cancel confirmation sends nothing; changed snapshot error is preserved`, async () => {
      const network = vi
          .fn()
          .mockResolvedValue(json({ detail: "snapshot changed" }, 409)),
        reader = new ReadClient(network);
      reader.mode = "home";
      expect(
        await new HomeCleanup(reader, () => false).execute(
          kind,
          previewFor(kind),
        ),
      ).toBeNull();
      expect(network).not.toHaveBeenCalled();
      await expect(
        new HomeCleanup(reader, () => true).execute(kind, previewFor(kind)),
      ).rejects.toThrow("snapshot changed");
      await expect(
        new HomeCleanup(reader, () => true).execute(kind, {
          ...previewFor(kind),
          snapshotToken: "",
        }),
      ).rejects.toThrow("预览契约不完整");
    });
    it(`${kind}: cloud cannot POST a home cleanup route`, async () => {
      const network = vi.fn(),
        reader = new ReadClient(network);
      reader.mode = "cloud";
      await expect(
        new HomeCleanup(reader).preview(kind, ["fixture"]),
      ).rejects.toThrow("云端必须使用清理队列");
      expect(network).not.toHaveBeenCalled();
    });
  }
  it("manual/unknown draft and test production require their own second confirmation", async () => {
    const network = vi.fn(),
      reader = new ReadClient(network);
    reader.mode = "home";
    for (const [kind, flag] of [
      ["drafts", "containsManualOrUnknown"],
      ["production", "containsTestFiles"],
    ] as const) {
      const confirm = vi
        .fn()
        .mockReturnValueOnce(true)
        .mockReturnValueOnce(false);
      expect(
        await new HomeCleanup(reader, confirm).execute(kind, {
          ...previewFor(kind),
          [flag]: true,
        }),
      ).toBeNull();
      expect(confirm).toHaveBeenCalledTimes(2);
    }
    expect(network).not.toHaveBeenCalled();
  });
  it("pending purge needs both confirmations, exact body and 10 minute timeout", async () => {
    const network = vi
        .fn()
        .mockResolvedValue(json({ message: "fixture purge" })),
      reader = new ReadClient(network);
    reader.mode = "home";
    expect(
      await new HomeCleanup(
        reader,
        vi.fn().mockReturnValueOnce(true).mockReturnValueOnce(false),
      ).emptyPending({ count: 2, sizeBytes: 1024 }),
    ).toBeNull();
    expect(network).not.toHaveBeenCalled();
    const timer = vi.spyOn(globalThis, "setTimeout");
    await new HomeCleanup(reader, () => true).emptyPending({
      count: 2,
      sizeBytes: 1024,
    });
    expect(network.mock.calls[0][0]).toBe("/api/controls/pending-delete/empty");
    expect(JSON.parse(network.mock.calls[0][1].body)).toEqual({
      confirm: "EMPTY_PENDING_DELETE_NOW",
    });
    expect(timer.mock.calls.some((call) => call[1] === 600000)).toBe(true);
  });
  it("read-view cancellation does not abort a long cleanup, and another instance cannot send twice", async () => {
    let done!: (value: Response) => void;
    const waiting = new Promise<Response>((resolve) => {
        done = resolve;
      }),
      network = vi.fn().mockReturnValue(waiting),
      reader = new ReadClient(network);
    reader.mode = "home";
    const first = new HomeCleanup(reader, () => true).execute(
      "production",
      previewFor("production"),
    );
    reader.stop();
    await expect(
      new HomeCleanup(reader, () => true).execute(
        "production",
        previewFor("production"),
      ),
    ).rejects.toThrow("仍在处理");
    expect(network.mock.calls[0][1].signal.aborted).toBe(false);
    done(json({ state: "completed" }));
    await first;
    expect(network).toHaveBeenCalledTimes(1);
  });
  it("timeout never retries and reports the original duration", async () => {
    const network = vi
        .fn()
        .mockRejectedValue(new DOMException("timeout", "AbortError")),
      reader = new ReadClient(network);
    reader.mode = "home";
    await expect(
      new HomeCleanup(reader, () => true).execute(
        "production",
        previewFor("production"),
      ),
    ).rejects.toThrow("已等待 15 分钟");
    expect(network).toHaveBeenCalledTimes(1);
  });
});
describe("file selection/preview safety in actual React managers", () => {
  for (const kind of kinds)
    it(`${kind}: protected rows cannot be selected; filters invalidate preview; duplicate execute sends once`, async () => {
      const spec = cleanupSpecs[kind],
        rows = [
          {
            [spec.id]: "server-object",
            name: "普通文件",
            category: kind === "drafts" ? "formal" : "final_output",
            defaultSelected: kind === "production",
            sizeBytes: 1024,
            updatedAt: "2026-10-19T12:00:00+08:00",
          },
          {
            [spec.id]: "locked",
            name: "受保护文件",
            protected: true,
            protectedReason: "lease-active",
            sizeBytes: 200,
          },
        ];
      const network = vi.fn().mockImplementation(async (url, init) => {
        if (init?.method === "POST")
          return json(
            String(url).endsWith("/preview")
              ? previewFor(kind)
              : {
                  state: "partial_failed",
                  message: "部分失败",
                  results: [{ name: "fixture", reason: "mock-locked" }],
                },
          );
        return json({
          items: rows,
          counts: { total: 2, protected: 1 },
          snapshotToken: "synthetic-list",
        });
      });
      const reader = new ReadClient(network);
      reader.mode = "home";
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
      vi.spyOn(window, "alert").mockImplementation(() => undefined);
      const snapshot = {
        mode: "home",
        pendingDelete: { count: 0 },
        status: {},
      } as unknown as Snapshot;
      render(
        <FileManagers
          snapshot={snapshot}
          reader={reader}
          refresh={() => undefined}
        />,
      );
      fireEvent.click(
        screen.getByRole("button", { name: "管理 " + spec.title }),
      );
      const checkbox = await screen.findByRole("checkbox", {
        name: "选择 普通文件",
      });
      expect(
        screen.getByRole("checkbox", { name: "选择 受保护文件" }),
      ).toBeDisabled();
      if (kind !== "production") fireEvent.click(checkbox);
      fireEvent.click(
        screen.getByRole("button", {
          name: kind === "production" ? "预览清理" : "预览删除",
        }),
      );
      await screen.findByRole("button", { name: "确认移入待删区" });
      fireEvent.change(screen.getByRole("searchbox", { name: "搜索文件" }), {
        target: { value: "普通" },
      });
      expect(
        screen.queryByRole("button", { name: "确认移入待删区" }),
      ).toBeNull();
      fireEvent.click(
        screen.getByRole("button", {
          name: kind === "production" ? "预览清理" : "预览删除",
        }),
      );
      const execute = await screen.findByRole("button", {
        name: "确认移入待删区",
      });
      fireEvent.click(execute);
      fireEvent.click(execute);
      await waitFor(() =>
        expect(
          network.mock.calls.filter(
            (call) =>
              call[1]?.method === "POST" &&
              !String(call[0]).endsWith("/preview"),
          ),
        ).toHaveLength(1),
      );
      expect(confirm).toHaveBeenCalledTimes(1);
      await screen.findByRole("status");
      expect(screen.getByRole("status")).toHaveTextContent("部分失败");
    });
});
