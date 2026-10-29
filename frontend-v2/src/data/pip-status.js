// A PiP display is affirmative only when both Workbench and executor are fresh.
export function capcutSessionNotice(data, now = Date.now() / 1000) {
  const row = data?.overview?.pipeline?.capcut?.capcutSession;
  if (!row || row.mode !== 'pip') return null;
  const epoch = row.heartbeatEpoch;
  const online = row.executorOnline === true && typeof epoch === 'number' &&
    Number.isFinite(epoch) && now - epoch >= 0 && now - epoch <= 15 &&
    Number.isInteger(row.sessionId) && row.sessionId > 0 && ['ready', 'busy'].includes(row.state);
  return online
    ? { online: true, title: '剪映在子会话运行中，可以正常使用电脑',
        detail: '请保持画中画子会话打开，不要在主桌面打开剪映。' }
    : { online: false, title: '等待剪映子会话',
        detail: '子会话执行器离线或心跳已过期；任务不会自动切回主桌面。' };
}
