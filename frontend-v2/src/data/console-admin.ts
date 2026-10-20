import { ReadClient } from "./client";
import { object, type Row } from "./types";
import { HomeCleanup } from "./home-cleanup";

export class ConsoleAdmin {
  private active = new Set<string>();
  constructor(
    readonly reader: ReadClient,
    readonly redirect = (url: string) => window.location.assign(url),
  ) {}
  async cloudPost(path: string, body?: Row) {
    if (this.reader.mode !== "cloud") throw new Error("该操作仅限云端模式");
    if (
      !["/auth/password", "/auth/logout", "/console/backups/request"].includes(
        path,
      ) &&
      !/^\/console\/backups\/[^/]+\/verify$/.test(path)
    )
      throw new Error("未声明的账号或备份操作");
    if (this.active.has(path)) throw new Error("操作仍在处理，请等待原结果");
    this.active.add(path);
    try {
      const session = await this.reader.request("/auth/session");
      if (!session.ok) throw new Error("请重新登录");
      const info = object(await session.json());
      const response = await this.reader.request(path, {
        method: "POST",
        headers: {
          ...(body ? { "Content-Type": "application/json" } : {}),
          "X-CSRF-Token": String(info.csrf),
        },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      if (path === "/auth/logout") {
        if (!response.ok) throw new Error("退出失败，请重试");
        this.redirect("/login");
        return { loggedOut: true };
      }
      if (path === "/auth/password") {
        if (!response.ok) throw new Error("未修改，请核对密码后重试");
        this.redirect("/login");
        return { changed: true };
      }
      if (!response.ok) throw new Error(`请求失败 (${response.status})`);
      return object(await response.json());
    } finally {
      this.active.delete(path);
    }
  }
  async reset(confirm = window.confirm.bind(window)) {
    if (this.reader.mode !== "home")
      throw new Error("云端不允许重置家里测试记录");
    if (
      !confirm(
        "确认把今天的测试任务记录备份后全部归零吗？视频、音频、素材、配置和校准都会保留。",
      )
    )
      return null;
    if (
      !confirm(
        "再次确认：Dashboard、工作台、接收器和 CapCut 的任务进度将从空状态重新开始。",
      )
    )
      return null;
    return new HomeCleanup(this.reader).post("/api/controls/testing/reset", {
      confirm: "RESET_TEST_RECORDS",
    });
  }
}
const admins = new WeakMap<ReadClient, ConsoleAdmin>();
export function consoleAdminFor(reader: ReadClient) {
  let admin = admins.get(reader);
  if (!admin) {
    admin = new ConsoleAdmin(reader);
    admins.set(reader, admin);
  }
  return admin;
}
