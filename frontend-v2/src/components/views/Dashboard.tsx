import { replenishmentQueueStatus } from "@/data/replenishment-status";
import { CountUp } from "@/components/react-bits/Motion";
import ResetAction from "./ResetAction";
import ContinueActions from "./ContinueActions";
import FileManagers from "./FileManagers";
import { uploadWriterFor } from "@/data/upload-writer";
import TaskOperations from "./TaskOperations";
import type { ReadClient } from "@/data/client";
import { UploadActions } from "./UploadActions";
import { useState } from "react";
import {
  object as o,
  list,
  text as t,
  number as n,
  type Row,
  type Snapshot,
} from "@/data/types";
import { useDashboard } from "@/data/useDashboard";
import {
  formatClock,
  formatDateTime,
  formatAge,
  ageFromTime,
  runtimeFacts,
  nextActionFor,
  describeSourceErrors,
  safetyEntries,
} from "@/data/legacy-formatters";
import type { View } from "@/lib/preferences";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Panel, Status, Progress, Field, Empty } from "./shared";
import {
  heroFor,
  metricValues,
  uploadValues,
  currentValues,
  pipelineFor,
  continueLabels,
} from "./presentation";
import { TaskBox, Pipeline, Tasks } from "./TaskViews";
import { BackupPanel, SourcePanel, CommandList, Freshness } from "./CloudViews";

