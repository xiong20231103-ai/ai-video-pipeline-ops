import { Button } from "@/components/ui/button";
import { useState } from "react";
import {
  object as o,
  list,
  number as n,
  text as t,
  strings,
  type Row,
} from "@/data/types";
import {
  formatClock,
  formatDateTime,
  formatAge,
  step5FilterKey,
  stageClass,
} from "@/data/legacy-formatters";
import {
  Status,
  Panel,
  Progress,
  Empty,
  Table,
  DisabledWrite,
  Field,
} from "./shared";
import { pipelineFor } from "./presentation";

export function TaskBox({
  data,
  selected,
  onSelect,
}: {
  data: Row;
  selected: string;
  onSelect: (id: string) => void;
}) {
  const payload = o(data.taskBoxes),
    boxes = list(payload.items),
    history = list(payload.history);
  const box = o(
    payload.selected || boxes.find((x) => x.batchId === selected) || boxes[0],
  );
  const current = o(box.current),
    next = o(box.next),
    projects = strings(box.selectedProjects),
    deferred = strings(box.unselectedProjects);
  return (
    <Panel
      title="任务箱总览"
      actions={
        <label className="inline-filter">
          任务箱
          <select
            aria-label="选择任务箱"
            value={t(box.batchId, "")}
            onChange={(e) => onSelect(e.target.value)}
          >
            {boxes.length ? (
              boxes.map((x) => (
                <option key={t(x.batchId)} value={t(x.batchId)}>
                  {t(x.productionDate, "未定日期")} · {t(x.completedProjects)}/
                  {t(x.projectCount)} 项
                  {x.state === "stale" ? " · 历史未完成" : ""} ·{" "}
                  {t(x.batchId).slice(-8)}
                </option>
              ))
            ) : (
              <option value="">暂无任务箱</option>
            )}
          </select>
        </label>
      }
    >
      <h3 data-legacy="taskBoxTitle">
        {box.batchId
          ? `${t(box.productionDate, "未定日期")}任务箱 · 已完成 ${box.completedProjects} / ${box.projectCount}${box.state === "stale" ? " · 历史未完成（超过 14 天）" : ""}`
          : "暂无任务箱"}
      </h3>
      <p className="data-muted" data-legacy="taskBoxScope">
        {!box.batchId
          ? "本次项目组合：当前无生产任务"
          : projects.length
            ? `本次项目组合：${projects.join("、")}${deferred.length ? `；未选择：${deferred.join("、")}` : ""}`
            : "本次项目组合：按现有任务合同运行"}
      </p>
      <dl className="data-fields">
        <Field
          name="项目进度"
          value={`${n(box.completedProjects)} / ${n(box.projectCount)}`}
          legacy="taskBoxProjectProgress"
        />
        <Field
          name="成片进度"
          value={`${n(box.completedVideos)} / ${n(box.totalVideos)}`}
          legacy="taskBoxVideoProgress"
        />
        <Field
          name="当前项目"
          legacy="taskBoxCurrent"
          value={
            box.current
              ? `${current.sequence}/${box.projectCount} ${current.project}/${current.material}`
              : box.batchId
                ? "没有正在运行的项目"
                : "--"
          }
        />
        <Field
          name="下一项目"
          legacy="taskBoxNext"
          value={
            box.next
              ? `${next.sequence}/${box.projectCount} ${next.project}/${next.material}`
              : "--"
          }
        />
      </dl>
      <Progress
        value={
          n(box.projectCount)
            ? (n(box.completedProjects) * 100) / n(box.projectCount)
            : 0
        }
      />
      <div className="taskbox-grid">
        {list(box.items).map((item) => (
          <article
            key={t(item.taskId)}
            className={`taskbox-tile ${current.taskId === item.taskId ? "is-current" : ""}`}
          >
            <header>
              <span className="sequence-number">{t(item.sequence)}</span>
              <strong>
                {t(item.project)} / {t(item.material)}
              </strong>
            </header>
            <Status state={t(item.status)}>{t(item.currentStep)}</Status>
            <p>{t(item.stateText)}</p>
            <small>
              成片 {t(item.finalCompleted)} / {t(item.expected)}
              {item.historicalFailed
                ? ` · 历史失败 ${item.historicalFailed}`
                : ""}
            </small>
          </article>
        ))}
      </div>
      {!box.batchId && <Empty>等待公司投递器提交任务</Empty>}
      {history.length > 0 && (
        <details className="data-details">
          <summary>撤回历史 {history.length}</summary>
          {history.map((x, i) => (
            <p key={i}>
              {t(x.project, "未分类")} / {t(x.material)} · {t(x.productionDate)}{" "}
              · {t(x.status, "cancelled")} · {t(x.reason, "已撤回")}
            </p>
          ))}
        </details>
      )}
    </Panel>
  );
}

