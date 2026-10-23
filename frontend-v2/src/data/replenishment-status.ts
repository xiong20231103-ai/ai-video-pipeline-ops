import type { Row } from "./types";
export function replenishmentQueueStatus(gap: Row, queue: Row[]) {
  const missing = Math.max(0, Number(gap.missingCount ?? (Number(gap.expectedCount || 0) - Number(gap.completed || 0))) || 0);
  const seen = new Set<string>();
  let count = 0;
  let manual = false;
  for (const child of Array.isArray(queue) ? queue : []) {
    const id = String(child.taskId || "");
    if (!id || seen.has(id) || !gap.taskId || child.replenishForTaskId !== gap.taskId || child.canonicalTaskId !== gap.taskId) continue;
    if (String(child.date || child.productionDate || "") !== String(gap.date || gap.productionDate || "")) continue;
    if (child.project !== gap.project || child.material !== gap.material || child.status !== "pending_confirmation") continue;
    seen.add(id);
    const urls = Array.isArray(child.urls) ? new Set((child.urls as unknown[]).filter(url => typeof url === "string" && url.trim())) : new Set();
    if (!urls.size) continue;
    count += urls.size;
    if (!["auto_start_first", "auto_start_sequential"].includes(String(child.startMode || ""))) manual = true;
  }
  const queued = Math.min(missing, count);
  const remaining = Math.max(0, missing - queued);
  const message = queued ? `补链已收到 ${queued} 条，${manual ? "等待确认启动" : "排队中"}；素材仍缺 ${missing} 条${remaining ? `，另有 ${remaining} 条尚未补交` : "，请勿重复补交"}` : "";
  return { queued, remaining, message };
}
