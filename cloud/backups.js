/* Cloud-only backup catalog. Downloaded material remains ciphertext. */
(() => {
  const api = async (path, method = 'GET') => {
    const headers = {};
    if (method !== 'GET') {
      const session = await fetch('/auth/session').then(r => r.json());
      headers['X-CSRF-Token'] = session.csrf;
    }
    const response = await fetch(path, {method, headers});
    if (!response.ok) throw new Error(`请求失败 (${response.status})`);
    return response.json();
  };
  const element = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const show = async (body, message) => {
    try {
      const result = await api('/console/backups');
      body.replaceChildren();
      body.append(element('p', `仅台账和配置恢复；视频、草稿不在备份中。已用及预留 ${(result.usedReservedBytes / 1048576).toFixed(1)} MiB / ${(result.quotaBytes / 1e9).toFixed(0)} GB。`));
      const phase = result.agentState?.phase || 'waiting_configuration';
      const phases = {waiting_configuration: '等待本机配置恢复密钥', creating: '正在生成', uploading: '正在上传', completed: '最近一次已上传', failed: '备份失败，请检查代理状态'};
      body.append(element('p', `家里备份：${phases[phase] || phase}。${result.recipientConfigured ? '云端已登记公钥。' : '云端尚未登记公钥。'}`));
      body.append(element('p', `实际保留日期：${result.retainedDates.join('、') || '尚无备份'}`));
      if (!result.items.length) body.append(element('p', '尚无已完成的备份包；未完成上传不会显示为可恢复备份。'));
      for (const item of result.items) {
        const row = element('div');
        row.style.cssText = 'padding:8px 0;border-bottom:1px solid #888';
        row.append(element('p', `${item.kind === 'home' ? '家里台账/配置' : '云端数据库'} · ${item.date} · ${(item.bytes / 1048576).toFixed(2)} MiB · ${item.packageId}`));
        for (const name of ['manifest.json', ...item.manifest.artifacts.map(p => p.name)]) {
          const link = element('a', `下载 ${name}`);
          link.href = `/console/backups/${item.packageId}/${name}`;
          link.download = name; link.style.marginRight = '16px'; row.append(link);
        }
        const verify = element('button', '校验云端文件');
        verify.type = 'button';
        verify.onclick = async () => {
          verify.disabled = true;
          try { const checked = await api(`/console/backups/${item.packageId}/verify`, 'POST'); message.textContent = checked.verified ? `校验通过：${item.packageId}` : `校验失败：${item.packageId}`; }
          catch (error) { message.textContent = error.message; }
          finally { verify.disabled = false; }
        };
        row.append(verify); body.append(row);
      }
      if (result.events.length) body.append(element('p', '保留/容量事件：' + result.events.map(e => `${new Date(e.at * 1000).toLocaleString()} ${e.code}`).join('；')));
    } catch (error) { message.textContent = error.message; }
  };
  document.addEventListener('DOMContentLoaded', () => {
    const panel = element('details'); panel.id = 'cloudBackupPanel';
    panel.style.cssText = 'margin:16px;padding:12px;border:1px solid #888;border-radius:8px;overflow-wrap:anywhere';
    panel.append(element('summary', '异地备份（台账与配置）'));
    const refresh = element('button', '刷新列表'), request = element('button', '请求一次备份');
    refresh.type = request.type = 'button';
    const message = element('p'), body = element('div'); message.setAttribute('role', 'status');
    refresh.onclick = () => show(body, message);
    request.onclick = async () => {
      request.disabled = true;
      try { await api('/console/backups/request', 'POST'); message.textContent = '请求已排队；代理配置就绪后执行。稍后刷新列表查看。'; }
      catch (error) { message.textContent = error.message; }
      finally { request.disabled = false; }
    };
    panel.append(refresh, request, message, body);
    panel.addEventListener('toggle', () => { if (panel.open) show(body, message); });
    document.body.append(panel);
  });
})();