export function Pipeline({
  data,
  date,
  onDate,
}: {
  data: Row;
  date: string;
  onDate: (value: string) => void;
}) {
  const pipeline = pipelineFor(data),
    payload = o(data.pipeline),
    dates = [
      ...new Set(
        [t(payload.date, date), ...strings(payload.availableDates)].filter(
          Boolean,
        ),
      ),
    ];
  return (
    <Panel
      title="全流程状态"
      actions={
        <label className="inline-filter">
          查看日期
          <select
            aria-label="全流程查看日期"
            value={t(payload.date, date)}
            onChange={(e) => onDate(e.target.value)}
          >
            {dates.map((x) => (
              <option key={x} value={x}>
                生产日期 {x}
              </option>
            ))}
          </select>
        </label>
      }
    >
      <div className="pipeline-cards">
        {["download", "voice", "stitch", "capcut", "upload"].map((key, i) => {
          const x = o(pipeline[key]);
          return (
            <article className="pipeline-tile" key={key}>
              <header>
                <span className="sequence-number">{i + 1}</span>
                <strong>
                  {["TikHub", "AI 配音", "AI 拼接", "CapCut", "网盘上传"][i]}
                </strong>
              </header>
              <Status state={t(x.state)}>{t(x.stateText, "等待")}</Status>
              <p>{t(x.current || x.source, "暂无当前任务")}</p>
              <Progress value={x.progress} />
              <small>
                {n(x.completed)} 完成 / {n(x.failed)} 失败 / {n(x.total)} 总计
                {x.todaySummary ? ` · 今日 ${x.todaySummary}` : ""}
                {n(x.testHistoryCount)
                  ? ` · 测试历史 ${n(x.testHistoryCount)} 条（不计生产）`
                  : ""}
              </small>
            </article>
          );
        })}
      </div>
      <Table
        headings={[
          "步骤",
          "程序",
          "当前任务 / 子阶段",
          "进度",
          "完成 / 失败 / 总计",
          "最后更新",
          "状态",
        ]}
      >
        {["download", "voice", "stitch", "capcut", "upload"].map((key) => {
          const x = o(pipeline[key]);
          return (
            <tr key={key}>
              <td>
                {t(x.step, "")} {t(x.name, key)}
              </td>
              <td>
                {t(x.program)}
                <small>
                  {x.state === "unconfigured"
                    ? "尚未接入"
                    : x.programOnline
                      ? "程序运行中"
                      : "程序未运行"}
                </small>
              </td>
              <td>
                {[
                  t(x.current || x.todaySummary || x.source, "暂无当前任务"),
                  t(x.phaseText || x.currentPhase, ""),
                ]
                  .filter(Boolean)
                  .join(" · ")}
                <small>
                  {t(x.source, "")}
                  {n(x.testHistoryCount)
                    ? `；测试历史 ${n(x.testHistoryCount)} 条（不计生产）`
                    : ""}
                </small>
              </td>
              <td>{n(x.progress)}%</td>
              <td>
                {n(x.completed)} / {n(x.failed)} / {n(x.total)}
              </td>
              <td>
                {formatDateTime(x.updatedAt)}
                <small>
                  {x.state === "running"
                    ? x.isLive
                      ? "实时更新"
                      : "状态未刷新"
                    : formatAge(x.ageSeconds)}
                </small>
              </td>
              <td>
                <Status state={stageClass(x.state)}>
                  {t(x.stateText, "等待")}
                </Status>
              </td>
            </tr>
          );
        })}
      </Table>
      <DownloadFailures download={o(pipeline.download)} />
    </Panel>
  );
}
function DownloadFailures({ download }: { download: Row }) {
  const items = list(download.failureItems),
    failed = Math.max(n(download.failed), items.length);
  if (!failed) return null;
  return (
    <div className="data-notice tone-danger">
      <strong>下载 / 去字幕失败任务 · {failed} 条</strong>
      <p>这些链接未进入后续语音、拼接与剪辑；补链或重试后再继续。</p>
      <ul>
        {items.length ? (
          items.slice(0, 8).map((x, i) => (
            <li key={i}>
              <code>{t(x.url, "未记录链接")}</code> ·{" "}
              {t(x.reason, "下载或 AI 去字幕失败")}
            </li>
          ))
        ) : (
          <li>
            已记录 {failed}{" "}
            条失败；请在本页任务箱展开对应材料，查看原因并直接补链。
          </li>
        )}
      </ul>
    </div>
  );
}

