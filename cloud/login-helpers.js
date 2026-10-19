// Presentation preferences only. Never persist authentication fields.
export function safeDestination(value) {
  if (typeof value !== 'string' || value.length > 2048 || !value.startsWith('/') || value.startsWith('//') || [...value].some(c => c.charCodeAt(0) < 33 || c.charCodeAt(0) === 127 || c.charCodeAt(0) === 92)) return '/';
  return ['/', '/legacy', '/static/index.html', '/static/v2/index.html'].includes(value.split(/[?#]/, 1)[0]) ? value : '/';
}
export function returnDestination() {
  return safeDestination(new URLSearchParams(window.location.search).get('next'));
}
export function busy(active) {
  for (const form of document.querySelectorAll('form')) {
    form.setAttribute('aria-busy', String(active));
    for (const button of form.querySelectorAll('button')) button.disabled = active;
  }
}
export function optionsFailed() {
  document.getElementById('registration').hidden = true;
  document.getElementById('message').textContent = '暂时无法查询注册状态，已有账号仍可登录。';
}
export function setup() {
  let theme = 'dark';
  try { if (localStorage.getItem('ops-v2:theme') === 'light') theme = 'light'; } catch { /* Presentation remains usable. */ }
  const apply = () => {
    document.documentElement.dataset.theme = theme;
    document.getElementById('themeToggle').setAttribute('aria-label', theme === 'dark' ? '切换到浅色主题' : '切换到深色主题');
  };
  apply();
  document.getElementById('themeToggle').addEventListener('click', () => {
    theme = theme === 'dark' ? 'light' : 'dark'; apply();
    try { localStorage.setItem('ops-v2:theme', theme); } catch { /* No authentication state is stored. */ }
  });
}
