import { useRef, useState } from "react";
import { formatDateTime } from "@/data/legacy-formatters";
import { Button } from "@/components/ui/button";
import { UploadWriter, uploadWriterFor } from "@/data/upload-writer";
import type { ReadClient } from "@/data/client";
import { object, text, type Row, type Snapshot } from "@/data/types";
import { localReceipts, pendingStates, saveReceipts } from "@/data/receipts";

const uploadConfirmations = {
  rescan:
    "确认重新对账正式清单，补传遗漏成片，并对云端已实时核验的任务继续安全清理吗？不会重新剪辑等待中的任务，也不会清理配音、公共素材、Logo或公共样品。",
  "verify-history":
    "确认核验历史百度云文件吗？系统只会查询云端文件是否存在，并核对云端路径和文件大小；不会补传、不会删除本地或云端文件，也不会改变项目完成状态。",
};
export function UploadActions({
  snapshot,
  reader,
  refresh,
}: {
  snapshot: Snapshot;
  reader: ReadClient | null;
  refresh: () => void;
}) {
  const [busy, setBusy] = useState(""),
    [result, setResult] = useState<Row | null>(null);
  const inFlight = useRef(false);
  const sourceHistory = object(
    object(snapshot.dashboard?.controls).historicalCloudVerification,
  );
  const [historyReply, setHistoryReply] = useState<{
    source: Row;
    value: Row;
  } | null>(null);
  const history =
    historyReply?.source === sourceHistory ? historyReply.value : sourceHistory;
  const health = useRef(snapshot.status);
  health.current = snapshot.status;
  const writer = useRef<UploadWriter | null>(null);
  if (reader && writer.current?.reader !== reader)
    writer.current = uploadWriterFor(reader, () => health.current);
  async function run(action: keyof typeof uploadConfirmations) {
    if (inFlight.current || !writer.current?.available()) return;
    if (!window.confirm(uploadConfirmations[action])) return;
    inFlight.current = true;
    setBusy(action);
    try {
      const answer = await writer.current.post(
        "/api/controls/upload/" + action,
        {},
      );
      if (action === "verify-history")
        setHistoryReply({ source: sourceHistory, value: answer });
      setResult(
        action === "rescan"
          ? {
              ...answer,
              updatedAt: new Date().toISOString(),
              state:
                snapshot.mode === "cloud"
                  ? answer.state || "requested"
                  : "completed",
              message:
                answer.message ||
                (snapshot.mode === "cloud"
                  ? "家里已接收上传检查请求，请查看实际上传状态"
                  : "上传检查已完成"),
            }
          : {
              ...answer,
              message: `${text(answer.message, "尚未核验历史百度云文件")}${Number(answer.total ?? answer.eligible ?? 0) ? ` · ${Number(answer.processed || 0)}/${Number(answer.total ?? answer.eligible)}，通过 ${Number(answer.verified || 0)}，失败 ${Number(answer.failed || 0)}` : ""}`,
            },
      );
      refresh();
    } catch (error) {
      if (action === "verify-history")
        setHistoryReply({ source: sourceHistory, value: { state: "failed" } });
      setResult({
        state: "failed",
        updatedAt: new Date().toISOString(),
        message:
          error instanceof Error
            ? error.message
            : action === "rescan"
              ? "上传检查失败"
              : "历史百度云核验提交失败",
      });
    } finally {
      inFlight.current = false;
      setBusy("");
    }
  }
  const available = Boolean(writer.current?.available());
  const receipts =
    snapshot.mode === "cloud"
      ? localReceipts().filter(
          (row) =>
            String(row.path).startsWith("/api/controls/upload/") &&
            !pendingStates.has(String(row.state)),
        )
      : [];
  return (
    <>
      <div className="data-actions">
        <Button
          data-v2-upload="rescan"
          disabled={!available || !!busy}
          onClick={() => void run("rescan")}
        >
          {busy === "rescan" ? "正在检查上传缺口…" : "重新对账、补传并清理"}
        </Button>
        <Button
          data-v2-upload="verify-history"
          variant="outline"
          disabled={
            !available ||
            !!busy ||
            ["requested", "running"].includes(String(history.state))
          }
          onClick={() => void run("verify-history")}
        >
          {busy === "verify-history"
            ? "正在提交历史核验…"
            : ["requested", "running"].includes(String(history.state))
              ? `正在核验历史云端文件 ${Number(history.processed || 0)}/${Number(history.total || history.eligible || 0) || "…"}`
              : "核验历史云端文件"}
        </Button>
      </div>
      {result && (
        <p role="status">
          {(
            {
              completed: "已完成",
              requested: "已请求",
              failed: "失败",
              running: "执行中",
            } as Record<string, string>
          )[String(result.state)] || text(result.state)}{" "}
          · {text(result.message)}
          {result.updatedAt ? ` · ${formatDateTime(result.updatedAt)}` : ""}
        </p>
      )}
      {snapshot.mode === "cloud" && (
        <p>云端排队与 HTTP 回执请看“安全继续与命令”；结果不明不会重发。</p>
      )}
      {receipts.map((row) => (
        <Button
          variant="outline"
          key={String(row.requestId)}
          onClick={() => {
            if (
              !window.confirm(
                "结束本次回执后，相同输入的下一次点击将创建新命令。确认？",
              )
            )
              return;
            saveReceipts(
              localReceipts().filter(
                (item) => item.requestId !== row.requestId,
              ),
            );
            setResult(null);
            refresh();
          }}
        >
          结束本次回执，允许新操作 · {text(row.cloudCommandId || row.requestId)}
        </Button>
      ))}
    </>
  );
}
