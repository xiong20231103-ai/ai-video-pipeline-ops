/** Matches legacy app.js PR #33; this is a display unit, not a retry signal. */
export function controlTimeoutError(timeoutMs: number, cause: unknown) {
  const duration =
    timeoutMs < 60000
      ? Math.round(timeoutMs / 1000) + " 秒"
      : Math.round(timeoutMs / 60000) + " 分钟";
  const error = new Error(
    "操作仍在后台处理（已等待 " + duration + "），请刷新状态后再继续",
    { cause },
  );
  Object.assign(error, { code: "CONTROL_REQUEST_TIMEOUT" });
  return error;
}
