import { controlTimeoutError } from "./control-timeout";
import { ReadClient } from "./client";
import { list, number, object, text, type Row } from "./types";
import { formatBytes } from "./legacy-formatters";
export type CleanupKind = "drafts" | "audio" | "production";
export const cleanupSpecs = {
  drafts: {
    title: "CapCut 草稿",
    endpoint: "capcut-drafts",
    id: "draftId",
    ids: "draftIds",
    action: "cleanup",
    confirmation: "RECYCLE_SELECTED_CAPCUT_DRAFTS",
  },
  audio: {
    title: "音频文件",
    endpoint: "audio-files",
    id: "audioId",
    ids: "audioIds",
    action: "recycle",
    confirmation: "RECYCLE_SELECTED_AUDIO_FILES",
  },
  production: {
    title: "生产文件",
    endpoint: "production-files",
    id: "fileId",
    ids: "fileIds",
    action: "recycle",
    confirmation: "RECYCLE_SELECTED_PRODUCTION_FILES",
  },
} as const;
export function cleanupDate(value: unknown) {
  const date = new Date((value || "") as string);
  return Number.isNaN(date.getTime())
    ? ""
    : `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
export function cleanupField(kind: CleanupKind, row: Row, key: string): string {
  if (key === "date")
    return kind === "drafts"
      ? cleanupDate(row.updatedAt || row.createdAt)
      : String(row.date || cleanupDate(row.updatedAt));
  return String(row[key] || "");
}
export function cleanupFiltered(
  kind: CleanupKind,
  rows: Row[],
  filters: Record<string, string>,
) {
  return rows.filter((row) => {
    for (const key of [
      "date",
      "project",
      "material",
      "language",
      "audioBatch",
      "category",
    ])
      if (filters[key] && cleanupField(kind, row, key) !== filters[key])
        return false;
    if (
      (filters.state === "protected" && !row.protected) ||
      (filters.state === "deletable" && row.protected)
    )
      return false;
    const query = (filters.query || "").trim().toLocaleLowerCase();
    const fields =
      kind === "drafts"
        ? [row.name || "", row.sourceLabel || ""]
        : kind === "audio"
          ? [
              row.name || "",
              row.relativePath || "",
              row.project || "",
              row.material || "",
              row.language || "",
            ]
          : [
              row.name,
              row.relativePath,
              row.categoryLabel,
              row.project,
              row.material,
              row.language,
              row.taskState,
            ];
    return !query || fields.join(" ").toLocaleLowerCase().includes(query);
  });
}
let activeCleanup: Promise<Row> | null = null;
export class HomeCleanup {
  constructor(
    readonly reader: ReadClient,
    readonly confirm: (message: string) => boolean = window.confirm.bind(
      window,
    ),
  ) {}
  load(kind: CleanupKind) {
    return this.reader.read(
      "/api/controls/" + cleanupSpecs[kind].endpoint,
      1,
      60000,
    );
  }
  async post(path: string, body: Row, timeout = 10000): Promise<Row> {
    if (this.reader.mode !== "home")
      throw new Error("家里清理接口仅限家里模式；云端必须使用清理队列");
    if (activeCleanup) throw new Error("上一条文件操作仍在处理，请等待原回执");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    const work = (async () => {
      try {
        const response = await this.reader.network(path, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal: controller.signal,
        });
        const value = object(await response.json());
        if (!response.ok) throw new Error(text(value.detail, "操作失败"));
        return value;
      } catch (error) {
        if (object(error).name === "AbortError") {
          throw controlTimeoutError(timeout, error);
        }
        throw error;
      } finally {
        clearTimeout(timer);
      }
    })();
    activeCleanup = work;
    try {
      return await work;
    } finally {
      if (activeCleanup === work) activeCleanup = null;
    }
  }
  preview(kind: CleanupKind, ids: string[]) {
    if (!ids.length) throw new Error("请先勾选要移入待删区的对象");
    return this.post(
      "/api/controls/" + cleanupSpecs[kind].endpoint + "/preview",
      { [cleanupSpecs[kind].ids]: ids },
      60000,
    );
  }
  async execute(kind: CleanupKind, preview: Row) {
    if (!number(preview.deletableCount)) return null;
    const specCheck = cleanupSpecs[kind];
    if (
      typeof preview.snapshotToken !== "string" ||
      !preview.snapshotToken ||
      !list(preview.deletable).length ||
      list(preview.deletable).some(
        (row) => typeof row[specCheck.id] !== "string" || !row[specCheck.id],
      )
    )
      throw new Error("预览契约不完整，请重新预览");
    const count = number(preview.deletableCount),
      size = formatBytes(preview.sizeBytes);
    const question =
      kind === "drafts"
        ? `确认将 ${count} 个草稿移入待删区吗？保留 3 天后自动清除，期间可恢复；不会删除视频、音频、成片或生产任务。`
        : kind === "audio"
          ? `确认将 ${count} 个音频文件（${size}）移入待删区吗？保留 3 天后自动清除，期间可恢复；不会删除文件夹，也不会改变任务完成状态。`
          : `确认将 ${count} 个生产文件（${size}）移入待删区吗？保留 3 天后自动清除，期间可恢复；项目状态、上传记录及云端文件不会改变。`;
    if (!this.confirm(question)) return null;
    if (
      kind === "drafts" &&
      preview.containsManualOrUnknown &&
      !this.confirm(
        "选择中包含人工或来源不明草稿。再次确认仍要将这些草稿移入待删区。",
      )
    )
      return null;
    if (
      kind === "production" &&
      preview.containsTestFiles &&
      !this.confirm(
        "选择中包含 CapCut 测试或首帧测试文件。再次确认仍要将这些测试文件移入待删区。",
      )
    )
      return null;
    const spec = cleanupSpecs[kind],
      ids = list(preview.deletable).map((row) => String(row[spec.id]));
    const payload: Row = {
      [spec.ids]: ids,
      snapshotToken: preview.snapshotToken,
      confirm: spec.confirmation,
    };
    if (kind === "drafts")
      payload.includeUnknown = Boolean(preview.containsManualOrUnknown);
    return this.post(
      "/api/controls/" + spec.endpoint + "/" + spec.action,
      payload,
      kind === "production" ? 15 * 60 * 1000 : 10000,
    );
  }
  async emptyPending(info: Row) {
    if (
      !this.confirm(
        `确认立即永久清除待删区的 ${number(info.count)} 项（约 ${formatBytes(info.sizeBytes)}）吗？清除后无法恢复。`,
      )
    )
      return null;
    if (!this.confirm("再次确认：这一步会永久删除，不进入回收站。"))
      return null;
    return this.post(
      "/api/controls/pending-delete/empty",
      { confirm: "EMPTY_PENDING_DELETE_NOW" },
      600000,
    );
  }
}
