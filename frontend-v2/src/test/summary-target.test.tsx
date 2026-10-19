import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";
import { useDashboard } from "@/data/useDashboard";
import { expectedContinueTarget } from "@/data/safe-continue";
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
  localStorage.clear();
});
for (const mode of ["home", "cloud"] as const)
  it(
    mode +
      " summary advances and clears expectedTarget with the displayed current task box",
    async () => {
      vi.useFakeTimers();
      let summary = 0;
      vi.spyOn(window, "fetch").mockImplementation(async (url, init) => {
        expect(!init?.method || init.method === "GET").toBe(true);
        const path = String(url);
        if (path === "/auth/options")
          return mode === "home"
            ? json({}, 404)
            : json({ registrationOpen: false });
        if (path === "/api/dashboard")
          return json({
            selectedDate: "10.19",
            currentTaskBox: {
              batchId: "old-batch",
              current: { taskId: "old-task", attemptId: "old-attempt" },
            },
            controls: { continue: { state: "idle", allowed: false } },
          });
        if (path === "/api/dashboard/summary") {
          summary++;
          return json({
            currentTaskBox:
              summary === 1
                ? {
                    batchId: "new-batch",
                    current: { taskId: "new-task", attemptId: "new-attempt" },
                  }
                : null,
            controls: { continue: { state: "idle", allowed: false } },
          });
        }
        if (path === "/console/commands") return json({ items: [] });
        return json({});
      });
      const hook = renderHook(() => useDashboard("", ""));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(
        expectedContinueTarget(hook.result.current.snapshot.dashboard || {}),
      ).toEqual({
        batchId: "old-batch",
        taskId: "old-task",
        attemptId: "old-attempt",
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);
      });
      const current = hook.result.current.snapshot.dashboard || {};
      expect(expectedContinueTarget(current)).toEqual({
        batchId: "new-batch",
        taskId: "new-task",
        attemptId: "new-attempt",
      });
      expect((current.taskBoxes as { selected: unknown }).selected).toEqual(
        current.currentTaskBox,
      );
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);
      });
      expect(
        expectedContinueTarget(hook.result.current.snapshot.dashboard || {}),
      ).toEqual({});
      expect(
        (
          hook.result.current.snapshot.dashboard?.taskBoxes as {
            selected: unknown;
          }
        ).selected,
      ).toBeNull();
      hook.unmount();
    },
  );
