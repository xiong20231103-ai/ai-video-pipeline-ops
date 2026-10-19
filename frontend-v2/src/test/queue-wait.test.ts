import { afterEach, describe, expect, it, vi } from "vitest";
import { ReadClient } from "@/data/client";
import { controlTimeoutError } from "@/data/control-timeout";
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
afterEach(() => vi.useRealTimers());
describe("cloud queue waiting is independent from each HTTP deadline", () => {
  it("can display a 200 payload after 30 seconds of continuous 202 replies", async () => {
    vi.useFakeTimers();
    const start = Date.now();
    const network = vi
      .fn()
      .mockImplementation(async () =>
        Date.now() - start < 30000
          ? json({ queued: true }, 202)
          : json({
              selectedDate: "10.19",
              message: "fixture data after queue",
            }),
      );
    const reader = new ReadClient(network);
    reader.mode = "cloud";
    const request = reader.read("/api/dashboard", 0),
      resolved = expect(request).resolves.toEqual({
        selectedDate: "10.19",
        message: "fixture data after queue",
      });
    await vi.advanceTimersByTimeAsync(30000);
    await resolved;
    expect(network).toHaveBeenCalledTimes(61);
    expect(reader.controller.signal.aborted).toBe(false);
  });
  it("allows exactly 120 pending polls, with 500ms waits, before reporting pending", async () => {
    vi.useFakeTimers();
    const network = vi.fn().mockResolvedValue(json({ queued: true }, 202)),
      reader = new ReadClient(network);
    reader.mode = "cloud";
    const checked = expect(reader.read("/api/dashboard", 0)).rejects.toThrow(
      "正在向家里取数",
    );
    await vi.advanceTimersByTimeAsync(60000);
    await checked;
    expect(network).toHaveBeenCalledTimes(120);
  });
  it("still aborts a single hung request eight seconds after that request starts", async () => {
    vi.useFakeTimers();
    const network = vi
      .fn()
      .mockResolvedValueOnce(json({}, 202))
      .mockImplementation(
        (_url: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) =>
            init!.signal!.addEventListener("abort", () =>
              reject(new DOMException("Aborted", "AbortError")),
            ),
          ),
      );
    const reader = new ReadClient(network);
    reader.mode = "cloud";
    const checked = expect(reader.read("/api/dashboard", 0)).rejects.toThrow(
      "Aborted",
    );
    await vi.advanceTimersByTimeAsync(500);
    expect(network).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(8000);
    await checked;
  });
  it("can cancel the 500ms queue wait on teardown without another request", async () => {
    vi.useFakeTimers();
    const network = vi.fn().mockResolvedValue(json({}, 202)),
      reader = new ReadClient(network);
    reader.mode = "cloud";
    const checked = expect(reader.read("/api/dashboard", 0)).rejects.toThrow(
      "Aborted",
    );
    await vi.advanceTimersByTimeAsync(100);
    reader.stop();
    await checked;
    expect(network).toHaveBeenCalledTimes(1);
  });
});
describe("PR33 legacy timeout units and unchanged recovery advice", () => {
  for (const [duration, expected] of [
    [10000, "10 秒"],
    [59999, "60 秒"],
    [60000, "1 分钟"],
    [90000, "2 分钟"],
    [900000, "15 分钟"],
  ] as const)
    it(`${duration}ms uses ${expected}`, () => {
      const cause = new Error("synthetic");
      const error = controlTimeoutError(duration, cause);
      expect(error.message).toBe(
        `操作仍在后台处理（已等待 ${expected}），请刷新状态后再继续`,
      );
      expect(error.cause).toBe(cause);
      expect(Reflect.get(error, "code")).toBe("CONTROL_REQUEST_TIMEOUT");
    });
});
