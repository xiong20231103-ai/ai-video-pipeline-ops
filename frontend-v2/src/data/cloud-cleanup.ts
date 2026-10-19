import { ReadClient } from "./client";
import { UploadWriter, uploadWriterFor } from "./upload-writer";
import { cleanupSpecs, type CleanupKind } from "./home-cleanup";
import { type Row } from "./types";

export type CloudCleanupKind = CleanupKind | "pending";
type Ticket = Row & {
  ids: string[];
  includeUnknown: boolean;
  received: number;
};
const endpoint = "/api/controls/cloud-cleanup/";

/** Tickets live only in this page instance; receipts survive reload in the queue writer. */
export class CloudCleanup {
  private previews = new Map<CloudCleanupKind, Ticket>();
  constructor(
    readonly reader: ReadClient,
    readonly writer: UploadWriter,
    readonly confirm: (message: string) => boolean = window.confirm.bind(
      window,
    ),
    readonly prompt: (message: string) => string | null = window.prompt.bind(
      window,
    ),
    readonly now: () => number = () => performance.now(),
  ) {}
  available() {
    return (
      this.reader.mode === "cloud" &&
      this.writer.health().canCleanup === true &&
      this.writer.available()
    );
  }
  invalidate() {
    this.previews.clear();
  }
  capability() {
    return this.reader.read(endpoint + "capabilities", 0);
  }
  private send(action: string, payload: Row) {
    if (!this.available())
      throw new Error("云端清理未启用、家里未就绪或有待对账命令；尚未提交");
    return this.writer.post(endpoint + action, payload);
  }
  async preview(kind: CloudCleanupKind, ids: string[]) {
    this.previews.delete(kind);
    if (kind !== "pending" && !ids.length) throw new Error("请先勾选对象");
    const chosen = kind === "pending" ? [] : [...ids];
    const includeUnknown =
      kind === "drafts" &&
      this.confirm(
        "本次选择是否包含人工或来源不明草稿？选“取消”将保护这类草稿。",
      );
    const value = await this.send("preview", {
      kind,
      ids: chosen,
      includeUnknown,
    });
    if (
      value.kind !== kind ||
      !Array.isArray(value.ids) ||
      JSON.stringify(value.ids) !== JSON.stringify(chosen) ||
      typeof value.ticket !== "string" ||
      typeof value.expiresAt !== "number"
    )
      throw new Error("预览契约不完整，请重新预览");
    this.previews.set(kind, {
      ...value,
      ids: chosen,
      includeUnknown,
      received: this.now(),
    });
    return value;
  }
  async execute(kind: CloudCleanupKind, ids: string[]) {
    if (kind === "pending") await this.preview(kind, []);
    const p = this.previews.get(kind);
    if (!p || this.now() - p.received >= 120000)
      throw new Error("预览已过期或页面已重载，请重新预览");
    if (kind !== "pending" && JSON.stringify(ids) !== JSON.stringify(p.ids))
      throw new Error("选择已变化，请重新预览");
    if (
      p.containsManualOrUnknown &&
      !this.confirm("包含人工或来源不明草稿，请再次确认所选对象。")
    )
      return null;
    if (
      p.containsTestFiles &&
      !this.confirm("包含测试文件，请再次确认所选对象。")
    )
      return null;
    if (
      !this.confirm(
        kind === "pending"
          ? "将立即永久清除待删区，不能恢复。是否继续？"
          : "所选对象将移入待删区，保留3天后清除。是否继续？",
      )
    )
      return null;
    const magic =
      kind === "pending"
        ? "EMPTY_PENDING_DELETE_NOW"
        : cleanupSpecs[kind].confirmation;
    if (this.prompt("请输入 " + magic + " 确认本次操作") !== magic) return null;
    if (
      kind === "pending" &&
      this.prompt("再次输入 EMPTY_PENDING_DELETE_NOW 确认永久清除") !== magic
    )
      return null;
    if (this.now() - p.received >= 120000)
      throw new Error("确认期间预览已过期，请重新预览");
    const result = await this.send("execute", {
      kind,
      ids: p.ids,
      includeUnknown: p.includeUnknown,
      snapshotToken: p.snapshotToken,
      ticket: p.ticket,
      expiresAt: p.expiresAt,
      confirm: magic,
    });
    this.previews.delete(kind);
    return result;
  }
}
const services = new WeakMap<ReadClient, CloudCleanup>();
export function cloudCleanupFor(reader: ReadClient, health: () => Row) {
  const writer = uploadWriterFor(reader, health);
  let service = services.get(reader);
  if (!service) {
    service = new CloudCleanup(reader, writer);
    services.set(reader, service);
  }
  // Existing writer health closure is updated by uploadWriterFor on each render.
  return service;
}
