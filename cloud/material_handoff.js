'use strict';
(() => {
  const $ = id => document.getElementById(id);
  let state = null, csrf = '', pending = null, sending = false;
  const timestamp = value => value == null ? '无' : new Date(value * 1000).toLocaleString();
  function text(tag, value, parent) {
    const element = document.createElement(tag);
    element.textContent = value;
    parent.append(element);
    return element;
  }
  async function json(url, options = {}) {
    const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', ...options });
    if (!response.ok) {
      if (response.status === 401) throw Error('登录已失效，请返回控制台登录。');
      throw Error('操作未完成，请刷新状态后核对。HTTP ' + response.status);
    }
    return response.json();
  }
  function availability() {
    $('submit').disabled = sending || !state?.holder || !state?.candidates?.length || !$('stopped').checked || !$('reason').value.trim();
  }
  function packageNote() {
    const item = state?.candidates.find(item => item.id === $('package').value);
    $('package-note').textContent = item ? `包提交时间：${timestamp(item.committed_at)}；来源：${item.device === 'home' ? '家里' : '公司'}；待核对数量：${JSON.stringify(item.summary?.unresolved || {})}。接手前本机还会校验并恢复此包。` : '暂无可恢复的完整交接包；不能用半包接管。';
  }
  async function refresh() {
    const [auth, status] = await Promise.all([json('/auth/session'), json('/api/material-handoff/v1/status')]);
    csrf = auth.csrf; state = status;
    const fields = [['值班端', state.holder === 'home' ? '家里' : state.holder === 'office' ? '公司' : '无'],
      ['状态', state.phase === 'idle' ? '可正常接手' : state.lease_lost ? '连接已失效，需人工确认' : state.phase === 'preparing' ? '正在准备接手' : state.phase === 'draining' ? '正在交接' : '值班中'],
      ['最近联系', timestamp(state.last_contact_at)], ['当前执行许可截止', timestamp(state.lease_until)],
      ['最近完整交接包', state.current_package || '尚未建立首次基线'],
      ['当前包提交时间', timestamp(state.package?.committed_at)],
      ['当前包待核对数量', JSON.stringify(state.package?.summary?.unresolved || {})],
      ['交接存储已预留', `${state.storage.reserved_bytes} / ${state.storage.cap_bytes} 字节（不自动删除）`]];
    $('status').replaceChildren();
    for (const [label, value] of fields) { text('dt', label, $('status')); text('dd', value, $('status')); }
    $('package').replaceChildren();
    for (const item of state.candidates) { const option = text('option', `${timestamp(item.committed_at)} · ${item.id}`, $('package')); option.value = item.id; }
    $('audit').replaceChildren();
    for (const row of state.audit) text('li', `${timestamp(row.at)} · ${row.actor} · ${row.action} · ${JSON.stringify(row.detail)}`, $('audit'));
    $('stopped').checked = false;
    packageNote(); availability();
    $('message').textContent = '状态已更新。强制接管需要重新确认另一端已停止。';
  }
  $('refresh').onclick = () => refresh().catch(error => { $('message').textContent = error.message; });
  $('package').onchange = () => { $('stopped').checked = false; pending = null; packageNote(); availability(); };
  for (const id of ['target', 'reason', 'stopped']) $(id).oninput = availability;
  $('takeover').onsubmit = async event => {
    event.preventDefault();
    if ($('submit').disabled || !state) return;
    const body = { generation: state.generation, epoch: state.epoch, target_device: $('target').value,
      package_id: $('package').value, reason: $('reason').value.trim(),
      confirmation: '另一端已停止，未完成操作作废', other_device_stopped: $('stopped').checked };
    const contract = JSON.stringify(body);
    // Lost HTTP ACK reuses the same request ID; changed user choices get a new one.
    if (!pending || pending.contract !== contract) pending = { contract, id: crypto.randomUUID() };
    sending = true; availability();
    try {
      await json('/api/material-handoff/v1/force-takeover', { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        body: JSON.stringify({ ...body, request_id: pending.id }) });
      pending = null;
      await refresh();
      $('message').textContent = '接手准备权已建立。请在接手端领取、下载校验并恢复交接包；激活成功后才能开工。';
    } catch (error) { $('message').textContent = error.message + ' 请先核对当前值班状态，勿假定未执行。'; }
    finally { sending = false; availability(); }
  };
  refresh().catch(error => { $('message').textContent = error.message; });
})();
