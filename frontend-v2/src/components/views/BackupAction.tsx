import { useFeedback } from "@/data/use-feedback";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { consoleAdminFor } from "@/data/console-admin";
import type { ReadClient } from "@/data/client";
export default function BackupAction({
  reader,
  packageId,
}: {
  reader: ReadClient | null;
  packageId?: string;
}) {
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    lock = useRef(false);
  useFeedback(message);
  async function run() {
    if (!reader || lock.current) return;
    lock.current = true;
    setBusy(true);
    setMessage("");
    try {
      const value = await consoleAdminFor(reader).cloudPost(
        packageId
          ? "/console/backups/" + encodeURIComponent(packageId) + "/verify"
          : "/console/backups/request",
      );
      setMessage(
        packageId
          ? (value.verified ? "校验通过：" : "校验失败：") + packageId
          : "请求已排队；代理配置就绪后执行。稍后刷新列表查看。",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "请求失败");
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return (
    <div>
      <Button
        variant="outline"
        disabled={!reader || busy}
        onClick={() => void run()}
      >
        {busy ? "正在处理…" : packageId ? "校验云端文件" : "请求一次备份"}
      </Button>
      {message && <p role="status">{message}</p>}
    </div>
  );
}
