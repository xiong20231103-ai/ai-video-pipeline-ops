import { loginDestination } from "@/lib/entry";
import { object, type Mode, type Row, type Sample } from "./types";

export class ReadClient {
  readonly samples = new Map<string, Sample>();
  private inflight = new Map<string, Promise<Row>>();
  private validators = new Map<string, { etag: string; body: Row }>();
  private watchers = new Map<string, Promise<void>>();
  readonly controller = new AbortController();
  mode: Mode | null = null;
  onSource?: () => void;
  onRefresh?: () => void;
  constructor(
    readonly network: typeof fetch = window.fetch.bind(window),
    readonly redirect = () => window.location.assign(loginDestination()),
  ) {}
  async detect(): Promise<Mode> {
    if (window.location.hostname === "100.92.17.9") return (this.mode = "home");
    const response = await this.request("/auth/options");
    if (
      response.ok &&
      typeof object(await response.json()).registrationOpen === "boolean"
    )
      return (this.mode = "cloud");
    if (
      response.status === 404 &&
      ["100.92.17.9", "127.0.0.1", "localhost"].includes(
        window.location.hostname,
      )
    )
      return (this.mode = "home");
    throw new Error("无法确认运行模式，已关闭所有业务操作；请使用旧页面");
  }
  stop() {
    this.controller.abort();
  }
  async wait(ms: number, signal = this.controller.signal) {
    if (signal.aborted) throw new DOMException("Aborted", "AbortError");
    await new Promise<void>((resolve, reject) => {
      const abort = () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      };
      const timer = setTimeout(() => {
        signal.removeEventListener("abort", abort);
        resolve();
      }, ms);
      signal.addEventListener("abort", abort, { once: true });
    });
  }
  async request(path: string, init: RequestInit = {}, timeout = 8000) {
    if (!path.startsWith("/") || path.startsWith("//"))
      throw new Error("只允许同源相对接口");
    const controller = new AbortController();
    const stop = () => controller.abort();
    const timer = setTimeout(stop, timeout);
    const signal = AbortSignal.any([
      this.controller.signal,
      controller.signal,
      ...(init.signal ? [init.signal] : []),
    ]);
    try {
      return await this.network(path, { ...init, signal });
    } finally {
      clearTimeout(timer);
    }
  }
  read(path: string, retries = 1, timeout = 8000): Promise<Row> {
    const prior = this.inflight.get(path);
    if (prior) return prior;
    const work = this.readOnce(path, retries, timeout).finally(() =>
      this.inflight.delete(path),
    );
    this.inflight.set(path, work);
    return work;
  }
  private async readOnce(
    path: string,
    retries: number,
    timeout: number,
  ): Promise<Row> {
    let last: unknown;
    for (let retry = 0; retry <= retries; retry++) {
      try {
        for (
          let pending = 0;
          pending <
          (this.mode === "cloud" && path.startsWith("/api/") ? 120 : 1);
          pending++
        ) {
          // Deadline belongs to ONE HTTP exchange (including its body), not the queue wait.
          const attempt = new AbortController();
          const deadline = setTimeout(() => attempt.abort(), timeout);
          try {
            const headers = new Headers(),
              saved = this.validators.get(path);
            if (saved) headers.set("If-None-Match", saved.etag);
            if (this.mode === "cloud")
              headers.set(
                "X-Ops-Page-Visible",
                String(document.visibilityState === "visible"),
              );
            const response = await this.request(
              path,
              { headers, cache: "no-cache", signal: attempt.signal },
              timeout,
            );
            if (response.status === 401 && this.mode === "cloud") {
              this.redirect();
              throw new Error("请重新登录");
            }
            if (response.status === 202 && this.mode === "cloud") {
              clearTimeout(deadline);
              await this.wait(500);
              continue;
            }
            this.observe(path, response);
            if (response.status === 304 && saved) return saved.body;
            if (!response.ok) throw new Error(String(response.status));
            const body = object(await response.json()),
              etag = response.headers.get("ETag");
            if (etag) this.validators.set(path, { etag, body });
            this.watchRefresh(path, response);
            return body;
          } finally {
            clearTimeout(deadline);
          }
        }
        throw new Error("正在向家里取数，稍后自动刷新；已有数据显示保留");
      } catch (error) {
        last = error;
        if (this.controller.signal.aborted) throw error;
        if (retry < retries) await this.wait(500 * 2 ** retry);
      }
    }
    throw last;
  }
  private observe(path: string, response: Response) {
    const age = response.headers.get("X-Cache-Age-Seconds");
    if (age === null) return;
    let health: Row = {};
    try {
      health = object(
        JSON.parse(response.headers.get("X-Source-Health") || "{}"),
      );
    } catch {
      /* Unknown scan age remains unknown. */
    }
    this.samples.set(path, {
      age: Number(age),
      received: performance.now(),
      scan: response.headers.get("X-Source-Scanned-At"),
      sourceAge:
        typeof health.scanAgeSeconds === "number" &&
        Number.isFinite(health.scanAgeSeconds) &&
        health.scanAgeSeconds >= 0
          ? health.scanAgeSeconds
          : null,
      version: response.headers.get("X-Cache-Version"),
      etag: response.headers.get("ETag"),
    });
    this.onSource?.();
  }
  private watchRefresh(path: string, response: Response) {
    const url = new URL(path, window.location.origin);
    if (
      this.mode !== "cloud" ||
      url.pathname !== "/api/dashboard" ||
      !url.searchParams.has("batchId") ||
      response.headers.get("X-Cache-Refresh-Pending") !== "true" ||
      this.watchers.has(path)
    )
      return;
    const version = response.headers.get("X-Cache-Version"),
      tag = response.headers.get("ETag");
    const watch = (async () => {
      for (let i = 0; i < 60; i++) {
        await this.wait(1000);
        if (document.visibilityState !== "visible") return;
        const newer = await this.request(path, {
          headers: { "X-Ops-Page-Visible": "true" },
        });
        if (newer.status === 401) {
          this.redirect();
          return;
        }
        if (
          newer.status === 200 &&
          (newer.headers.get("X-Cache-Version") !== version ||
            newer.headers.get("ETag") !== tag)
        ) {
          this.onRefresh?.();
          return;
        }
      }
    })()
      .catch(() => undefined)
      .finally(() => this.watchers.delete(path));
    this.watchers.set(path, watch);
  }
}
