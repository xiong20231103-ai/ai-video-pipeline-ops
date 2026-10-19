import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import TaskOperations from "@/components/views/TaskOperations";
import { ReadClient } from "@/data/client";
import { UploadWriter } from "@/data/upload-writer";
import type { Row, Snapshot } from "@/data/types";
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
const task = {
  taskId: "fixture/task",
  project: "模拟项目",
  material: "模拟材料",
  status: "pending_confirmation",
  expectedCount: 3,
  completed: 1,
  gapActive: true,
  missingCount: 2,
};
function setup(mode: "home" | "cloud", replenishment: Row | null = null) {
  const network = vi.fn().mockImplementation(async (url, init) => {
    if (String(url) === "/auth/session") return json({ csrf: "mock" });
    if (init?.method === "POST")
      return mode === "home"
        ? json({ message: "模拟业务回执" })
        : json(
            { cloudCommand: true, state: "queued", cloudCommandId: "fixture" },
            202,
          );
    return json({
      cloudCommandId: "fixture",
      state: "completed",
      result: {
        kind: "http",
        httpStatus: 200,
        bodyBase64: Buffer.from(
          JSON.stringify({ message: "模拟业务回执" }),
        ).toString("base64"),
      },
    });
  });
  const reader = new ReadClient(network);
  reader.mode = mode;
  vi.spyOn(reader, "wait").mockResolvedValue();
  const snapshot = {
    mode,
    status: { executorAvailable: true, homeReady: true },
    dashboard: {
      templates: {
        items: [
          {
            id: "fixture-template",
            project: "模拟项目",
            material: "模拟材料",
            materials: ["模拟材料", "另一个材料"],
            expectedCount: 3,
          },
        ],
      },
      receiverQueue: { items: [task] },
      projectGaps: { items: [task] },
    },
  } as unknown as Snapshot;
  const refresh = vi.fn(),
    onReplenishment = vi.fn();
  render(
    <TaskOperations
      snapshot={snapshot}
      reader={reader}
      refresh={refresh}
      replenishment={replenishment}
      onReplenishment={onReplenishment}
    />,
  );
  return { network, reader, refresh, onReplenishment };
}
describe("task writes with synthetic home/cloud transports", () => {
  for (const mode of ["home", "cloud"] as const) {
    it(`${mode}: create exact body and keep form on error until HTTP receipt`, async () => {
      const { network } = setup(mode);
      fireEvent.click(screen.getByRole("button", { name: "新建项目任务" }));
      fireEvent.change(screen.getByLabelText("项目"), {
        target: { value: "fixture-template" },
      });
      fireEvent.change(screen.getByLabelText("日期"), {
        target: { value: " 10.19 " },
      });
      fireEvent.change(screen.getByLabelText("音频批次"), {
        target: { value: " custom " },
      });
      fireEvent.change(screen.getByLabelText("语音策略"), {
        target: { value: "reuse_existing" },
      });
      fireEvent.change(screen.getByLabelText("视频链接（每行一条）"), {
        target: {
          value: "https://example.invalid/a\nhttps://example.invalid/b",
        },
      });
      fireEvent.click(screen.getByLabelText("提交并启动首项"));
      const button = screen.getByRole("button", { name: "提交任务" });
      fireEvent.click(button);
      fireEvent.click(button);
      await waitFor(() =>
        expect(
          network.mock.calls.filter((call) => call[1]?.method === "POST"),
        ).toHaveLength(1),
      );
      const [url, init] = network.mock.calls.find(
        (call) => call[1]?.method === "POST",
      )!;
      expect(url).toBe("/api/controls/tasks/create");
      expect(JSON.parse(init.body)).toEqual({
        date: "10.19",
        templateId: "fixture-template",
        material: "模拟材料",
        audioBatch: "custom",
        voicePlan: "reuse_existing",
        expectedCount: "3",
        urls: "https://example.invalid/a\nhttps://example.invalid/b",
        startNow: true,
      });
      await screen.findByText("模拟业务回执");
      if (mode === "cloud") expect(init.headers["X-CSRF-Token"]).toBe("mock");
    });
    it(`${mode}: replenish keeps the raw URLs and defaults startNow=true`, async () => {
      const { network, onReplenishment } = setup(mode, task);
      fireEvent.change(screen.getByLabelText("新链接（每行一条）"), {
        target: { value: " https://example.invalid/new " },
      });
      fireEvent.click(screen.getByRole("button", { name: "提交补链" }));
      await screen.findByText("模拟业务回执");
      const [url, init] = network.mock.calls.find(
        (call) => call[1]?.method === "POST",
      )!;
      expect(url).toBe("/api/controls/tasks/fixture%2Ftask/replenish");
      expect(JSON.parse(init.body)).toEqual({
        urls: " https://example.invalid/new ",
        startNow: true,
      });
      expect(onReplenishment).toHaveBeenCalledWith(null);
    });
    for (const action of ["start", "cancel"] as const)
      it(`${mode}: ${action} uses original confirmation; cancel confirmation sends zero`, async () => {
        const { network } = setup(mode);
        const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
        fireEvent.click(
          screen.getByRole("button", {
            name: action === "start" ? "启动首项" : "撤回",
          }),
        );
        expect(network).not.toHaveBeenCalled();
        confirm.mockReturnValue(true);
        fireEvent.click(
          screen.getByRole("button", {
            name: action === "start" ? "启动首项" : "撤回",
          }),
        );
        await screen.findByText("模拟业务回执");
        const [url, init] = network.mock.calls.find(
          (call) => call[1]?.method === "POST",
        )!;
        expect(url).toBe("/api/controls/tasks/fixture%2Ftask/" + action);
        if (mode === "home") expect(init).toEqual({ method: "POST" });
        else expect(JSON.parse(init.body)).toEqual({});
        expect(confirm.mock.calls[0][0]).toContain(
          action === "start"
            ? "确认启动这个批次的首项"
            : "确认撤回这个尚未开始的任务",
        );
      });
  }
  it("failed create preserves inputs and enables retry; unready cloud remains disabled", async () => {
    const { network } = setup("home");
    network.mockResolvedValue(json({ detail: "模拟拒绝" }, 409));
    fireEvent.click(screen.getByRole("button", { name: "新建项目任务" }));
    fireEvent.change(screen.getByLabelText("项目"), {
      target: { value: "fixture-template" },
    });
    const input = screen.getByLabelText("视频链接（每行一条）");
    fireEvent.change(input, {
      target: { value: "https://example.invalid/keep" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交任务" }));
    await screen.findByText("模拟拒绝");
    expect(input).toHaveValue("https://example.invalid/keep");
    expect(screen.getByRole("button", { name: "提交任务" })).not.toBeDisabled();
  });
  it("invalid mode/blocked cloud send no task command", async () => {
    const network = vi.fn(),
      reader = new ReadClient(network);
    reader.mode = "cloud";
    await expect(
      new UploadWriter(reader, () => ({ commandBlocker: "fixture" })).post(
        "/api/controls/tasks/create",
        { urls: "fixture" },
      ),
    ).rejects.toThrow("未就绪");
    expect(network).not.toHaveBeenCalled();
  });
});
