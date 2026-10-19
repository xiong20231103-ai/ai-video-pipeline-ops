import { controlTimeoutError } from "./control-timeout";
import { ReadClient } from "./client";
import {
  captureReceipt,
  localReceipts,
  pendingStates,
  saveReceipts,
} from "./receipts";
import { object, text, type Row } from "./types";
import { commandLabels } from "@/components/views/presentation";

const allowed = new Set([
  "/api/controls/upload/rescan",
  "/api/controls/upload/verify-history",
]);
const stable = (value: unknown): unknown =>
  Array.isArray(value)
    ? value.map(stable)
    : value && typeof value === "object"
      ? Object.fromEntries(
          Object.entries(value)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([key, item]) => [key, stable(item)]),
        )
      : value;

/** Cloud receives one POST only; all recovery is GET by the persisted identity. */
export class UploadWriter {
  private active = new Map<string, Promise<Row>>();
  constructor(
    readonly reader: ReadClient,
    public health: () => Row,
  ) {}
  available() {
    const h = this.health();
    return (
      (this.reader.mode === "home" && this.active.size === 0) ||
      (this.reader.mode === "cloud" &&
        h.executorAvailable === true &&
        h.homeReady === true &&
        !h.commandBlocker &&
        !localReceipts().some((row) => pendingStates.has(String(row.state))))
    );
  }
  async post(path: string, body: Row | null = {}): Promise<Row> {
    if (
      !allowed.has(path) &&
      !/^\/api\/controls\/tasks\/(create|[^/]+\/(start|cancel|replenish))$/.test(
        path,
      )
    )
      throw new Error("此操作尚未开放云端执行");
    if (this.reader.mode === "home") {
      const key = path + "\n" + JSON.stringify(stable(body || {}));
      const prior = this.active.get(key);
      if (prior) return prior;
      const work = this.home(path, body);
      this.active.set(key, work);
      try {
        return await work;
      } finally {
        this.active.delete(key);
      }
    }
    if (this.reader.mode !== "cloud")
      throw new Error("无法确认运行模式，尚未提交");
    const digest = await crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(path + "\n" + JSON.stringify(stable(body))),
    );
    const fingerprint = Array.from(new Uint8Array(digest), (byte) =>
      byte.toString(16).padStart(2, "0"),
    ).join("");
    const prior = this.active.get(fingerprint);
    if (prior) return prior;
    const work = this.cloud(path, body, fingerprint);
    this.active.set(fingerprint, work);
    try {
      return await work;
    } finally {
      this.active.delete(fingerprint);
    }
  }
  private async home(path: string, body: Row | null) {
    try {
      const response =
        body === null
          ? await this.reader.network(path, { method: "POST" })
          : await this.reader.request(
              path,
              {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body || {}),
              },
              10000,
            );
      const answer = object(await response.json());
      if (!response.ok) throw new Error(text(answer.detail, "操作失败"));
      return answer;
    } catch (error) {
      if (object(error).name === "AbortError")
        throw controlTimeoutError(10000, error);
      throw error;
    }
  }
  private persist(record: Row) {
    const records = localReceipts();
    const index = records.findIndex(
      (row) => row.requestId === record.requestId,
    );
    if (index < 0) records.push(record);
    else records[index] = record;
    saveReceipts(records);
  }
  private async query(record: Row) {
    const url = record.cloudCommandId
      ? "/console/commands/" + encodeURIComponent(String(record.cloudCommandId))
      : "/console/commands/request/" +
        encodeURIComponent(String(record.requestId));
    const response = await this.reader.request(url);
    if (response.status === 404) return null;
    if (response.status === 401) throw new Error("请重新登录");
    if (!response.ok) throw new Error("命令状态暂不可用");
    const answer = object(await response.json());
    Object.assign(record, captureReceipt(record, answer));
    this.persist(record);
    return answer;
  }
  private final(answer: Row) {
    const result = object(answer.result);
    if (answer.state === "completed" && result.kind === "http") {
      const bytes = Uint8Array.from(atob(text(result.bodyBase64, "")), (c) =>
        c.charCodeAt(0),
      );
      const value = object(JSON.parse(new TextDecoder().decode(bytes)));
      if (Number(result.httpStatus) < 200 || Number(result.httpStatus) >= 300)
        throw new Error(text(value.detail, "家里拒绝该操作"));
      return value;
    }
    throw new Error(
      commandLabels[String(answer.state)] ||
        "尚未得到家里回执；请看云端命令面板，不要重复提交",
    );
  }
  private async cloud(path: string, body: Row | null, fingerprint: string) {
    let record = localReceipts().find((row) => row.fingerprint === fingerprint);
    let answer: Row | null = null;
    if (!record) {
      if (!this.available())
        throw new Error("家里未就绪，或有待对账命令；尚未提交");
      record = {
        path,
        fingerprint,
        requestId: crypto.randomUUID(),
        state: "submitting",
        updatedAt: Date.now(),
      };
      this.persist(record); // Fail closed if persistence is unavailable: never send.
      const session = await this.reader.request("/auth/session");
      if (!session.ok) throw new Error("请重新登录");
      const info = object(await session.json());
      try {
        const response = await this.reader.request(path, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": String(info.csrf),
            "X-Client-Request-ID": String(record.requestId),
          },
          body: JSON.stringify(body || {}),
        });
        const value = object(await response.json());
        if (response.status === 202 && value.cloudCommand) {
          Object.assign(record, captureReceipt(record, value));
          this.persist(record);
          answer = value;
        } else if (response.ok)
          throw new Error("云端未返回排队契约，停止自动处理");
        else {
          record.state = "not_sent";
          this.persist(record);
          throw new Error(text(value.detail, "云端拒绝收件"));
        }
      } catch (error) {
        if (record.state === "not_sent") throw error;
        // Lost receive acknowledgement: query original identity; never repeat POST.
      }
    }
    for (let index = 0; index < 180; index++) {
      answer = answer || (await this.query(record));
      if (
        answer &&
        !["queued", "leased", "sent"].includes(String(answer.state))
      )
        return this.final(answer);
      await this.reader.wait(1000);
      answer = null;
    }
    throw new Error(
      "仍在查询命令回执；面板将继续查询，不会自动重发。输入内容保留。",
    );
  }
}

const writers = new WeakMap<ReadClient, UploadWriter>();
export function uploadWriterFor(reader: ReadClient, health: () => Row) {
  let writer = writers.get(reader);
  if (!writer) {
    writer = new UploadWriter(reader, health);
    writers.set(reader, writer);
  }
  writer.health = health;
  return writer;
}