export function Tasks({ data }: { data: Row }) {
  const [filter, setFilter] = useState(""),
    items = list(o(data.tasks).items),
    filters = new Map(
      items.map((x) => [
        step5FilterKey(x),
        `${t(x.project, "未分类")} / ${t(x.material)}`,
      ]),
    );
  const effective = filters.has(filter) ? filter : "",
    shown = items.filter((x) => !effective || step5FilterKey(x) === effective);
  const counts = {
    total: shown.length,
    waiting: 0,
    running: 0,
    completed: 0,
    failed: 0,
  };
  for (const row of shown) {
    const key = t(row.category, "") as keyof typeof counts;
    if (key in counts && key !== "total") counts[key]++;
  }
  const groups = new Map<string, Row[]>();
  for (const row of shown) {
    const key = `${t(row.project, "未分类")} / ${t(row.material)}`;
    groups.set(key, [...(groups.get(key) || []), row]);
  }
  return (
    <Panel
      title="第五步任务与进度"
      actions={
        <label className="inline-filter">
          查看
          <select
            aria-label="筛选第五步项目"
            value={effective}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="">全部项目</option>
            {[...filters].map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
      }
    >
      <div className="count-strip">
        {Object.entries(counts).map(([key, value], i) => (
          <div key={key}>
            <small>{["总任务", "等待", "剪辑中", "已完成", "失败"][i]}</small>
            <strong data-legacy={`count${key[0].toUpperCase() + key.slice(1)}`}>
              {value}
            </strong>
          </div>
        ))}
      </div>
      {!shown.length ? (
        <Empty>这个生产日期暂时没有第五步任务</Empty>
      ) : (
        [...groups].map(([name, group]) => (
          <div key={name} className="task-group">
            <h3>
              {name}
              <small>
                {group.filter((x) => x.category === "completed").length} /{" "}
                {group.length} 完成
              </small>
            </h3>
            <Table
              headings={[
                "项目",
                "材料 / 语言",
                "编号",
                "当前阶段",
                "成片文件",
                "状态",
              ]}
            >
              {group.map((x, i) => (
                <tr key={t(x.task_id, String(i))}>
                  <td>
                    <strong>{t(x.project, "未分类")}</strong>
                    <small>{t(x.date_label, "")}</small>
                  </td>
                  <td>
                    {t(x.material)}
                    <small>{t(x.language)}</small>
                  </td>
                  <td>
                    {t(x.number)}
                    {x.sequence ? `-${x.sequence}` : ""}
                  </td>
                  <td>
                    {t(x.phase_text || x.state_text || x.phase || x.state)}
                    <small>
                      {x.heartbeat_at
                        ? `心跳 ${formatClock(x.heartbeat_at)}`
                        : ""}
                    </small>
                  </td>
                  <td>
                    {t(x.output_name, "尚未生成")}
                    <small>{t(x.video_name, "")}</small>
                  </td>
                  <td>
                    <Status state={t(x.category)}>
                      {x.category === "running" ? "处理中" : t(x.state_text)}
                    </Status>
                  </td>
                </tr>
              ))}
            </Table>
          </div>
        ))
      )}
    </Panel>
  );
}

export function GapsAndQueue({
  data,
  actions,
}: {
  data: Row;
  actions?: {
    available: boolean;
    control: (row: Row, action: "start" | "cancel") => void;
    replenish: (row: Row) => void;
    create: () => void;
  };
}) {
  const gaps = list(o(data.projectGaps).items),
    queue = list(o(data.receiverQueue).items);
  const recent = (x: Row) =>
    x.status === "pending_confirmation" ||
    Date.now() - Date.parse(t(x.importedAt || x.createdAt, "")) <
      3 * 24 * 3600 * 1000;
  const renderQueue = (items: Row[]) =>
    items.map((x, i) => (
      <article key={t(x.taskId, String(i))} className="data-list-row">
        <strong>
          {t(x.project, "未分类")} / {t(x.material)}
        </strong>
        <Status>{t(x.status, "")}</Status>
        <p>
          {t(x.date)} ·{" "}
          {x.batchId
            ? `第 ${x.batchSequence || 1} / ${x.batchSize || 1} 项`
            : "单条任务"}{" "}
          · {Array.isArray(x.urls) ? x.urls.length : 0} 条链接
        </p>
        <div className="data-actions">
          {x.status === "pending_confirmation" &&
            !["auto_start_first", "auto_start_sequential"].includes(
              t(x.startMode),
            ) &&
            (actions ? (
              <Button
                disabled={!actions.available}
                onClick={() => actions.control(x, "start")}
              >
                启动首项
              </Button>
            ) : (
              <DisabledWrite>启动首项</DisabledWrite>
            ))}
          {["pending_confirmation", "imported_waiting_start"].includes(
            t(x.status),
          ) &&
            (actions ? (
              <Button
                variant="outline"
                disabled={!actions.available}
                onClick={() => actions.control(x, "cancel")}
              >
                撤回
              </Button>
            ) : (
              <DisabledWrite>撤回</DisabledWrite>
            ))}
        </div>
      </article>
    ));
  return (
    <>
      <Panel title="项目状态">
        {!gaps.length && <Empty>暂无项目级下载记录</Empty>}
        {gaps.map((x, i) => {
          const missing =
            x.missingCount !== undefined &&
            x.missingCount !== null &&
            x.missingCount !== ""
              ? n(x.missingCount)
              : Math.max(0, n(x.expectedCount) - n(x.completed));
          const videos = Object.values(o(x.videos)).map(o);
          return (
            <article className="data-list-row" key={t(x.taskId, String(i))}>
              <header>
                <strong>
                  {t(x.project, "未分类")} / {t(x.material)}
                </strong>
                <span>{t(x.date)}</span>
              </header>
              <p>
                {x.notStarted
                  ? `计划 ${n(x.expectedCount)} · 尚未开始`
                  : `总数 ${n(x.expectedCount)} · 已完成 ${n(x.completed)} · 剩余 ${missing} · 当前失败 ${n(x.failed)}`}
              </p>
              <small>
                {t(x.stateText || x.status)}
                {x.currentTask ? ` · 当前 ${x.currentTask}` : ""}
                {x.error ? ` · 错误 ${x.error}` : ""}
              </small>
              {n(x.historicalFailed) > 0 && (
                <p>历史失败 {n(x.historicalFailed)} 条，已被有效补链覆盖</p>
              )}
              {x.gapActive && x.taskId ? (
                actions ? (
                  <Button
                    disabled={!actions.available}
                    onClick={() => actions.replenish(x)}
                  >
                    按此缺口补链
                  </Button>
                ) : (
                  <DisabledWrite>按此缺口补链</DisabledWrite>
                )
              ) : null}
              {videos.length > 0 && (
                <details>
                  <summary>查看 {videos.length} 条任务状态</summary>
                  <Table headings={["链接", "阶段", "状态"]}>
                    {videos.map((v, j) => (
                      <tr key={j}>
                        <td>{t(v.url)}</td>
                        <td>{t(v.stage, "waiting")}</td>
                        <td>{t(v.error || v.message || v.status, "等待")}</td>
                      </tr>
                    ))}
                  </Table>
                </details>
              )}
            </article>
          );
        })}
      </Panel>
      <Panel title="任务确认与撤回">
        <p className="data-muted">
          只影响尚未开始的队列记录；不会删除视频、音频或素材。
        </p>
        {!queue.length ? (
          <Empty>暂无可确认或撤回的队列任务</Empty>
        ) : (
          <>
            {renderQueue(queue.filter(recent))}
            {!queue.some(recent) && (
              <Empty>最近 3 天没有需要确认或撤回的任务</Empty>
            )}
            {queue.some((x) => !recent(x)) && (
              <details>
                <summary>
                  更早导入的 {queue.filter((x) => !recent(x)).length}{" "}
                  条任务（超过 3 天，通常无需操作）
                </summary>
                {renderQueue(queue.filter((x) => !recent(x)))}
              </details>
            )}
          </>
        )}
        {actions ? (
          <Button disabled={!actions.available} onClick={actions.create}>
            新建项目任务
          </Button>
        ) : (
          <DisabledWrite>新建项目任务</DisabledWrite>
        )}
      </Panel>
    </>
  );
}
