import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { ConsoleAdmin } from "@/data/console-admin";
import { ReadClient } from "@/data/client";
import AccountActions from "@/components/views/AccountActions";
import BackupAction from "@/components/views/BackupAction";
import ResetAction from "@/components/views/ResetAction";
const json = (v: unknown, status = 200) =>
  new Response(JSON.stringify(v), {
    status,
    headers: { "Content-Type": "application/json" },
  });
function setup(mode: "home" | "cloud" = "cloud", status = 200) {
  const network = vi
      .fn()
      .mockImplementation(async (url) =>
        String(url) === "/auth/session"
          ? json({ csrf: "synthetic-csrf" })
          : json({ verified: true, message: "模拟结果" }, status),
      ),
    reader = new ReadClient(network);
  reader.mode = mode;
  const redirect = vi.fn(),
    admin = new ConsoleAdmin(reader, redirect);
  return { reader, network, redirect, admin };
}
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
describe("account and backup use local cloud administration only", () => {
  for (const path of [
    "/auth/logout",
    "/auth/password",
    "/console/backups/request",
    "/console/backups/synthetic/verify",
  ])
    it(path + " exact CSRF and method", async () => {
      const f = setup(),
        body =
          path === "/auth/password"
            ? {
                oldPassword: "synthetic-old",
                newPassword: "synthetic-new-only",
              }
            : undefined;
      await f.admin.cloudPost(path, body);
      expect(f.network.mock.calls).toHaveLength(2);
      expect(f.network.mock.calls[1][0]).toBe(path);
      const init = f.network.mock.calls[1][1];
      expect(init.method).toBe("POST");
      expect(init.headers["X-CSRF-Token"]).toBe("synthetic-csrf");
      expect(init.body).toBe(body ? JSON.stringify(body) : undefined);
      expect(f.redirect.mock.calls).toEqual(
        path.startsWith("/auth/") ? [["/login"]] : [],
      );
    });
  for (const path of ["/auth/password", "/console/backups/request"])
    it("home rejects cloud " + path, async () => {
      const f = setup("home");
      await expect(f.admin.cloudPost(path, {})).rejects.toThrow("仅限云端");
      expect(f.network).not.toHaveBeenCalled();
    });
  it("no arbitrary admin route is permitted", async () => {
    const f = setup();
    await expect(f.admin.cloudPost("/api/control-commands")).rejects.toThrow(
      "未声明",
    );
    expect(f.network).not.toHaveBeenCalled();
  });
  it("password rejection uses original generic message without server detail/password echo", async () => {
    const f = setup("cloud", 400);
    await expect(
      f.admin.cloudPost("/auth/password", {
        oldPassword: "synthetic-old",
        newPassword: "synthetic-new",
      }),
    ).rejects.toThrow("未修改，请核对密码后重试");
    expect(f.redirect).not.toHaveBeenCalled();
  });
  it("backup failure displays HTTP status, not success", async () => {
    const f = setup("cloud", 503);
    await expect(f.admin.cloudPost("/console/backups/request")).rejects.toThrow(
      "请求失败 (503)",
    );
  });
  it("CSRF session failure sends no POST", async () => {
    const f = setup();
    f.network.mockResolvedValue(json({}, 401));
    await expect(f.admin.cloudPost("/console/backups/request")).rejects.toThrow(
      "重新登录",
    );
    expect(f.network).toHaveBeenCalledTimes(1);
  });
  it("concurrent repeated request is refused before another fetch and later error allows explicit retry", async () => {
    let finish!: (v: Response) => void;
    const f = setup();
    f.network.mockReturnValue(
      new Promise<Response>((resolve) => (finish = resolve)),
    );
    const work = f.admin.cloudPost("/console/backups/request");
    await expect(f.admin.cloudPost("/console/backups/request")).rejects.toThrow(
      "仍在处理",
    );
    expect(f.network).toHaveBeenCalledTimes(1);
    finish(json({}, 401));
    await expect(work).rejects.toThrow("重新登录");
  });
});
describe("home reset keeps both exact original confirmations; cloud forbidden", () => {
  it("two confirmations, exact body, no CSRF, original 10s deadline", async () => {
    const f = setup("home"),
      confirm = vi.fn().mockReturnValue(true);
    await f.admin.reset(confirm);
    expect(confirm.mock.calls).toEqual([
      [
        "确认把今天的测试任务记录备份后全部归零吗？视频、音频、素材、配置和校准都会保留。",
      ],
      [
        "再次确认：Dashboard、工作台、接收器和 CapCut 的任务进度将从空状态重新开始。",
      ],
    ]);
    expect(f.network.mock.calls[0][0]).toBe("/api/controls/testing/reset");
    expect(JSON.parse(f.network.mock.calls[0][1].body)).toEqual({
      confirm: "RESET_TEST_RECORDS",
    });
  });
  for (const count of [0, 1])
    it("cancel at confirmation " + (count + 1) + " does not POST", async () => {
      const f = setup("home"),
        confirm = vi.fn().mockReturnValue(false);
      if (count) confirm.mockReturnValueOnce(true);
      expect(await f.admin.reset(confirm)).toBeNull();
      expect(f.network).not.toHaveBeenCalled();
    });
  it("cloud reset never prompts or sends", async () => {
    const f = setup(),
      confirm = vi.fn();
    await expect(f.admin.reset(confirm)).rejects.toThrow("云端不允许");
    expect(confirm).not.toHaveBeenCalled();
    expect(f.network).not.toHaveBeenCalled();
  });
  it("home reset timeout text preserved and no automatic retry", async () => {
    const f = setup("home");
    f.network.mockRejectedValue(new DOMException("fixture", "AbortError"));
    await expect(f.admin.reset(() => true)).rejects.toThrow("已等待 10 秒");
    expect(f.network).toHaveBeenCalledTimes(1);
  });
});
describe("front-end fields, disabling and error state", () => {
  it("account inputs have original constraints and never store credentials", async () => {
    const f = setup();
    const storage = vi.spyOn(Storage.prototype, "setItem");
    render(<AccountActions reader={f.reader} />);
    fireEvent.click(screen.getByRole("button", { name: "修改密码" }));
    const old = screen.getByLabelText("当前密码"),
      next = screen.getByLabelText("新密码（至少12个字符）");
    expect(old).toHaveAttribute("type", "password");
    expect(old).toHaveAttribute("maxlength", "256");
    expect(next).toHaveAttribute("minlength", "12");
    expect(next).toHaveAttribute("maxlength", "256");
    expect(old).toHaveAttribute("autocomplete", "current-password");
    expect(next).toHaveAttribute("autocomplete", "new-password");
    expect(screen.getByRole("link", { name: "登录与注册" })).toHaveAttribute(
      "href",
      "/login",
    );
    expect(storage).not.toHaveBeenCalled();
  });
  it("password failure retains input for correction, displays generic text, does not persist", async () => {
    const f = setup("cloud", 400),
      storage = vi.spyOn(Storage.prototype, "setItem");
    render(<AccountActions reader={f.reader} />);
    fireEvent.click(screen.getByRole("button", { name: "修改密码" }));
    fireEvent.change(screen.getByLabelText("当前密码"), {
      target: { value: "synthetic-old" },
    });
    fireEvent.change(screen.getByLabelText("新密码（至少12个字符）"), {
      target: { value: "synthetic-new-only" },
    });
    fireEvent.submit(screen.getByLabelText("当前密码").closest("form")!);
    expect(screen.getByRole("button", { name: "保存新密码" })).toBeDisabled();
    await screen.findByText("未修改，请核对密码后重试");
    expect(screen.getByLabelText("当前密码")).toHaveValue("synthetic-old");
    expect(storage).not.toHaveBeenCalled();
    expect(f.network.mock.calls[1][1].body).toBe(
      JSON.stringify({
        oldPassword: "synthetic-old",
        newPassword: "synthetic-new-only",
      }),
    );
  });
  it("backup pending UI disallows repeated click and displays exact queued message", async () => {
    const f = setup();
    render(<BackupAction reader={f.reader} />);
    fireEvent.click(screen.getByRole("button", { name: "请求一次备份" }));
    expect(screen.getByRole("button", { name: "正在处理…" })).toBeDisabled();
    await screen.findByText(
      "请求已排队；代理配置就绪后执行。稍后刷新列表查看。",
    );
    expect(
      f.network.mock.calls.filter((c) => c[1]?.method === "POST"),
    ).toHaveLength(1);
  });
  it("package verification never treats verified false as pass", async () => {
    const f = setup();
    f.network.mockImplementation(async (url) =>
      String(url) === "/auth/session"
        ? json({ csrf: "fixture" })
        : json({ verified: false }),
    );
    render(<BackupAction reader={f.reader} packageId="synthetic-package" />);
    fireEvent.click(screen.getByRole("button", { name: "校验云端文件" }));
    await screen.findByText("校验失败：synthetic-package");
  });
  it("reset cloud button disabled without prompting", () => {
    const f = setup(),
      confirm = vi.spyOn(window, "confirm");
    render(<ResetAction reader={f.reader} onReset={vi.fn()} />);
    expect(
      screen.getByRole("button", { name: "重置全部测试记录" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "重置全部测试记录" }));
    expect(confirm).not.toHaveBeenCalled();
    expect(f.network).not.toHaveBeenCalled();
  });
  it("successful reset clears selected context via callback only after both confirms and HTTP result", async () => {
    const f = setup("home"),
      onReset = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<ResetAction reader={f.reader} onReset={onReset} />);
    fireEvent.click(screen.getByRole("button", { name: "重置全部测试记录" }));
    await waitFor(() => expect(onReset).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("status")).toHaveTextContent("completed");
    expect(f.network).toHaveBeenCalledTimes(1);
  });
});
