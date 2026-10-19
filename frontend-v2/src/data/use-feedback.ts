import { useEffect, useRef } from "react";
export function useFeedback(message: string) {
  const last = useRef(message);
  useEffect(() => {
    if (message && message !== last.current)
      window.dispatchEvent(
        new CustomEvent("ops-v2-feedback", { detail: { message } }),
      );
    last.current = message;
  }, [message]);
}
