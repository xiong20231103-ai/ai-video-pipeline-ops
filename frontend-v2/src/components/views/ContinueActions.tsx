import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { safeContinueFor } from "@/data/safe-continue";
import { object, type Row, type Snapshot } from "@/data/types";
import type { ReadClient } from "@/data/client";

export default function ContinueActions({
  snapshot,
  reader,
  onResult,
  refresh,
}: {
  snapshot: Snapshot;
  reader: ReadClient | null;
  onResult: (value: Row) => void;
  refresh: () => void;
}) {
  const [, tick] = useState(0),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    const timer = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  const controller = reader ? safeContinueFor(reader) : null,
    state = controller?.state(object(snapshot.dashboard), snapshot.status);
  async function submit() {
    if (!controller || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await controller.submit(
        object(snapshot.dashboard),
        snapshot.status,
      );
      if (result) {
        onResult(result);
        refresh();
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : "发送继续指令失败");
      onResult({
        state: "failed",
        allowed: false,
        message: error instanceof Error ? error.message : "发送继续指令失败",
      });
    } finally {
      setBusy(false);
    }
  }
  async function query() {
    if (!controller || !reader || busy) return;
    const target = controller.target();
    if (!target) {
      setError("原云端命令尚待回执；只按原编号查询，不会重发");
      return;
    }
    setBusy(true);
    setError("");
    try {
      onResult(
        controller.observe(await reader.read(target, 0), snapshot.status, true),
      );
    } catch (error) {
      controller.failed();
      setError(error instanceof Error ? error.message : "无法读取安全继续状态");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Button
        disabled={busy || !state?.clickable}
        title={state?.title}
        data-allowed={state?.clickable ? "true" : "false"}
        onClick={() => void submit()}
      >
        {busy ? "正在处理…" : state?.label || "安全继续当前项目"}
      </Button>
      <Button
        variant="outline"
        disabled={busy || !reader}
        onClick={() => void query()}
      >
        按原命令编号查询与对账
      </Button>
      {error && <p role="alert">{error}</p>}
    </>
  );
}
