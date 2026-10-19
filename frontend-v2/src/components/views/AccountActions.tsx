import { useFeedback } from "@/data/use-feedback";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { consoleAdminFor } from "@/data/console-admin";
import type { ReadClient } from "@/data/client";
export default function AccountActions({
  reader,
}: {
  reader: ReadClient | null;
}) {
  const [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    formRef = useRef<HTMLFormElement>(null),
    lock = useRef(false);
  useFeedback(message);
  async function logout() {
    if (!reader || lock.current) return;
    lock.current = true;
    setBusy(true);
    try {
      await consoleAdminFor(reader).cloudPost("/auth/logout");
    } catch {
      setMessage("退出失败，请重试");
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return (
    <section aria-label="账号管理">
      <div className="data-actions">
        <Button
          variant="outline"
          disabled={!reader || busy}
          onClick={() => setOpen(true)}
        >
          修改密码
        </Button>
        <Button
          variant="outline"
          disabled={!reader || busy}
          onClick={() => void logout()}
        >
          退出登录
        </Button>
        <a href="/login">登录与注册</a>
      </div>
      {open && (
        <form
          ref={formRef}
          className="manager-filters"
          onSubmit={(event) => {
            event.preventDefault();
            if (!reader || lock.current) return;
            const form = event.currentTarget,
              values = Object.fromEntries(new FormData(form));
            lock.current = true;
            setBusy(true);
            setMessage("");
            void consoleAdminFor(reader)
              .cloudPost("/auth/password", values)
              .then(() => form.reset())
              .catch(() => setMessage("未修改，请核对密码后重试"))
              .finally(() => {
                lock.current = false;
                setBusy(false);
              });
          }}
        >
          <label>
            当前密码
            <Input
              name="oldPassword"
              type="password"
              autoComplete="current-password"
              maxLength={256}
              required
              disabled={busy}
            />
          </label>
          <label>
            新密码（至少12个字符）
            <Input
              name="newPassword"
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={256}
              required
              disabled={busy}
            />
          </label>
          <Button type="submit" disabled={!reader || busy}>
            保存新密码
          </Button>
        </form>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
