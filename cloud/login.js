'use strict'; import {setup, busy, optionsFailed, returnDestination} from '/login-helpers.js'; setup();
const message = document.getElementById('message');
fetch('/auth/options').then(response => { if (!response.ok) throw new Error('options_unavailable'); return response.json(); }).then(data => { document.getElementById('registration').hidden = data.registrationOpen !== true; }, optionsFailed);
for (const [id, route] of [['loginForm', '/auth/login'], ['registerForm', '/auth/register']]) {
  document.getElementById(id).addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    if (form.getAttribute('aria-busy') === 'true') return; busy(true); message.textContent = '';
    try {
      const response = await fetch(route, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.fromEntries(new FormData(form)))});
      if (!response.ok) { message.textContent = '未成功，请核对填写内容或稍后重试。'; return; }
      if (route === '/auth/login') { form.reset(); location.assign(returnDestination()); }
      else { form.reset(); message.textContent = '注册完成，请登录。'; document.getElementById('registration').open = false; }
    } catch { message.textContent = '连接暂不可用，请稍后重试。'; }
    finally { busy(false); }
  });
}
