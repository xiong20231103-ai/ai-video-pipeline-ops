import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
export function ToastHost() {
  const [toast, setToast] = useState<{ message: string; id: number } | null>(
    null,
  );
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let id = 0;
    const show = (event: Event) => {
      const message = (event as CustomEvent<{ message?: unknown }>).detail
        ?.message;
      if (typeof message !== "string" || !message) return;
      clearTimeout(timer);
      setToast({ message, id: ++id });
      timer = setTimeout(() => setToast(null), 5000);
    };
    window.addEventListener("ops-v2-feedback", show);
    return () => {
      window.removeEventListener("ops-v2-feedback", show);
      clearTimeout(timer);
    };
  }, []);
  return (
    <aside className="v2-toast-region" aria-live="polite" aria-atomic="true">
      {toast && (
        <div className="v2-toast" role="status" key={toast.id}>
          <p>{toast.message}</p>
          <Button
            variant="ghost"
            size="sm"
            aria-label="关闭提示"
            onClick={() => setToast(null)}
          >
            关闭
          </Button>
        </div>
      )}
    </aside>
  );
}
