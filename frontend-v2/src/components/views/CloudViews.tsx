import AccountActions from "./AccountActions";
import BackupAction from "./BackupAction";
import { CommandActions, SubmissionCancellation } from "./CommandActions";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  object as o,
  list,
  number as n,
  text as t,
  strings,
  type Snapshot,
  type Row,
} from "@/data/types";
import type { ReadClient } from "@/data/client";
import {
  formatClock,
  formatBytes,
  formatDateTime,
} from "@/data/legacy-formatters";
import { commandLabels } from "./presentation";
import { Panel, Status, Table, Empty, Field, DisabledWrite } from "./shared";
import { Button } from "@/components/ui/button";

export function Freshness({ snapshot }: { snapshot: Snapshot }) {
  const [tick, setTick] = useState(() => performance.now());
  const started = useRef(tick);
  useEffect(() => {
    const timer = setInterval(() => setTick(performance.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const sample = Object.entries(snapshot.sources)
    .filter(([key]) => /^\/api\/dashboard(?:\?|\/summary|$)/.test(key))
    .map(([, value]) => value)
    .sort((a, b) => b.received - a.received)[0];
  const cloud = snapshot.mode === "cloud",
    known =
      !cloud || (sample?.sourceAge !== null && sample?.sourceAge !== undefined);
  const age = Math.max(
    0,
    cloud && sample
      ? (tick - sample.received) / 1000 + sample.age + (sample.sourceAge || 0)
      : (tick - (snapshot.receivedTick ?? started.current)) / 1000,
  );
  const received = Boolean(snapshot.receivedAt),
    tone = age > 120 ? "danger" : age > 30 || !known ? "warning" : "neutral";
  const stamp = cloud
    ? known && received
      ? formatClock(new Date(Date.now() - age * 1000))
      : "源扫描时间未知"
    : received
      ? formatClock(snapshot.receivedAt)
      : "等待首次同步";
  return (
    <div
      className={`freshness-banner tone-${tone}`}
      role="status"
      data-testid="freshness"
    >
      <span>
        数据截至 <strong>{stamp}</strong>{" "}
        {received && <span>（{Math.floor(age)} 秒前）</span>}
      </span>
      {cloud && <small>云端缓存 · 收到缓存不代表实时</small>}
      {(age > 30 || !known) && <p>页面数据可能已过期，按 Ctrl+F5 刷新</p>}
    </div>
  );
}

export function SourcePanel({
  snapshot,
  reader = null,
}: {
  snapshot: Snapshot;
  reader?: ReadClient | null;
}) {
  const [tick, setTick] = useState(() => performance.now());
  useEffect(() => {
    const timer = setInterval(() => setTick(performance.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const health = snapshot.status;
  const state = !Object.hasOwn(health, "agentOnline")
    ? "云端状态尚未确认"
    : health.heartbeatAgeSeconds === null
      ? "等待家里代理部署/连接"
      : !health.agentOnline
        ? `家里离线，距心跳 ${Math.floor(n(health.heartbeatAgeSeconds))} 秒`
        : health.engineState === "healthy"
          ? "家里在线"
          : health.engineState === "busy"
            ? "引擎忙，保留已有数据"
            : "代理在线，旧引擎状态不可用/尚待确认";
  const names: Record<string, string> = {
    "/api/dashboard": "完整看板",
    "/api/dashboard/summary": "当前摘要",
    "/api/health": "递交健康",
    "/api/safety": "安全面板",
    "/api/task-boxes/current": "当前任务箱",
    "/api/task-boxes/history": "历史任务箱",
    "/api/controls/tasks": "任务队列",
    "/api/controls/templates": "任务模板",
    "/api/project-gaps": "项目缺口",
    "/api/pipeline": "历史流水线",
    "/api/controls/continue-current/status": "恢复状态",
    "/api/control-commands/current": "命令状态",
    "/api/subtitle-verification/current": "字幕核验",
  };
  return (
    <Panel title={`云端缓存 · ${state}`} motionId="cloud-sources">
      <p className="data-muted">
        列表记录本页读到的各份数据；切换日期后旧条目会保留，请以当前所选看板为准。
      </p>
      <p>
        {health.executorAvailable
          ? health.commandsPaused
            ? "命令下发已暂停"
            : "命令通道已部署"
          : "等待 Claude 部署命令代理"}{" "}
        · 当前账号：{t(snapshot.session.username, "等待会话")}
      </p>
      <Table
        headings={["数据来源", "数据截至", "缓存年龄", "状态"]}
        empty={!Object.keys(snapshot.sources).length}
      >
        {Object.entries(snapshot.sources).map(([key, sample]) => {
          const parsed = new URL(key, window.location.origin),
            age = Math.floor(
              sample.age + Math.max(0, tick - sample.received) / 1000,
            ),
            effective =
              sample.sourceAge === null ? null : sample.sourceAge + age;
          return (
            <tr key={key}>
              <td>
                {names[parsed.pathname] || "页面数据"}
                {parsed.searchParams.get("date")
                  ? " " + parsed.searchParams.get("date")
                  : ""}
              </td>
              <td>
                {effective === null || !sample.scan
                  ? "源扫描时间未知"
                  : `${formatClock(sample.scan)}（${Math.floor(effective)} 秒前）`}
              </td>
              <td>该版本最近取数 {age} 秒前</td>
              <td>
                <Status
                  state={
                    age > 120 || (effective !== null && effective > 120)
                      ? "failed"
                      : age > 30 || effective === null || effective > 30
                        ? "warning"
                        : "healthy"
                  }
                >
                  {effective === null
                    ? "更新时间未知"
                    : effective > 120
                      ? "可能已过期"
                      : "缓存数据"}
                </Status>
              </td>
            </tr>
          );
        })}
      </Table>
      <div className="data-actions">
        <AccountActions reader={reader} />
      </div>
    </Panel>
  );
}

export function CommandList({
  items,
  reader = null,
  refresh = () => {},
}: {
  items: Row[];
  reader?: ReadClient | null;
  refresh?: () => void;
}) {
  return (
    <Panel title="云端命令回执（HTTP 回执与业务完成分开）">
      <p className="data-muted">
        已完成仅表示收到家里 HTTP
        回执，业务进度请看原状态。结果不明不会自动重发。
      </p>
      <Table
        headings={["请求", "回执状态", "编号", "操作"]}
        empty={!items.length}
      >
        {items.slice(0, 50).map((x, i) => (
          <tr key={t(x.cloudCommandId || x.requestId, String(i))}>
            <td>{t(x.path || x.target)}</td>
            <td>
              <Status state={t(x.state)}>
                {commandLabels[t(x.state)] || t(x.state)}
              </Status>
            </td>
            <td>
              <code>{t(x.cloudCommandId || x.requestId)}</code>
            </td>
            <td>
              <CommandActions row={x} reader={reader} refresh={refresh} />
            </td>
          </tr>
        ))}
      </Table>
      <SubmissionCancellation reader={reader} refresh={refresh} />
    </Panel>
  );
}

export function BackupPanel({ reader }: { reader: ReadClient | null }) {
  const [data, setData] = useState<Row | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function load() {
    if (!reader || busy) return;
    setBusy(true);
    try {
      setData(await reader.read("/console/backups", 0));
      setError("");
    } catch (error) {
      setError(error instanceof Error ? error.message : "读取失败");
    } finally {
      setBusy(false);
    }
  }
  const phases: Record<string, string> = {
    waiting_configuration: "等待本机配置恢复密钥",
    creating: "正在生成",
    uploading: "正在上传",
    completed: "最近一次已上传",
    failed: "备份失败，请检查代理状态",
  };
  return (
    <Panel
      title="异地备份（台账与配置）"
      actions={
        <Button
          size="sm"
          variant="outline"
          onClick={() => void load()}
          disabled={busy}
        >
          刷新列表
        </Button>
      }
    >
      <details
        className="data-details"
        onToggle={(e) => {
          if (e.currentTarget.open && !data && !busy) void load();
        }}
      >
        <summary>查看备份状态与已完成备份包</summary>
        {error && <p role="alert">{error}</p>}
        {data ? (
          <>
            <p>
              仅台账和配置恢复；视频、草稿不在备份中。已用及预留{" "}
              {(n(data.usedReservedBytes) / 1048576).toFixed(1)} MiB /{" "}
              {(n(data.quotaBytes) / 1e9).toFixed(0)} GB。
            </p>
            <p>
              家里备份：
              {phases[t(o(data.agentState).phase, "waiting_configuration")] ||
                t(o(data.agentState).phase)}
              。
              {data.recipientConfigured
                ? "云端已登记公钥。"
                : "云端尚未登记公钥。"}
            </p>
            <p>
              实际保留日期：
              {strings(data.retainedDates).join("、") || "尚无备份"}
            </p>
            {!list(data.items).length && (
              <Empty>
                尚无已完成的备份包；未完成上传不会显示为可恢复备份。
              </Empty>
            )}
            {list(data.items).map((item) => (
              <article key={t(item.packageId)} className="data-list-row">
                <strong>
                  {item.kind === "home" ? "家里台账/配置" : "云端数据库"} ·{" "}
                  {t(item.date)} · {(n(item.bytes) / 1048576).toFixed(2)} MiB
                </strong>
                <p>
                  <code>{t(item.packageId)}</code>
                </p>
                <div className="data-actions">
                  {[
                    "manifest.json",
                    ...list(o(item.manifest).artifacts).map((x) =>
                      t(x.name, ""),
                    ),
                  ]
                    .filter((name) => /^[\w.-]+$/.test(name))
                    .map((name) => (
                      <a
                        key={name}
                        download={name}
                        href={`/console/backups/${encodeURIComponent(t(item.packageId))}/${encodeURIComponent(name)}`}
                      >
                        下载 {name}
                      </a>
                    ))}
                  <BackupAction reader={reader} packageId={t(item.packageId)} />
                </div>
              </article>
            ))}
            {list(data.events).length > 0 && (
              <p>
                保留/容量事件：
                {list(data.events)
                  .map(
                    (x) =>
                      `${new Date(n(x.at) * 1000).toLocaleString()} ${x.code}`,
                  )
                  .join("；")}
              </p>
            )}
          </>
        ) : (
          <Empty>{busy ? "正在读取…" : "展开后按需读取备份列表"}</Empty>
        )}
      </details>
      <BackupAction reader={reader} />
    </Panel>
  );
}

export function PendingDelete({
  data,
  actions,
}: {
  data: Row;
  actions?: ReactNode;
}) {
  return (
    <Panel title="待删区">
      <dl className="data-fields">
        <Field name="项目" value={n(data.count)} />
        <Field name="占用" value={formatBytes(data.sizeBytes)} />
        <Field name="保留期" value="3 天" />
        <Field name="核验失败待复核" value={n(data.needsReview)} />
      </dl>
      <p>{t(data.note, "仅在用户确认后移入，保留期间可恢复")}</p>
      {data.nextPurgeAt ? (
        <p>最早于 {formatDateTime(data.nextPurgeAt)} 自动清除。</p>
      ) : null}
      {actions === undefined ? (
        <DisabledWrite>立即清空待删区</DisabledWrite>
      ) : (
        actions
      )}
    </Panel>
  );
}
