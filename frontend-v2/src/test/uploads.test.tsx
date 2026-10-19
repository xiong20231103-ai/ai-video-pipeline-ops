const encodeBody = (value: string) =>
  Buffer.from(value, "utf8").toString("base64");
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { ReadClient } from "@/data/client";
import { UploadWriter } from "@/data/upload-writer";
import { UploadActions } from "@/components/views/UploadActions";
import { localReceipts, saveReceipts } from "@/data/receipts";
import type { Snapshot } from "@/data/types";
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const completed = (status = 200) => ({
  state: "completed",
  cloudCommandId: "fixture-command",
  result: {
    kind: "http",
    httpStatus: status,
    bodyBase64: encodeBody(
      JSON.stringify(
        status === 200
          ? { state: "requested", message: "模拟 HTTP 回执" }
          : { detail: "模拟拒绝" },
      ),
    ),
  },
});
function cloud(network: typeof fetch) {
  const reader = new ReadClient(network);
  reader.mode = "cloud";
  vi.spyOn(reader, "wait").mockResolvedValue();
  return new UploadWriter(reader, () => ({
    executorAvailable: true,
    homeReady: true,
  }));
}
beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
describe("upload transport: all network is mocked", () => {
  for (const action of ["rescan", "verify-history"])
    it(`home ${action}: exact empty POST body, one request`, async () => {
      const network = vi.fn().mockResolvedValue(json({ message: "fixture" }));
      const reader = new ReadClient(network);
      reader.mode = "home";
      await new UploadWriter(reader, () => ({})).post(
        "/api/controls/upload/" + action,
      );
      expect(network).toHaveBeenCalledTimes(1);
      expect(network.mock.calls[0][0]).toBe("/api/controls/upload/" + action);
      expect(network.mock.calls[0][1]).toMatchObject({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
    });
  it("cloud requires receipt contract and gets final home HTTP body, not the 202 envelope", async () => {
    const network = vi
      .fn()
      .mockResolvedValueOnce(json({ csrf: "mock-csrf" }))
      .mockResolvedValueOnce(
        json(
          {
            cloudCommand: true,
            state: "queued",
            cloudCommandId: "fixture-command",
          },
          202,
        ),
      )
      .mockResolvedValueOnce(json(completed()));
    const result = await cloud(network).post("/api/controls/upload/rescan");
    expect(result.message).toBe("模拟 HTTP 回执");
    const posts = network.mock.calls.filter(
      (call) => call[1]?.method === "POST",
    );
    expect(posts).toHaveLength(1);
    expect(posts[0][1].headers).toMatchObject({
      "X-CSRF-Token": "mock-csrf",
      "X-Client-Request-ID": localReceipts()[0].requestId,
    });
    expect(posts[0][1].body).toBe("{}");
    expect(localReceipts()[0].state).toBe("completed");
  });
  it("lost POST acknowledgement and reload recover by GET only; same input never repeats POST", async () => {
    const network = vi
      .fn()
      .mockResolvedValueOnce(json({ csrf: "mock" }))
      .mockRejectedValueOnce(new TypeError("lost response"))
      .mockResolvedValueOnce(json(completed()));
    await cloud(network).post("/api/controls/upload/rescan");
    const afterReload = vi.fn().mockResolvedValue(json(completed()));
    await cloud(afterReload).post("/api/controls/upload/rescan");
    expect(afterReload.mock.calls.every((call) => !call[1]?.method)).toBe(true);
    expect(
      network.mock.calls.filter((call) => call[1]?.method === "POST"),
    ).toHaveLength(1);
  });
  it("unknown remains blocked and is never retried", async () => {
    const network = vi
      .fn()
      .mockResolvedValueOnce(json({ csrf: "mock" }))
      .mockResolvedValueOnce(
        json(
          { cloudCommand: true, state: "unknown", cloudCommandId: "fixture" },
          202,
        ),
      );
    await expect(
      cloud(network).post("/api/controls/upload/rescan"),
    ).rejects.toThrow("结果不明");
    expect(localReceipts()[0].state).toBe("unknown");
  });
  it("queued timeout keeps original identity and never resends", async () => {
    const network = vi.fn().mockImplementation(async (url, init) =>
      init?.method === "POST"
        ? json(
            {
              cloudCommand: true,
              state: "queued",
              cloudCommandId: "fixture",
            },
            202,
          )
        : String(url) === "/auth/session"
          ? json({ csrf: "mock" })
          : json({ state: "queued", cloudCommandId: "fixture" }),
    );
    await expect(
      cloud(network).post("/api/controls/upload/rescan"),
    ).rejects.toThrow("不会自动重发");
    expect(localReceipts()[0].state).toBe("queued");
    expect(
      network.mock.calls.filter((call) => call[1]?.method === "POST"),
    ).toHaveLength(1);
  });
  it("cloud rejection is not_sent, final home HTTP error is displayed unchanged", async () => {
    const refused = vi
      .fn()
      .mockResolvedValueOnce(json({ csrf: "mock" }))
      .mockResolvedValueOnce(json({ detail: "mock forbidden" }, 403));
    await expect(
      cloud(refused).post("/api/controls/upload/rescan"),
    ).rejects.toThrow("mock forbidden");
    expect(localReceipts()[0].state).toBe("not_sent");
    localStorage.clear();
    const homeFailed = vi
      .fn()
      .mockResolvedValueOnce(json({ csrf: "mock" }))
      .mockResolvedValueOnce(
        json({ cloudCommand: true, ...completed(409) }, 202),
      );
    await expect(
      cloud(homeFailed).post("/api/controls/upload/rescan"),
    ).rejects.toThrow("模拟拒绝");
  });
  it("unready health and existing unknown command prevent any POST", async () => {
    const network = vi.fn(),
      reader = new ReadClient(network);
    reader.mode = "cloud";
    await expect(
      new UploadWriter(reader, () => ({})).post("/api/controls/upload/rescan"),
    ).rejects.toThrow("未就绪");
    saveReceipts([
      {
        path: "/other",
        fingerprint: "mock",
        requestId: "mock",
        state: "unknown",
      },
    ]);
    await expect(
      cloud(network).post("/api/controls/upload/rescan"),
    ).rejects.toThrow("待对账");
    expect(network).not.toHaveBeenCalled();
  });
  it("home timeout message matches old postJson and does not retry", async () => {
    const network = vi
      .fn()
      .mockRejectedValue(new DOMException("timeout", "AbortError"));
    const reader = new ReadClient(network);
    reader.mode = "home";
    await expect(
      new UploadWriter(reader, () => ({})).post("/api/controls/upload/rescan"),
    ).rejects.toThrow("操作仍在后台处理（已等待 10 秒）");
    expect(network).toHaveBeenCalledTimes(1);
  });
});
describe("upload confirmation and duplicate guard, home and cloud", () => {
  for (const mode of ["home", "cloud"] as const)
    it(`${mode}: cancel sends nothing, double-click sends once and disables both buttons`, async () => {
      let resolve!: (response: Response) => void;
      const waiting = new Promise<Response>((done) => {
        resolve = done;
      });
      const network = vi
        .fn()
        .mockImplementation(async (url, init) =>
          init?.method === "POST"
            ? waiting
            : String(url) === "/auth/session"
              ? json({ csrf: "mock" })
              : json(completed()),
        );
      const reader = new ReadClient(network);
      reader.mode = mode;
      vi.spyOn(reader, "wait").mockResolvedValue();
      const snapshot = {
        mode,
        status: { executorAvailable: true, homeReady: true },
        dashboard: { controls: {} },
      } as unknown as Snapshot;
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
      render(
        <UploadActions
          snapshot={snapshot}
          reader={reader}
          refresh={() => undefined}
        />,
      );
      const button = screen.getByRole("button", {
        name: "重新对账、补传并清理",
      });
      fireEvent.click(button);
      expect(network).not.toHaveBeenCalled();
      confirm.mockReturnValue(true);
      fireEvent.click(button);
      fireEvent.click(button);
      await waitFor(() =>
        expect(
          network.mock.calls.filter((call) => call[1]?.method === "POST"),
        ).toHaveLength(1),
      );
      expect(button).toBeDisabled();
      expect(
        screen.getByRole("button", { name: "核验历史云端文件" }),
      ).toBeDisabled();
      resolve(
        mode === "cloud"
          ? json(
              {
                cloudCommand: true,
                state: "queued",
                cloudCommandId: "fixture",
              },
              202,
            )
          : json({ message: "fixture" }),
      );
      await waitFor(() => expect(button).not.toBeDisabled());
      expect(confirm.mock.calls[1][0]).toContain("不会重新剪辑等待中的任务");
    });
});
