import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { commandAdminFor } from "@/data/command-admin";
import { pendingStates } from "@/data/receipts";
import type { ReadClient } from "@/data/client";
import type { Row } from "@/data/types";
export function CommandActions({
  row,
  reader,
  refresh,
}: {
  row: Row;
  reader: ReadClient | null;
  refresh: () => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    lock = useRef(false);
  async function act(action: "cancel" | "resolve" | "finish") {
    if (!reader || lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      await commandAdminFor(reader)[action](row);
      refresh();
    } catch (error) {
      setError(error instanceof Error ? error.message : "操作失败");
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return (
    <div className="data-actions">
      {["submitting", "queued", "leased"].includes(String(row.state)) && (
        <Button
          variant="outline"
          disabled={!reader || busy}
          onClick={() => void act("cancel")}
        >
          撤销发送前命令
        </Button>
      )}
      {row.state === "unknown" && (
        <Button
          variant="outline"
          disabled={!reader || busy}
          onClick={() => void act("resolve")}
        >
          人工对账后解除阻塞
        </Button>
      )}
      {!row.remote && !pendingStates.has(String(row.state)) && (
        <Button
          variant="outline"
          disabled={!reader || busy}
          onClick={() => void act("finish")}
        >
          结束本次回执，允许新操作
        </Button>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
export function SubmissionCancellation({
  reader,
  refresh,
}: {
  reader: ReadClient | null;
  refresh: () => void;
}) {
  const [id, setId] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    lock = useRef(false);
  return (
    <form
      className="data-actions"
      onSubmit={(event) => {
        event.preventDefault();
        if (!reader || lock.current) return;
        lock.current = true;
        setBusy(true);
        setMessage("");
        void commandAdminFor(reader)
          .cancelSubmission(id)
          .then(() => {
            setMessage(
              "发送前撤销已记录；晚到收件也会被拒绝。请让递交器重新查询。",
            );
            refresh();
          })
          .catch((error) =>
            setMessage(error instanceof Error ? error.message : "撤销失败"),
          )
          .finally(() => {
            lock.current = false;
            setBusy(false);
          });
      }}
    >
      <Input
        aria-label="递交器原请求ID"
        placeholder="递交器原请求ID（仅用于收件回包丢失）"
        required
        value={id}
        onChange={(event) => setId(event.target.value)}
      />
      <Button disabled={!reader || busy} type="submit">
        撤销该递交器请求（仅发送前）
      </Button>
      {message && <p role="status">{message}</p>}
    </form>
  );
}
