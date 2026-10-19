import { beforeEach, expect, it } from "vitest";
import { mergePolledReceipts, saveReceipts } from "@/data/receipts";
const row = {
  requestId: "fixture",
  fingerprint: "fixture",
  path: "/api/controls/cloud-cleanup/preview",
  state: "submitting",
};
beforeEach(() => localStorage.clear());
it("async poll cannot erase a concurrently completed or newly-created queue receipt", () => {
  const completed = { ...row, state: "completed", cloudCommandId: "server" };
  const fresh = { ...row, requestId: "new" };
  saveReceipts([completed, fresh]);
  expect(mergePolledReceipts([row], [row])).toEqual([completed, fresh]);
});
it("async preview poll cannot resurrect an intentionally discarded terminal ticket receipt", () => {
  expect(
    mergePolledReceipts(
      [{ ...row, state: "completed" }],
      [{ ...row, state: "completed" }],
    ),
  ).toEqual([]);
});
it("poll updates original unchanged receipt normally", () => {
  saveReceipts([row]);
  expect(mergePolledReceipts([row], [{ ...row, state: "completed" }])).toEqual([
    { ...row, state: "completed" },
  ]);
});
it("stale unknown poll cannot overwrite a newer manual reconciliation", () => {
  const unknown = { ...row, state: "unknown" };
  saveReceipts([{ ...unknown, state: "resolved_unknown" }]);
  expect(mergePolledReceipts([unknown], [unknown])[0].state).toBe(
    "resolved_unknown",
  );
});
