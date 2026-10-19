import { ReadClient } from "./client";
import {
  captureReceipt,
  localReceipts,
  pendingStates,
  saveReceipts,
} from "./receipts";
import { object, text, type Row } from "./types";

export class CommandAdmin {
  private busy = false;
  constructor(
    readonly reader: ReadClient,
    readonly confirm = window.confirm.bind(window),
    readonly prompt = window.prompt.bind(window),
  ) {}
  private async post(path: string, body: Row = {}) {
    if (this.reader.mode !== "cloud")
      throw new Error("命令回执管理仅限云端模式");
    if (this.busy) throw new Error("上一条回执管理操作仍在处理");
    this.busy = true;
    try {
      const session = await this.reader.request("/auth/session");
      if (!session.ok) throw new Error("请重新登录");
      const info = object(await session.json());
      const response = await this.reader.request(path, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": String(info.csrf),
        },
        body: JSON.stringify(body),
      });
      const value = object(await response.json());
      if (!response.ok) throw new Error(text(value.detail, "操作失败"));
      return value;
    } finally {
      this.busy = false;
    }
  }
  async cancel(row: Row) {
    if (!["submitting", "queued", "leased"].includes(String(row.state)))
      throw new Error("只能撤销发送前命令");
    const identity = row.remote ? row.cloudCommandId : row.requestId;
    if (typeof identity !== "string" || !identity)
      throw new Error("缺少原命令编号");
    const value = await this.post(
      row.remote
        ? "/console/commands/" + encodeURIComponent(identity) + "/cancel"
        : "/console/commands/request/" +
            encodeURIComponent(identity) +
            "/cancel",
    );
    saveReceipts(
      localReceipts().map((r) =>
        r.requestId === row.requestId ? { ...r, state: "cancelled" } : r,
      ),
    );
    return value;
  }
  async resolve(row: Row) {
    if (row.state !== "unknown" || typeof row.cloudCommandId !== "string")
      throw new Error("只能人工对账结果不明命令");
    const note = this.prompt(
      "先在家里核实原请求已停止及业务实际结果，再填写对账依据（至少10字）。此操作不会重试原命令。",
    );
    if (!note) return null;
    if (
      this.prompt("输入 CONFIRMED_HOME_REQUEST_STOPPED 确认原请求已停止") !==
      "CONFIRMED_HOME_REQUEST_STOPPED"
    )
      return null;
    const value = await this.post(
      "/console/commands/" +
        encodeURIComponent(row.cloudCommandId) +
        "/resolve",
      { note, confirmation: "CONFIRMED_HOME_REQUEST_STOPPED" },
    );
    saveReceipts(
      localReceipts().map((r) =>
        r.requestId === row.requestId ? captureReceipt(r, value) : r,
      ),
    );
    return value;
  }
  finish(row: Row) {
    if (
      this.reader.mode !== "cloud" ||
      row.remote ||
      pendingStates.has(String(row.state))
    )
      throw new Error("未决或远端回执不能结束");
    if (
      !this.confirm("结束本次回执后，相同输入的下一次点击将创建新命令。确认？")
    )
      return false;
    saveReceipts(localReceipts().filter((r) => r.requestId !== row.requestId));
    return true;
  }
  cancelSubmission(requestId: string) {
    if (!requestId.trim()) throw new Error("请输入递交器原请求ID");
    return this.post(
      "/console/submission-requests/" +
        encodeURIComponent(requestId.trim()) +
        "/cancel",
    );
  }
}
const admins = new WeakMap<ReadClient, CommandAdmin>();
export function commandAdminFor(reader: ReadClient) {
  let admin = admins.get(reader);
  if (!admin) {
    admin = new CommandAdmin(reader);
    admins.set(reader, admin);
  }
  return admin;
}
