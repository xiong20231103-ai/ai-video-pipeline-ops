import { replenishmentQueueStatus } from "@/data/replenishment-status";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Panel } from "./shared";
import { GapsAndQueue } from "./TaskViews";
import { uploadWriterFor } from "@/data/upload-writer";
import type { ReadClient } from "@/data/client";
import {
  object,
  list,
  text,
  number,
  strings,
  type Row,
  type Snapshot,
} from "@/data/types";

const currentDate = () => {
  const date = new Date();
  return `${date.getMonth() + 1}.${date.getDate()}`;
};
export default function TaskOperations({
  snapshot,
  reader,
  refresh,
  replenishment,
  onReplenishment,
}: {
  snapshot: Snapshot;
  reader: ReadClient | null;
  refresh: () => void;
  replenishment: Row | null;
  onReplenishment: (row: Row | null) => void;
}) {
  const [createOpen, setCreateOpen] = useState(false),
    [templateId, setTemplate] = useState(""),
    [count, setCount] = useState(""),
    [result, setResult] = useState(""),
    [busy, setBusy] = useState("");
  const inFlight = useRef(false),
    health = useRef(snapshot.status);
  health.current = snapshot.status;
  const writer = reader ? uploadWriterFor(reader, () => health.current) : null;
  const available = Boolean(writer?.available()) && !busy;
  const data = object(snapshot.dashboard),
    templates = list(object(data.templates).items),
    template = templates.find((row) => String(row.id) === templateId);
  const signature = JSON.stringify(templates);
  const [seenSignature, setSeenSignature] = useState(signature);
  if (seenSignature !== signature) {
    setSeenSignature(signature);
    if (templateId && !template) setTemplate("");
    if (template?.expectedCount) setCount(String(template.expectedCount));
  }
  const materials = strings(template?.materials).length
    ? strings(template?.materials)
    : template?.material
      ? [String(template.material)]
      : [];
  async function submit(
    path: string,
    body: Row | null,
    fallback: string,
    onSuccess?: () => void,
  ) {
    if (inFlight.current || !writer?.available()) return;
    inFlight.current = true;
    setBusy(path);
    try {
      const answer = await writer.post(path, body);
      setResult(text(answer.message, fallback));
      onSuccess?.();
      refresh();
    } catch (error) {
      setResult(error instanceof Error ? error.message : "操作失败");
    } finally {
      inFlight.current = false;
      setBusy("");
    }
  }
  function control(item: Row, action: "start" | "cancel") {
    if (!item.taskId || !available) return;
    if (
      action === "start" &&
      (item.status !== "pending_confirmation" ||
        ["auto_start_first", "auto_start_sequential"].includes(
          String(item.startMode),
        ))
    )
      return;
    if (
      action === "cancel" &&
      !["pending_confirmation", "imported_waiting_start"].includes(
        String(item.status),
      )
    )
      return;
    if (
      !window.confirm(
        action === "start"
          ? "确认启动这个批次的首项吗？工作台会继续按原有顺序处理。"
          : "确认撤回这个尚未开始的任务吗？不会删除任何视频、音频或素材。",
      )
    )
      return;
    void submit(
      `/api/controls/tasks/${encodeURIComponent(String(item.taskId))}/${action}`,
      null,
      action === "start" ? "启动命令已发送" : "撤回命令已发送",
    );
  }
  const missing = replenishment
    ? number(
        replenishment.missingCount ??
          Math.max(
            0,
            number(replenishment.expectedCount) -
              number(replenishment.completed),
          ),
      )
    : 0;
  return (
    <>
      <GapsAndQueue
        data={data}
        actions={{
          available,
          control,
          replenish: (row) => {
            const queued = replenishmentQueueStatus(row, data.receiverQueue && !(data.receiverQueue as Record<string, unknown>).error ? ((data.receiverQueue as Record<string, unknown>).items as Row[] || []) : []);
            if (queued.queued) { setResult(queued.message); return; }
            onReplenishment(row);
          },
          create: () => setCreateOpen(true),
        }}
      />
      {result && <p role="status">{result}</p>}
      <Sheet open={createOpen} onOpenChange={setCreateOpen}>
        <SheetContent className="task-operation-sheet">
          <SheetHeader>
            <SheetTitle>新建项目任务</SheetTitle>
          </SheetHeader>
          <form
            className="data-form"
            onSubmit={(event) => {
              event.preventDefault();
              if (!available) return;
              const form = event.currentTarget,
                fields = new FormData(form);
              void submit(
                "/api/controls/tasks/create",
                {
                  date: String(fields.get("date") || "").trim(),
                  templateId,
                  material: String(fields.get("material") || ""),
                  audioBatch: String(fields.get("audioBatch") || "").trim(),
                  voicePlan: String(fields.get("voicePlan") || ""),
                  expectedCount: count,
                  urls: String(fields.get("urls") || ""),
                  startNow: fields.get("startNow") === "on",
                },
                "任务已提交",
                () => {
                  form.reset();
                  setTemplate("");
                  setCount("");
                  setCreateOpen(false);
                },
              );
            }}
          >
            <label>
              日期
              <Input name="date" defaultValue={currentDate()} required />
            </label>
            <label>
              项目
              <select
                aria-label="项目"
                name="templateId"
                required
                value={templateId}
                onChange={(event) => {
                  const id = event.target.value;
                  setTemplate(id);
                  const selected = templates.find(
                    (row) => String(row.id) === id,
                  );
                  if (selected?.expectedCount)
                    setCount(String(selected.expectedCount));
                }}
              >
                <option value="">请选择项目</option>
                {templates.map((row) => (
                  <option key={String(row.id)} value={String(row.id)}>
                    {text(row.label, `${row.project} / ${row.material}`)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              材料
              <select
                aria-label="材料"
                name="material"
                key={templateId + signature}
              >
                {materials.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <label>
              音频批次
              <Input name="audioBatch" placeholder="默认使用日期" />
            </label>
            <label>
              语音策略
              <select aria-label="语音策略" name="voicePlan">
                <option value="">按项目默认</option>
                <option value="reuse_existing">复用已有语音</option>
                <option value="create_new">新建语音</option>
              </select>
            </label>
            <label>
              计划视频数
              <Input
                name="expectedCount"
                type="number"
                min="1"
                value={count}
                onChange={(event) => setCount(event.target.value)}
              />
            </label>
            <label>
              视频链接（每行一条）
              <textarea name="urls" rows={4} required />
            </label>
            <label className="checkbox-label">
              <input type="checkbox" name="startNow" />
              提交并启动首项
            </label>
            <Button type="submit" disabled={!available}>
              {busy ? "正在提交…" : "提交任务"}
            </Button>
          </form>
        </SheetContent>
      </Sheet>
      <Sheet
        open={Boolean(replenishment)}
        onOpenChange={(open) => {
          if (!open) onReplenishment(null);
        }}
      >
        <SheetContent className="task-operation-sheet">
          <SheetHeader>
            <SheetTitle>
              补链：{text(replenishment?.project)} /{" "}
              {text(replenishment?.material)}
            </SheetTitle>
          </SheetHeader>
          <Panel title="当前缺口">
            <p>
              原计划 {number(replenishment?.expectedCount)} 条，已完成{" "}
              {number(replenishment?.completed)} 条；请只粘贴 {missing}{" "}
              条新链接。
            </p>
          </Panel>
          <form
            key={String(replenishment?.taskId)}
            className="data-form"
            onSubmit={(event) => {
              event.preventDefault();
              if (!available || !replenishment?.taskId) return;
              const fields = new FormData(event.currentTarget);
              void submit(
                `/api/controls/tasks/${encodeURIComponent(String(replenishment.taskId))}/replenish`,
                {
                  urls: String(fields.get("urls") || ""),
                  startNow: fields.get("startNow") === "on",
                },
                "补链任务已提交",
                () => onReplenishment(null),
              );
            }}
          >
            <label>
              新链接（每行一条）
              <textarea name="urls" rows={4} required />
            </label>
            <label className="checkbox-label">
              <input type="checkbox" name="startNow" defaultChecked />
              补链后继续当前项目
            </label>
            <Button type="submit" disabled={!available}>
              {busy ? "正在提交…" : "提交补链"}
            </Button>
          </form>
        </SheetContent>
      </Sheet>
    </>
  );
}
