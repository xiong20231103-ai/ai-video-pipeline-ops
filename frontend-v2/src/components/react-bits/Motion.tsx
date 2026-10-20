import { useEffect, useLayoutEffect, useRef, type ReactNode } from "react";

// Native-API adaptations of React Bits' BlurText/FadeContent/CountUp behavior.
// Upstream references and differences are recorded in docs/v2/V2-3_POLISH.md.
const played = new Set<string>();
const reduced = () =>
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
function once(
  node: HTMLElement,
  key: string,
  keyframes: Keyframe[],
  duration: number,
) {
  if (played.has(key) || reduced() || typeof node.animate !== "function")
    return;
  const animation = node.animate(keyframes, {
    duration,
    easing: "cubic-bezier(.22,1,.36,1)",
  });
  animation.onfinish = () => {
    played.add(key);
  };
  return () => {
    animation.onfinish = null;
    animation.cancel();
  };
}
export function BlurText({ text }: { text: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(
    () =>
      ref.current
        ? once(
            ref.current,
            "heading:" + text,
            [
              { filter: "blur(8px)", opacity: 0, transform: "translateY(8px)" },
              { filter: "blur(0px)", opacity: 1, transform: "translateY(0)" },
            ],
            450,
          )
        : undefined,
    [text],
  );
  return (
    <span ref={ref} className="bits-blur-text">
      {text}
    </span>
  );
}
export function FadeContent({
  id,
  children,
  className = "",
  ...props
}: {
  id: string;
  children: ReactNode;
  className?: string;
  "data-panel"?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node || played.has("panel:" + id) || reduced()) return;
    let stop: (() => void) | undefined;
    if (typeof IntersectionObserver === "undefined") {
      stop = once(
        node,
        "panel:" + id,
        [
          { opacity: 0, transform: "translateY(10px)" },
          { opacity: 1, transform: "translateY(0)" },
        ],
        320,
      );
      return () => stop?.();
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((x) => x.isIntersecting)) {
          observer.disconnect();
          stop = once(
            node,
            "panel:" + id,
            [
              { opacity: 0, transform: "translateY(10px)" },
              { opacity: 1, transform: "translateY(0)" },
            ],
            320,
          );
        }
      },
      { threshold: 0.08 },
    );
    observer.observe(node);
    return () => {
      observer.disconnect();
      stop?.();
    };
  }, [id]);
  return (
    <div ref={ref} className={className} {...props}>
      {children}
    </div>
  );
}
export function CountUp({ value }: { value: string }) {
  const ref = useRef<HTMLSpanElement>(null),
    previous = useRef<string | null>(null);
  useLayoutEffect(() => {
    const node = ref.current,
      old = previous.current;
    previous.current = value;
    if (!node || old === value) return;
    node.textContent = value;
    const match = /^(-?\d+(?:\.\d+)?)(.*)$/.exec(value),
      from = old === null ? 0 : Number.parseFloat(old);
    if (
      reduced() ||
      !match ||
      !Number.isFinite(from) ||
      typeof requestAnimationFrame !== "function"
    )
      return;
    const to = Number(match[1]),
      decimals = (match[1].split(".")[1] || "").length,
      suffix = match[2],
      start = performance.now();
    let frame = 0;
    const step = (at: number) => {
      const t = Math.min(1, Math.max(0, (at - start) / 450)),
        ease = 1 - Math.pow(1 - t, 3);
      node.textContent =
        t === 1
          ? value
          : (from + (to - from) * ease).toFixed(decimals) + suffix;
      if (t < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value]);
  return (
    <span aria-hidden="true" ref={ref}>
      {value}
    </span>
  );
}
