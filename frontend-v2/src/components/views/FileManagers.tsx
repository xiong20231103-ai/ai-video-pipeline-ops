import { useEffect, useRef, useState } from "react";
import { cloudCleanupFor } from "@/data/cloud-cleanup";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  HomeCleanup,
  cleanupField,
  cleanupFiltered,
  cleanupSpecs,
  type CleanupKind,
} from "@/data/home-cleanup";
import { formatBytes, formatDateTime } from "@/data/legacy-formatters";
import {
  list,
  object,
  number,
  text,
  type Row,
  type Snapshot,
} from "@/data/types";
import type { ReadClient } from "@/data/client";
import { Panel, Status, Table } from "./shared";
import { PendingDelete } from "./CloudViews";

export default function FileManagers({
  snapshot,
  reader,
  refresh,
}: {
  snapshot: Snapshot;
  reader: ReadClient | null;
  refresh: () => void;
}) {
  const [capabilityNote, setCapabilityNote] = useState("");
  const [kind, setKind] = useState<CleanupKind | null>(null),
    [payload, setPayload] = useState<Row>({}),
    [selection, setSelection] = useState<string[]>([]),
    [filters, setFilters] = useState<Record<string, string>>({}),
    [preview, setPreview] = useState<Row | null>(null),
    [error, setError] = useState(""),
    [result, setResult] = useState<Row | null>(null),
    [busy, setBusy] = useState(""),
    [protection, setProtection] = useState<Row | null>(null),
    [pendingReply, setPendingReply] = useState<{
      source: Row;
      value: Row;
    } | null>(null);
  const inFlight = useRef(false),
    generation = useRef(0),
    service = reader ? new HomeCleanup(reader) : null;
  const cloudService =
    reader && snapshot.mode === "cloud"
      ? cloudCleanupFor(reader, () => snapshot.status)
      : null;
  const canWrite =
    snapshot.mode === "home" || Boolean(cloudService?.available());
  useEffect(() => {
    if (!reader || snapshot.mode !== "cloud" || !kind) return;
    let cancelled = false;
    const check = () => {
      void reader
        .read("/api/controls/cloud-cleanup/capabilities", 0)
        .catch(() => {
          if (!cancelled)
            setCapabilityNote("暂未取得清理通道状态；等待云端状态刷新");
        });
    };
    check();
    const timer = setInterval(check, 30000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [kind, reader, snapshot.mode]);
  const pending =
    pendingReply?.source === snapshot.pendingDelete
      ? pendingReply.value
      : snapshot.pendingDelete;
  const rows = list(payload.items),
    spec = kind ? cleanupSpecs[kind] : null,
    visible = kind ? cleanupFiltered(kind, rows, filters) : [],
    categories = object(object(payload.counts).categories);
  function invalidate() {
    setPreview(null);
    cloudService?.invalidate();
  }
  async function load(next: CleanupKind, defaults = false) {
    if (!service || inFlight.current) return;
    const id = ++generation.current;
    inFlight.current = true;
    setBusy("load");
    cloudService?.invalidate();
    setKind(next);
    setError("");
    setPreview(null);
    try {
      const value = await service.load(next);
      if (id !== generation.current) return;
      const categoryCounts = object(object(value.counts).categories);
      const items = list(value.items),
        key = cleanupSpecs[next].id;
      setPayload(value);
      setSelection((previous) =>
        defaults && next === "production"
          ? items
              .filter(
                (row) =>
                  row.defaultSelected &&
                  !row.protected &&
                  typeof row[key] === "string" &&
                  row[key],
              )
              .map((row) => String(row[key]))
          : previous.filter((id) =>
              items.some((row) => String(row[key]) === id && !row.protected),
            ),
      );
      setFilters((previous) =>
        Object.fromEntries(
          Object.entries(previous).map(([key, value]) => [
            key,
            ["query", "state"].includes(key) ||
            (next === "drafts" && key === "category") ||
            (next === "production" &&
              key === "category" &&
              Object.hasOwn(categoryCounts, value)) ||
            items.some((row) => cleanupField(next, row, key) === value)
              ? value
              : "",
          ]),
        ),
      );
    } catch (error) {
      setError(error instanceof Error ? error.message : "读取失败");
    } finally {
      inFlight.current = false;
      setBusy("");
    }
  }
  async function makePreview() {
    if (!kind || !service || inFlight.current || !canWrite) return;
    inFlight.current = true;
    setBusy("preview");
    setPreview(null);
    setError("");
    try {
      const value = cloudService
        ? await cloudService.preview(kind, selection)
        : await service.preview(kind, selection);
      setPreview(value);
      if (number(value.blockedCount) && kind === "audio")
        window.alert(
          `有 ${value.blockedCount} 个音频被活动任务保护，已禁止删除。请查看页面中的具体原因。`,
        );
      if (number(value.blockedCount) && kind === "production")
        window.alert(
          `有 ${value.blockedCount} 个文件被活动任务、云端核验或身份规则保护，已自动排除。`,
        );
    } catch (error) {
      const message = error instanceof Error ? error.message : "请刷新后重试";
      setError(message);
      if (kind === "audio") window.alert(message);
    } finally {
      inFlight.current = false;
      setBusy("");
    }
  }
  async function execute() {
    if (!kind || !preview || !service || inFlight.current || !canWrite) return;
    inFlight.current = true;
    setBusy("execute");
    setError("");
    try {
      const value = cloudService
        ? await cloudService.execute(kind, selection)
        : await service.execute(kind, preview);
      if (!value) return;
      setResult(value);
      setSelection([]);
      setPreview(null);
      inFlight.current = false;
      await load(kind);
      refresh();
      if (kind !== "drafts")
        window.alert(
          text(
            value.message,
            kind === "audio" ? "音频已移入待删区" : "生产文件清理已完成",
          ),
        );
    } catch (error) {
      const message = error instanceof Error ? error.message : "清理失败";
      setError(message);
      setResult({ state: "failed", message });
      if (kind !== "drafts") window.alert(message);
    } finally {
      inFlight.current = false;
      setBusy("");
    }
  }
  async function empty() {
    if (!service || inFlight.current || !canWrite) return;
    inFlight.current = true;
    setBusy("pending");
    try {
      const value = cloudService
        ? await cloudService.execute("pending", [])
        : await service.emptyPending(pending);
      if (value) {
        setResult(value);
        window.alert(text(value.message, "待删区已清空"));
      }
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "清空待删区失败");
    } finally {
      try {
        const value = await reader!.read("/api/controls/pending-delete");
        setPendingReply({ source: snapshot.pendingDelete, value });
      } catch {
        /* keep last trusted inventory */
      }
      inFlight.current = false;
      setBusy("");
    }
  }
  function choose(id: string, checked: boolean) {
    if (
      busy ||
      !spec ||
      !rows.some((row) => row[spec.id] === id && !row.protected)
    )
      return;
    setSelection((old) =>
      checked
        ? [...new Set([...old, id])]
        : old.filter((value) => value !== id),
    );
    invalidate();
  }
  const selected = rows.filter(
      (row) => spec && selection.includes(String(row[spec.id])),
    ),
    size = selected.reduce((sum, row) => sum + number(row.sizeBytes), 0);
  const filterKeys =
    kind === "drafts"
      ? ["category", "date"]
      : kind === "audio"
        ? ["date", "project", "material", "language", "audioBatch", "state"]
        : ["date", "project", "material", "category", "state"];
  const labels: Record<string, string> = {
    category: "类型",
    date: "日期",
    project: "项目",
    material: "材料",
    language: "语言",
    audioBatch: "批次",
    state: "任务状态",
  };
  return (
    <>
      <Panel title="文件管理">
        <p>
          只处理服务器登记的对象；受保护对象不可选择。移入同盘待删区，保留 3
          天。
        </p>
        <div className="data-actions">
          {(Object.keys(cleanupSpecs) as CleanupKind[]).map((next) => (
            <Button
              key={next}
              disabled={!reader || !!busy}
              onClick={() => {
                setFilters({});
                setSelection([]);
                setPayload({});
                setResult(null);
                void load(next, true);
              }}
            >
              管理 {cleanupSpecs[next].title}
            </Button>
          ))}
        </div>
        {snapshot.mode === "cloud" && (
          <p>
            云端清理通过命令队列，家里执行后返回逐项回执。
            {canWrite
              ? "清理通道已就绪。"
              : "清理开关未开启、家里未就绪或有命令待核对，操作已锁定。"}
          </p>
        )}
      </Panel>
      <PendingDelete
        data={pending}
        actions={
          number(pending.count) > 0 && (
            <Button
              variant="outline"
              disabled={!canWrite || !!busy}
              onClick={() => void empty()}
            >
              立即清空待删区（{number(pending.count)} 项，约{" "}
              {formatBytes(pending.sizeBytes)}）
            </Button>
          )
        }
      />
      {snapshot.mode === "cloud" && (
        <>
          <Button
            variant="outline"
            disabled={!!busy}
            onClick={() => {
              void cloudService
                ?.capability()
                .then(() =>
                  setCapabilityNote("已请求清理通道状态，等待云端状态刷新"),
                )
                .catch((error) =>
                  setCapabilityNote(
                    error instanceof Error ? error.message : "检查失败",
                  ),
                );
            }}
          >
            检查清理通道
          </Button>
          {capabilityNote && <p role="status">{capabilityNote}</p>}
        </>
      )}
      {result && (
        <p role="status">
          {text(result.state)} · {text(result.message)}
        </p>
      )}
      <Sheet
        open={Boolean(kind)}
        onOpenChange={(open) => {
          if (!open && !inFlight.current) {
            setKind(null);
            generation.current++;
          }
        }}
      >
        <SheetContent className="file-manager-sheet">
          <SheetHeader>
            <SheetTitle>管理 {kind ? cleanupSpecs[kind].title : ""}</SheetTitle>
          </SheetHeader>
          <div className="file-manager-body">
            <p>
              {kind === "drafts"
                ? "CapCut 或批处理客户端运行时禁止删除。人工及来源不明草稿不会默认勾选。"
                : kind === "audio"
                  ? "活动、等待恢复、拼接中或 CapCut 处理中任务引用的音频会被锁定。点击受保护行可查看具体原因。"
                  : "活动任务、云端核验或身份规则保护的文件不会删除。永不包含 E:\\JianyingPro Drafts。"}
            </p>
            <div className="data-actions">
              <Status
                state={
                  number(object(payload.counts).protected) ||
                  (Array.isArray(payload.runningProcesses)
                    ? payload.runningProcesses.length
                    : 0)
                    ? "failed"
                    : "neutral"
                }
              >
                {number(object(payload.counts).total)} 个
              </Status>
              <Button
                variant="outline"
                disabled={!!busy || !kind}
                onClick={() => kind && void load(kind)}
              >
                刷新清单
              </Button>
            </div>
            {kind === "production" && (
              <div className="category-tiles">
                {Object.entries(categories).map(([key, raw]) => {
                  const row = object(raw);
                  return (
                    <Button
                      key={key}
                      variant="outline"
                      disabled={!!busy}
                      onClick={() => {
                        setFilters((old) => ({ ...old, category: key }));
                        invalidate();
                      }}
                    >
                      {text(row.label, key)} · {number(row.total)} 个 ·{" "}
                      {formatBytes(row.sizeBytes)} · 可清理{" "}
                      {number(row.deletable)} / 保护 {number(row.protected)}
                    </Button>
                  );
                })}
              </div>
            )}
            <div className="manager-filters">
              {filterKeys.map((key) => {
                let options = [
                  ...new Set(
                    rows
                      .map((row) => (kind ? cleanupField(kind, row, key) : ""))
                      .filter(Boolean),
                  ),
                ].sort((a, b) =>
                  key === "date"
                    ? b.localeCompare(a)
                    : a.localeCompare(b, "zh-CN"),
                );
                if (key === "category" && kind === "drafts")
                  options = ["formal", "lab", "manual_or_unknown"];
                if (key === "state") options = ["deletable", "protected"];
                if (key === "category" && kind === "production")
                  options = Object.keys(categories);
                return (
                  <label key={key}>
                    {labels[key]}
                    <select
                      aria-label={labels[key]}
                      disabled={!!busy}
                      value={filters[key] || ""}
                      onChange={(event) => {
                        setFilters((old) => ({
                          ...old,
                          [key]: event.target.value,
                        }));
                        invalidate();
                      }}
                    >
                      <option value="">
                        全部{labels[key]}（{rows.length}）
                      </option>
                      {options.map((value) => (
                        <option key={value} value={value}>
                          {key === "category"
                            ? text(
                                object(categories[value]).label,
                                (
                                  {
                                    formal: "正式自动",
                                    lab: "内测",
                                    manual_or_unknown: "人工/不明",
                                  } as Record<string, string>
                                )[value] || value,
                              )
                            : key === "state"
                              ? value === "protected"
                                ? "任务正在使用"
                                : "可手动删除"
                              : value}
                          {key !== "state" &&
                          !(kind === "drafts" && key === "category")
                            ? "（" +
                              rows.filter(
                                (row) =>
                                  kind &&
                                  cleanupField(kind, row, key) === value,
                              ).length +
                              "）"
                            : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                );
              })}
              <label>
                搜索
                <Input
                  aria-label="搜索文件"
                  type="search"
                  disabled={!!busy}
                  value={filters.query || ""}
                  onChange={(event) => {
                    setFilters((old) => ({
                      ...old,
                      query: event.target.value,
                    }));
                    invalidate();
                  }}
                />
              </label>
            </div>
            <div className="data-actions">
              <Button
                variant="outline"
                disabled={!!busy}
                onClick={() => {
                  if (!spec) return;
                  setSelection((old) => [
                    ...new Set([
                      ...old,
                      ...visible
                        .filter(
                          (row) =>
                            !row.protected &&
                            typeof row[spec.id] === "string" &&
                            row[spec.id],
                        )
                        .map((row) => String(row[spec.id])),
                    ]),
                  ]);
                  invalidate();
                }}
              >
                全选当前筛选
              </Button>
              <Button
                variant="outline"
                disabled={!!busy}
                onClick={() => {
                  setSelection([]);
                  invalidate();
                }}
              >
                取消全选
              </Button>
              <strong>
                已选择 {selected.length} 个 · {formatBytes(size)}
                {kind === "production" &&
                selected.some((row) => row.category === "capcut_test")
                  ? ` · 含测试 ${selected.filter((row) => row.category === "capcut_test").length}`
                  : ""}
              </strong>
            </div>
            {error && <p role="alert">{error}</p>}
            {!error && (
              <Table
                headings={[
                  "选择",
                  "名称",
                  "类型 / 状态",
                  "日期 / 大小",
                  "身份 / 来源",
                ]}
                empty={!visible.length}
              >
                {visible.map((row, index) => (
                  <tr key={text(spec ? row[spec.id] : index)}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`选择 ${text(row.name)}`}
                        disabled={
                          !!busy ||
                          Boolean(row.protected) ||
                          !spec ||
                          typeof row[spec.id] !== "string"
                        }
                        checked={Boolean(
                          spec && selection.includes(String(row[spec.id])),
                        )}
                        onChange={(event) =>
                          spec &&
                          choose(String(row[spec.id]), event.target.checked)
                        }
                      />
                    </td>
                    <td>
                      {row.protected && kind !== "drafts" ? (
                        <Button
                          variant="ghost"
                          onClick={() => setProtection(row)}
                        >
                          {text(row.name)}
                        </Button>
                      ) : (
                        text(row.name)
                      )}
                    </td>
                    <td>
                      {text(
                        row.categoryLabel,
                        row.category
                          ? (
                              {
                                formal: "正式自动",
                                lab: "内测",
                                manual_or_unknown: "人工/不明",
                              } as Record<string, string>
                            )[String(row.category)] || String(row.category)
                          : "",
                      )}
                      <p>
                        {row.protected
                          ? kind === "drafts"
                            ? text(row.protectedReason)
                            : kind === "audio"
                              ? "任务正在使用，禁止删除"
                              : "受保护"
                          : kind === "production"
                            ? row.category === "capcut_test"
                              ? "测试文件，可手动清理"
                              : "云端已核验，可清理"
                            : kind === "drafts"
                              ? row.inIndex
                                ? "索引正常"
                                : "目录未登记在首页索引"
                              : "可手动删除"}
                      </p>
                    </td>
                    <td>
                      {kind === "drafts"
                        ? formatDateTime(row.updatedAt || row.createdAt)
                        : kind === "audio"
                          ? text(row.date) +
                            " · " +
                            formatDateTime(row.updatedAt || row.createdAt)
                          : text(row.date)}{" "}
                      · {formatBytes(row.sizeBytes)}
                    </td>
                    <td>
                      {kind === "drafts"
                        ? text(
                            row.sourceLabel,
                            row.protected
                              ? text(row.protectedReason)
                              : row.inIndex
                                ? "索引正常"
                                : "目录未登记在首页索引",
                          )
                        : [row.project, row.material, row.language]
                            .filter(Boolean)
                            .join(" / ") ||
                          text(
                            row.sourceLabel,
                            kind === "production" &&
                              row.category === "capcut_test"
                              ? "隔离测试文件"
                              : "历史或未登记任务",
                          )}
                      <p>{text(row.relativePath, "")}</p>
                    </td>
                  </tr>
                ))}
              </Table>
            )}
            {preview && (
              <Panel title="清理预览">
                <p>{text(preview.message)}</p>
                {snapshot.mode === "cloud" && (
                  <p>
                    预览有效期至{" "}
                    {formatDateTime(Number(preview.expiresAt) * 1000)}
                    ；页面重载后需重新预览。
                  </p>
                )}
                <p>
                  可处理 {number(preview.deletableCount)}，阻止{" "}
                  {number(preview.blockedCount)} · 约{" "}
                  {formatBytes(preview.sizeBytes)}
                </p>
                {list(preview.categories).map((row, index) => (
                  <p key={index}>
                    {text(row.label)}：{number(row.count)} 个 ·{" "}
                    {formatBytes(row.sizeBytes)}
                  </p>
                ))}
                <ul>
                  {list(preview.blocked)
                    .slice(0, kind === "production" ? 30 : undefined)
                    .map((row, index) => (
                      <li key={index}>
                        {text(row.name)}：{text(row.reason)}
                      </li>
                    ))}
                </ul>
                {kind === "production" && number(preview.blockedCount) > 30 && (
                  <p>
                    另有 {number(preview.blockedCount) - 30}{" "}
                    个受保护文件，请返回清单查看。
                  </p>
                )}
              </Panel>
            )}
            <div className="data-actions">
              <Button
                disabled={!!busy || !selection.length || !canWrite}
                onClick={() => void makePreview()}
              >
                {busy === "preview"
                  ? "正在核对…"
                  : kind === "production"
                    ? "预览清理"
                    : "预览删除"}
              </Button>
              {Boolean(number(preview?.deletableCount)) && (
                <Button
                  variant="destructive"
                  disabled={!!busy || !canWrite}
                  onClick={() => void execute()}
                >
                  {busy === "execute" ? "正在移入待删区…" : "确认移入待删区"}
                </Button>
              )}
            </div>
            {result && (
              <p role="status">
                {text(result.state)} · {text(result.message)}
              </p>
            )}
            {result && (
              <details>
                <summary>逐项回执</summary>
                <p>{text(result.message)}</p>
                {list(result.items || result.results || result.failed).map(
                  (row, index) => (
                    <p key={index}>
                      {text(row.name || row.id)}：
                      {text(row.message || row.reason || row.state)}
                    </p>
                  ),
                )}
              </details>
            )}
          </div>
        </SheetContent>
      </Sheet>
      <Sheet
        open={Boolean(protection)}
        onOpenChange={(open) => {
          if (!open) setProtection(null);
        }}
      >
        <SheetContent>
          <SheetHeader>
            <SheetTitle>文件受保护</SheetTitle>
          </SheetHeader>
          <div className="file-manager-body">
            <p>{text(protection?.name)}</p>
            <p>
              {[protection?.project, protection?.material, protection?.language]
                .filter(Boolean)
                .join(" / ") || "历史或未登记任务"}
            </p>
            <p>{text(protection?.taskState, "受保护")}</p>
            <p>{text(protection?.protectedReason, "任务正在使用，禁止删除")}</p>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
