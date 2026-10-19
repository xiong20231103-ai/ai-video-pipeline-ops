import { ReadClient } from "./client";
import { uploadWriterFor } from "./upload-writer";
import { localReceipts, pendingStates } from "./receipts";
import { list, object, text, type Row } from "./types";
import { runtimeFacts } from "./legacy-formatters";
import { commandLabels } from "@/components/views/presentation";

export const continuePhases = new Set([
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
]);
export function continueInFlight(result: Row) {
  return (
    !result.stale &&
    continuePhases.has(String(result.state)) &&
    result.continueCanRetry !== true
  );
}
export function expectedContinueTarget(data: Row) {
  const box = object(data.currentTaskBox),
    current = object(box.current);
  return Object.fromEntries(
    Object.entries({
      batchId: box.batchId,
      taskId: current.taskId,
      attemptId: current.attemptId,
    }).filter(([, value]) => typeof value === "string" && value),
  );
}
export class SafeContinue {
  private eligibility = new Map<
    string,
    { allowed: boolean; retry: unknown; reason: unknown; at: number }
  >();
  private specific: Row | null = null;
  private sending = false;
  private failures = 0;
  constructor(
    readonly reader: ReadClient,
    readonly now = () => performance.now(),
  ) {}
  private record() {
    return [...localReceipts()]
      .reverse()
      .find((r) => r.path === "/api/control-commands");
  }
  target() {
    if (this.reader.mode !== "cloud") return "/api/control-commands/current";
    const record = this.record();
    if (record && pendingStates.has(String(record.state))) return null;
    return record?.homeCommandId
      ? "/api/control-commands/" +
          encodeURIComponent(String(record.homeCommandId))
      : "/api/control-commands/current";
  }
  observe(raw: Row, health: Row, statusResponse = false): Row {
    if (statusResponse) this.failures = 0;
    if (this.reader.mode !== "cloud") return raw;
    let result = raw,
      observed = true;
    const record = this.record();
    if (record && pendingStates.has(String(record.state)))
      return {
        ...result,
        state: record.state,
        allowed: false,
        continueCanRetry: false,
        message: commandLabels[String(record.state)],
        cloudCommandId: record.cloudCommandId,
      };
    if (record?.homeCommandId && result.commandId !== record.homeCommandId) {
      observed = false;
      result =
        this.specific?.commandId === record.homeCommandId
          ? this.specific
          : {
              commandId: record.homeCommandId,
              state: "persisted",
              allowed: false,
              message: "正在按原命令编号查询业务状态",
            };
    } else if (record?.homeCommandId === result.commandId)
      this.specific = result;
    const identity = String(result.commandId || "");
    if (observed && typeof result.allowed === "boolean")
      this.eligibility.set(identity, {
        allowed: result.allowed,
        retry: result.continueCanRetry,
        reason: result.continueLockReason,
        at: this.now(),
      });
    return this.display(result, health);
  }
  display(raw: Row, health: Row): Row {
    if (this.failures >= 2)
      return {
        allowed: false,
        state: "offline",
        message: "无法读取安全继续状态；正在自动重连",
      };
    if (this.reader.mode !== "cloud") return raw;
    const record = this.record();
    if (record && pendingStates.has(String(record.state)))
      return {
        ...raw,
        state: record.state,
        allowed: false,
        continueCanRetry: false,
        message: commandLabels[String(record.state)],
        cloudCommandId: record.cloudCommandId,
      };
    const proof = this.eligibility.get(String(raw.commandId || "")),
      fresh = Boolean(proof && this.now() - proof.at <= 10000);
    return {
      ...raw,
      ...(fresh
        ? { continueCanRetry: proof?.retry, continueLockReason: proof?.reason }
        : {}),
      allowed:
        fresh &&
        proof?.allowed === true &&
        health.canContinue === true &&
        !health.commandBlocker,
    };
  }
  needsPoll() {
    return this.failures >= 2;
  }
  failed() {
    this.failures++;
  }
  state(data: Row, health: Row) {
    const result = this.display(object(object(data.controls).continue), health),
      inFlight = continueInFlight(result);
    const facts = runtimeFacts(
        list(data.services),
        object(data.currentProjectStatus),
      ),
      runtimeBusy = !inFlight && Boolean(facts.busy);
    const clickable =
      this.failures < 2 &&
      !this.sending &&
      result.allowed !== false &&
      !runtimeBusy &&
      (result.continueCanRetry === true || !inFlight) &&
      (this.reader.mode === "home" ||
        (health.canContinue === true &&
          uploadWriterFor(this.reader, () => health).available()));
    const state = String(result.state || "idle");
    const label =
      this.failures >= 2
        ? "状态服务离线，正在重连…"
        : this.sending
          ? "正在发送继续指令…"
          : runtimeBusy
            ? "流水线正在运行，无需点击"
            : ["requested", "persisted"].includes(state)
              ? "命令已保存，等待接收器…"
              : state === "receiver_acknowledged"
                ? "接收器已收到，等待工作台…"
                : ["accepted", "workbench_acknowledged"].includes(state)
                  ? "工作台已接收，正在核对…"
                  : ["running", "recovering", "executing"].includes(state)
                    ? "正在安全继续，请勿重复点击…"
                    : "安全继续当前项目";
    const title =
      this.failures >= 2
        ? "Dashboard或任务接收器暂时不可用，恢复连接后会自动重新对账"
        : runtimeBusy
          ? "工作台正在自动处理当前项目（下载/语音/CapCut），点击不会启动任何新步骤；运行结束或出现阻断后按钮会恢复"
          : inFlight
            ? text(
                result.continueLockReason || result.message,
                "继续命令正在执行，请等待状态更新",
              )
            : result.allowed === false
              ? text(result.message, "接收器状态未对账")
              : "";
    return { result, inFlight, runtimeBusy, clickable, label, title };
  }
  async submit(
    data: Row,
    health: Row,
    confirm = window.confirm.bind(window),
  ): Promise<Row | null> {
    if (!this.state(data, health).clickable)
      throw new Error("安全继续尚未获得资格或存在运行中命令；尚未提交");
    if (
      !confirm(
        "确认让家里工作台安全继续当前项目吗？它会先核对任务清单，不会删除素材或重做有效成片。",
      )
    )
      return null;
    if (!this.state(data, health).clickable)
      throw new Error("确认期间资格已失效，请重新对账");
    this.sending = true;
    try {
      const expectedTarget = expectedContinueTarget(data),
        clientRequestId =
          window.crypto?.randomUUID?.() ||
          `dashboard-${Date.now()}-${Math.random()}`;
      const body = Object.keys(expectedTarget).length
        ? { clientRequestId, expectedTarget }
        : { clientRequestId };
      const result = await uploadWriterFor(this.reader, () => health).post(
        "/api/control-commands",
        body,
      );
      return {
        ...result,
        state: result.state || "persisted",
        message: result.message || "命令已保存，等待家里接收器确认",
        requestedAt: new Date().toISOString(),
      };
    } finally {
      this.sending = false;
    }
  }
}
const controllers = new WeakMap<ReadClient, SafeContinue>();
export function safeContinueFor(reader: ReadClient) {
  let controller = controllers.get(reader);
  if (!controller) {
    controller = new SafeContinue(reader);
    controllers.set(reader, controller);
  }
  return controller;
}
