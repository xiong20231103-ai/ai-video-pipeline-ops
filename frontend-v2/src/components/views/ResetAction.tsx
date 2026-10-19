import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type { ReadClient } from "@/data/client";
import { consoleAdminFor } from "@/data/console-admin";
import { text, type Row } from "@/data/types";
export default function ResetAction({
  reader,
  onReset,
  initialResult = {},
}: {
  initialResult?: Row;
  reader: ReadClient | null;
  onReset: () => void;
}) {
  const [busy, setBusy] = useState(false),
    [result, setResult] = useState<Row | null>(null),
    lock = useRef(false);
  async function reset() {
    if (!reader || reader.mode !== "home" || lock.current) return;
    lock.current = true;
    setBusy(true);
    try {
      const value = await consoleAdminFor(reader).reset();
      if (value) {
        setResult({
          state: "completed",
          message: value.message || "测试记录已重置",
          updatedAt: value.resetAt || new Date().toISOString(),
        });
        onReset();
      }
    } catch (error) {
      setResult({
        state: "failed",
        message: error instanceof Error ? error.message : "测试记录重置失败",
        updatedAt: new Date().toISOString(),
      });
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return (
    <div>
      <Button
        variant="outline"
        disabled={!reader || reader.mode !== "home" || busy}
        onClick={() => void reset()}
      >
        {busy ? "正在备份并重置…" : "重置全部测试记录"}
      </Button>
      {result || initialResult.message ? (
        <p role="status">
          {text((result || initialResult).state)} ·{" "}
          {text((result || initialResult).message)} ·{" "}
          {text((result || initialResult).updatedAt)}
        </p>
      ) : (
        <p>尚未重置测试记录</p>
      )}
    </div>
  );
}