function Current({ current }: { current: Row }) {
  const fields = currentValues(current);
  return (
    <Panel
      title="当前第五步任务"
      actions={
        <Status state={fields.category}>
          <span data-legacy="currentState">{fields.currentState}</span>
        </Status>
      }
    >
      <dl className="data-fields">
        {(["Date", "Project", "Material", "Language"] as const).map(
          (key, i) => (
            <Field
              key={key}
              name={["日期", "项目", "材料", "语言"][i]}
              legacy={`current${key}`}
              value={fields[`current${key}`]}
            />
          ),
        )}
      </dl>
      {fields.currentError && (
        <p role="alert" data-legacy="currentError">
          {fields.currentError}
        </p>
      )}
    </Panel>
  );
}
function Runtime({ data }: { data: Row }) {
  const facts = runtimeFacts(list(data.services), o(data.currentProjectStatus));
  const next =
    facts.busy || facts.offline
      ? null
      : nextActionFor(o(data.currentProjectStatus));
  if (facts.offline)
    return (
      <div className="data-notice tone-danger">
        <strong>工作台已离线，生产实际已停止</strong>
        <p>
          当前项目{facts.projectLabel ? `（${facts.projectLabel}）` : ""}
          显示为运行中，但工作台没有在运行。点击“安全继续当前项目”会自动启动工作台，并从断点继续。
        </p>
      </div>
    );
  if (facts.workbench && facts.capcut)
    return (
      <div className="data-notice tone-warning">
        <strong>CapCut 正在自动剪辑：请勿操作这台电脑</strong>
        <p>
          剪映需要独占前台，移动鼠标、敲键盘或切换窗口都会让它失败。即使出现失败，客户端也会先自动重试，无需马上点击安全继续。
        </p>
      </div>
    );
  if (facts.workbench && facts.voice)
    return (
      <div className="data-notice tone-warning">
        <strong>正在生成语音：请勿切换或关闭 Fish Audio 页面</strong>
        <p>Fish 页面需要保持在文本转语音页，并保持窗口最大化。</p>
      </div>
    );
  return next ? (
    <div className="data-notice tone-warning">
      <strong>{next.title}</strong>
      <p>
        原因：{next.reasons.slice(0, 3).join("；")}
        {next.reasons.length > 3
          ? `（另有 ${next.reasons.length - 3} 条）`
          : ""}
      </p>
      <p>{next.action}</p>
    </div>
  ) : null;
}
function Safety({ data }: { data: Row }) {
  return (
    <Panel
      title="生产安全"
      actions={<small>最后检查 {formatDateTime(data.updatedAt)}</small>}
    >
      <div className="safety-tiles">
        {safetyEntries(data).map((x) => (
          <article key={x.title}>
            <header>
              <strong>{x.title}</strong>
              <Status state={x.tone}>
                {x.tone === "good"
                  ? "正常"
                  : x.tone === "blocked"
                    ? "阻止"
                    : "需留意"}
              </Status>
            </header>
            <p>{x.text}</p>
          </article>
        ))}
      </div>
      <p className="data-muted">
        本区域全部来自本机确定性检查，正常查询消耗 0 模型 Token。
      </p>
    </Panel>
  );
}
function Health({ data }: { data: Row }) {
  const commands = list(data.openCommands),
    errors = list(data.recentErrors),
    stuck = commands.filter(
      (x) => n(x.ageSeconds) > 600 || x.state === "reconciliation_required",
    );
  return (
    <Panel
      motionId="system-health"
      title={
        !data.updatedAt
          ? "系统健康 · 状态暂不可用"
          : stuck.length
            ? `系统健康 · ${stuck.length} 条安全继续命令未结束`
            : errors.length
              ? `系统健康 · 最近 24 小时 ${errors.length} 类报错`
              : "系统健康 · 正常"
      }
    >
      {!data.updatedAt ? (
        <Empty>尚无可信健康数据，不能判为正常</Empty>
      ) : (
        <div className="data-columns">
          <div>
            <h3>安全继续命令</h3>
            {commands.length ? (
              commands.map((x, i) => (
                <div className="data-list-row" key={i}>
                  <strong>
                    {t(x.step)} · {t(x.state, "")}
                  </strong>
                  <p>{t(x.taskId || x.commandId)}</p>
                  <small>
                    已持续 {formatAge(x.ageSeconds).replace("前", "")}
                  </small>
                </div>
              ))
            ) : (
              <p>没有未结束的安全继续命令</p>
            )}
          </div>
          <div>
            <h3>工作台最近报错</h3>
            {errors.length ? (
              errors.map((x, i) => (
                <div className="data-list-row" key={i}>
                  <strong>
                    {t(x.lastAt, "").slice(5, 16).replace("T", " ")}
                  </strong>
                  <p>{t(x.message, "")}</p>
                  {n(x.count) > 1 && <small>{n(x.count)} 次</small>}
                </div>
              ))
            ) : (
              <p>
                {data.logAvailable === false
                  ? "未找到工作台日志文件"
                  : "最近 24 小时工作台日志没有报错"}
              </p>
            )}
          </div>
        </div>
      )}
    </Panel>
  );
}
function ServicesAndSources({ data }: { data: Row }) {
  const source = o(data.sources),
    messages: string[] = [];
  if (source.stale) messages.push("Dashboard采集状态已经过期");
  if (source.receiverError)
    messages.push(`接收器状态读取失败：${source.receiverError}`);
  if (o(source.watchdog).state === "failed")
    messages.push(
      `Dashboard守护启动失败：${t(o(source.watchdog).message, "原因未知")}`,
    );
  messages.push(...describeSourceErrors(list(source.errors)).slice(0, 5));
  const processes = o(o(o(data.overview).metrics).processes);
  return (
    <Panel title="服务运行状态">
      <div className="data-actions">
        {["workbench", "voice", "capcut"].map((key, i) => (
          <Status key={key} state={processes[key] ? "online" : "offline"}>
            {["工作台", "语音客户端", "CapCut客户端"][i]} ·{" "}
            {processes[key] ? "运行中" : "未运行"}
          </Status>
        ))}
      </div>
      <div className="service-tiles">
        {list(data.services).map((x, i) => (
          <article key={t(x.key, String(i))}>
            <strong>{t(x.name)}</strong>
            <Status state={x.online ? "online" : "offline"}>
              {t(x.stateText, x.online ? "运行中" : "未运行")}
            </Status>
            <small>{ageFromTime(x.updatedAt)}</small>
          </article>
        ))}
      </div>
      {messages.length > 0 && (
        <div className="data-notice tone-warning">
          <strong>状态源提醒</strong>
          <ul>
            {messages.map((message, i) => (
              <li key={i}>{message}</li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  );
}
function Result({ result, fallback }: { result: Row; fallback: string }) {
  return (
    <p className="operation-result">
      <Status state={t(result.state, "")}>{t(result.state, "尚无记录")}</Status>
      {t(result.message, fallback)}
      {result.updatedAt ? ` · ${formatDateTime(result.updatedAt)}` : ""}
    </p>
  );
}
function Upload({
  data,
  snapshot,
  reader,
  refresh,
}: {
  data: Row;
  snapshot: Snapshot;
  reader: ReadClient | null;
  refresh: () => void;
}) {
  const upload = o(pipelineFor(data).upload),
    values = uploadValues(upload),
    controls = o(data.controls),
    history = o(controls.historicalCloudVerification),
    total = n(history.total ?? history.eligible);
  return (
    <Panel
      title="最终成片上传"
      actions={
        <Status state={t(upload.state)}>
          <span data-legacy="uploadCardBadge">{values.badge}</span>
        </Status>
      }
    >
      <h3 data-legacy="uploadCardTitle">{values.title}</h3>
      <p data-legacy="uploadCardMessage">{values.message}</p>
      {values.live && (
        <>
          <div className="upload-heading">
            <strong data-legacy="uploadProgressLabel">{values.label}</strong>
            <span data-legacy="uploadProgressPercent">{values.percentage}</span>
          </div>
          <Progress value={values.percent} />
          <dl className="data-fields">
            <Field
              name="已上传 / 总量"
              value={values.bytes}
              legacy="uploadBytesText"
            />
            <Field
              name="实时估算速度"
              value={values.speed}
              legacy="uploadSpeedText"
            />
            <Field
              name="剩余"
              value={values.remaining}
              legacy="uploadRemainingText"
            />
            <Field name="预计完成" value={values.eta} legacy="uploadEtaText" />
          </dl>
          <p data-legacy="uploadCurrentFile">{values.file}</p>
        </>
      )}
      <UploadActions snapshot={snapshot} reader={reader} refresh={refresh} />
      <Result result={o(controls.uploadRescan)} fallback="尚无操作记录" />
      <Result
        result={{
          ...history,
          message: `${t(history.message, "尚未核验历史百度云文件")}${total ? ` · ${n(history.processed)}/${total}，通过 ${n(history.verified)}，失败 ${n(history.failed)}` : ""}`,
        }}
        fallback="尚未核验历史百度云文件"
      />
    </Panel>
  );
}
function ContinueStatus({
  onReset,
  data,
  snapshot,
  reader,
  onResult,
  refresh,
}: {
  onReset: () => void;
  data: Row;
  snapshot: Snapshot;
  reader: ReadClient | null;
  onResult: (value: Row) => void;
  refresh: () => void;
}) {
  const result = o(o(data.controls).continue),
    state = t(result.state, "idle");
  const inFlight =
    [
      "submitting",
      "queued",
      "leased",
      "sent",
      "unknown",
      "requested",
      "accepted",
      "running",
      "recovering",
      "persisted",
      "receiver_acknowledged",
      "workbench_acknowledged",
      "executing",
    ].includes(state) &&
    !result.stale &&
    result.continueCanRetry !== true;
  const launchState = result.workbenchReady
    ? "工作台已确认就绪"
    : result.workbenchAlreadyRunning
      ? "正在复用已运行的工作台"
      : result.workbenchStartPending
        ? "工作台正在启动"
        : result.workbenchStarted
          ? "工作台已启动，等待接收指令"
          : "";
  return (
    <Panel title="安全继续与对账">
      <div className="data-actions">
        <ContinueActions
          snapshot={snapshot}
          reader={reader}
          onResult={onResult}
          refresh={refresh}
        />
        <ResetAction
          reader={reader}
          onReset={onReset}
          initialResult={o(o(data.controls).resetRecords)}
        />
      </div>
      <Status state={state}>
        {continueLabels[state] || state}
        {result.stale ? " · 结果已过期" : ""}
      </Status>
      <p>{formatDateTime(result.finishedAt || result.requestedAt)}</p>
      <p>{t(result.message, "尚未执行安全继续对账")}</p>
      {result.commandId ? (
        <p>
          命令编号：<code>{t(result.commandId)}</code>
          {inFlight ? " · 请勿重复点击" : ""}
        </p>
      ) : null}
      {result.bridgeState ? (
        <p>
          Fish桥接：{t(result.bridgeState)}
          {result.bridgePort ? ` · 端口 ${n(result.bridgePort)}` : ""}
          {result.bridgePid ? ` · PID ${n(result.bridgePid)}` : ""}
          {result.bridgeMessage ? ` · ${result.bridgeMessage}` : ""}
        </p>
      ) : null}
      <dl className="data-fields">
        {list(result.steps).map((x, i) => (
          <Field
            key={i}
            name={`${x.step}. ${x.name}`}
            value={`${n(x.actual)} / ${n(x.expected)}`}
          />
        ))}
      </dl>
      {launchState && (
        <p>
          {launchState}
          {result.workbenchPid ? `（PID ${n(result.workbenchPid)}）` : ""}
        </p>
      )}
      {inFlight && result.workbenchLaunchError ? (
        <p role="alert">
          工作台启动失败
          {result.workbenchLaunchCode
            ? `（${result.workbenchLaunchCode}）`
            : ""}
          ：{t(result.workbenchLaunchError)}
          {result.workbenchLaunchLog
            ? `；日志：${result.workbenchLaunchLog}`
            : ""}
        </p>
      ) : null}
    </Panel>
  );
}
function Events({ data }: { data: Row }) {
  const items = list(o(data.events).items);
  return (
    <Panel title="最近事件">
      {!items.length && <Empty>暂无事件</Empty>}
      {items.slice(0, 20).map((x, i) => (
        <article className="data-list-row" key={i}>
          <Status state={t(x.severity, "INFO").toLowerCase()}>
            {t(x.severity, "INFO")}
          </Status>
          <strong>{t(x.message, "")}</strong>
          <small>{formatClock(x.created_at)}</small>
        </article>
      ))}
    </Panel>
  );
}

export default function Dashboard({ view }: { view: View }) {
  const [date, setDate] = useState(""),
    [batchId, setBatch] = useState("");
  const [replenishment, setReplenishment] = useState<Row | null>(null);
  const { snapshot, reader, refresh, acceptContinueResult } = useDashboard(
    date,
    batchId,
  );
  const data = snapshot.dashboard;
  const canWrite = reader.current
    ? uploadWriterFor(reader.current, () => snapshot.status).available()
    : false;
  return (
    <div className="dashboard-content">
      <div className="data-toolbar">
        <Status state={snapshot.mode ? "healthy" : "unknown"}>
          {snapshot.mode === "cloud"
            ? "云端缓存模式"
            : snapshot.mode === "home"
              ? "家里模式"
              : "正在确认运行模式"}
        </Status>
        <span>V2 独立预览：操作资格由当前模式与服务状态决定</span>
        <Button variant="outline" size="sm" onClick={refresh}>
          刷新
        </Button>
      </div>
      <Freshness snapshot={snapshot} />
      {snapshot.error && (
        <div className="data-notice tone-warning" role="alert">
          {snapshot.error}
        </div>
      )}
      {snapshot.loading && !data && (
        <Skeleton className="data-loading" aria-label="正在读取看板" />
      )}
      {data && (
        <>
          <Runtime data={data} />
          {view === "overview" && (
            <>
              <Overview
                data={data}
                snapshot={snapshot}
                canWrite={canWrite}
                onReplenish={(row) => {
                  setReplenishment(row);
                  window.location.hash = "tasks";
                }}
              />
              <TaskBox
                data={data}
                selected={batchId}
                onSelect={(value) => {
                  setBatch(value);
                  setDate("");
                }}
              />
              <Pipeline data={data} date={date} onDate={setDate} />
              <Safety data={snapshot.safety} />
            </>
          )}
          {view === "tasks" && (
            <>
              <TaskBox
                data={data}
                selected={batchId}
                onSelect={(value) => {
                  setBatch(value);
                  setDate("");
                }}
              />
              <Pipeline data={data} date={date} onDate={setDate} />
              <Tasks data={data} />
              <Current current={o(o(data.overview).current)} />
              <TaskOperations
                snapshot={snapshot}
                reader={reader.current}
                refresh={refresh}
                replenishment={replenishment}
                onReplenishment={setReplenishment}
              />
            </>
          )}
          {view === "uploads" && (
            <Upload
              data={data}
              snapshot={snapshot}
              reader={reader.current}
              refresh={refresh}
            />
          )}
          {view === "files" && (
            <FileManagers
              snapshot={snapshot}
              reader={reader.current}
              refresh={refresh}
            />
          )}
          {view === "commands" && (
            <>
              <ContinueStatus
                data={data}
                snapshot={snapshot}
                reader={reader.current}
                onReset={() => {
                  setDate("");
                  setBatch("");
                  refresh();
                }}
                onResult={acceptContinueResult}
                refresh={refresh}
              />
              {snapshot.mode === "cloud" && (
                <CommandList
                  items={snapshot.commands}
                  reader={reader.current}
                  refresh={refresh}
                />
              )}
            </>
          )}
          {view === "health" && (
            <>
              <ServicesAndSources data={data} />
              <Health data={o(data.health)} />
              <Safety data={snapshot.safety} />
              <Events data={data} />
            </>
          )}
          {snapshot.mode === "cloud" && (
            <>
              <SourcePanel snapshot={snapshot} reader={reader.current} />
              {view === "health" && <BackupPanel reader={reader.current} />}
            </>
          )}
        </>
      )}
    </div>
  );
}

function Overview({
  data,
  snapshot,
  canWrite,
  onReplenish,
}: {
  data: Row;
  snapshot: Snapshot;
  canWrite: boolean;
  onReplenish: (row: Row) => void;
}) {
  const overview = o(data.overview),
    machine = o(overview.machine),
    hero = heroFor(data),
    metrics = metricValues(o(overview.metrics));
  return (
    <>
      <GapQuickHint data={data} canWrite={canWrite} onReplenish={onReplenish} />
      <Panel
        title="当前生产状态"
        className="overview-hero"
        actions={
          <Status state={machine.online ? "online" : "offline"}>
            <span data-legacy="machineBadge">
              {t(machine.name)} · {machine.online ? "在线" : "离线"}
            </span>
          </Status>
        }
      >
        <h2 data-legacy="heroTitle">{hero.title}</h2>
        <p data-legacy="heroSubtitle">{hero.subtitle}</p>
        <small data-legacy="footerMachine">
          {t(machine.name)} · {t(machine.status)}
        </small>
        <small>
          {snapshot.mode === "cloud"
            ? "访问、控制、备份、通知；计算仍在家里"
            : "监控与安全控制中心"}
        </small>
      </Panel>
      <div className="resource-grid">
        {metrics.map((x) => (
          <Panel key={x.key} title={x.label}>
            <strong className="resource-value">
              <span className="sr-only" data-legacy={`${x.key}Value`}>
                {x.value}
              </span>
              <CountUp value={x.value} />
            </strong>
            <Progress value={x.progress} />
            <small data-legacy={`${x.key}Note`}>{x.note}</small>
          </Panel>
        ))}
      </div>
    </>
  );
}

function GapQuickHint({
  data,
  canWrite,
  onReplenish,
}: {
  data: Row;
  canWrite: boolean;
  onReplenish: (row: Row) => void;
}) {
  const active = list(o(data.projectGaps).items).filter(
    (x) => x.gapActive && String(x.taskId || ""),
  );
  if (!active.length) return null;
  const queue = o(data.receiverQueue).error ? [] : list(o(data.receiverQueue).items);
  const received = active.filter(x => replenishmentQueueStatus(x, queue).queued > 0).length;
  const missing = (row: Row) =>
    n(row.missingCount ?? Math.max(0, n(row.expectedCount) - n(row.completed)));
  return (
    <div className="data-notice tone-warning">
      <strong>
        {received ? `${active.length} 个项目仍有素材缺口 · ${received} 个已收到补链` : active.length === 1
          ? "当前项目需要补链"
          : `${active.length} 个项目需要补链`}
      </strong>
      <p>
        合计缺少 {active.reduce((sum, row) => sum + missing(row), 0)}{" "}
        条；已收到的补链等待下载核验，请勿重复补交
      </p>
      <div className="data-actions">
        {active.map((x, i) => (
          <Button key={i} disabled={!canWrite || replenishmentQueueStatus(x, queue).queued > 0} onClick={() => onReplenish(x)}>
            {t(x.project, "未分类")} / {t(x.material)} · {replenishmentQueueStatus(x, queue).message || `缺 ${missing(x)} 条`}
          </Button>
        ))}
      </div>
    </div>
  );
}
