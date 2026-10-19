// Serves only the committed static build on loopback, under the cloud's CSP.
// No production process, network service or interface is used.
const assert = require('node:assert/strict')
const http = require('node:http')
const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require(process.env.OPS_UI_PLAYWRIGHT || 'playwright')

const root = path.resolve(__dirname, '../../static/v2')
const evidence = process.env.V2_EVIDENCE_DIR
if (evidence) fs.mkdirSync(evidence, { recursive: true })
const csp = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'"
const requests = [], failures = [], errors = [], violations = [], screenshots = []
const server = http.createServer((req, res) => {
  requests.push({ method: req.method, path: req.url })
  if (req.method !== 'GET' || !req.url.startsWith('/static/v2/')) { res.writeHead(403); return res.end() }
  const file = path.resolve(root, decodeURIComponent(req.url.split('?')[0].slice('/static/v2/'.length)))
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { res.writeHead(404); return res.end() }
  const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' }
  res.writeHead(200, { 'Content-Type': mime[path.extname(file)] || 'text/plain', 'Content-Security-Policy': csp, 'Cache-Control': 'no-store' })
  res.end(fs.readFileSync(file))
})

async function run() {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const origin = `http://127.0.0.1:${server.address().port}`
  const browser = await chromium.launch({ executablePath: process.env.OPS_UI_BROWSER_PATH, headless: true })
  try {
    for (const [width, height] of [[1920, 1080], [1440, 900], [1366, 768], [375, 812]]) {
      const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 })
      await context.route('**/*', route => {
        const url = new URL(route.request().url())
        if (url.origin !== origin || !url.pathname.startsWith('/static/v2/') || route.request().method() !== 'GET') {
          failures.push({ type: 'unexpected request', url: url.href, method: route.request().method() })
          return route.abort()
        }
        return route.continue()
      })
      const page = await context.newPage()
      page.on('pageerror', error => errors.push(error.message))
      page.on('console', event => { if (event.type() === 'error') errors.push(event.text()) })
      await page.exposeFunction('recordCspViolation', data => violations.push(data))
      await page.addInitScript(() => document.addEventListener('securitypolicyviolation', event => {
        window.recordCspViolation({ directive: event.violatedDirective, blocked: event.blockedURI })
      }))
      await page.goto(`${origin}/static/v2/index.html`, { waitUntil: 'networkidle' })
      await page.getByRole('heading', { name: '你的控制台，即将就绪' }).waitFor()
      await page.mouse.move(0, 0)
      for (const theme of ['dark', 'light']) {
        if (theme === 'light') await page.getByRole('button', { name: '切换到浅色主题' }).click()
        await page.mouse.move(0, 0)
        await page.waitForTimeout(300)
        const metrics = await page.evaluate(() => ({
          theme: document.documentElement.dataset.theme,
          overflow: document.documentElement.scrollWidth > window.innerWidth,
          background: getComputedStyle(document.body).backgroundColor,
          card: getComputedStyle(document.querySelector('.empty-card')).backgroundColor,
          inlineScripts: document.querySelectorAll('script:not([src])').length,
        }))
        assert.equal(metrics.theme, theme)
        assert.equal(metrics.overflow, false, `Horizontal overflow: ${theme} ${width}`)
        assert.equal(metrics.inlineScripts, 0)
        assert.equal(metrics.background, theme === 'dark' ? 'rgb(11, 13, 18)' : 'rgb(244, 245, 248)')
        assert.equal(metrics.card, theme === 'dark' ? 'rgb(24, 27, 34)' : 'rgb(255, 255, 255)')
        const name = `${theme}-${width}x${height}.png`
        if (evidence) await page.screenshot({ path: path.join(evidence, name), animations: 'disabled' })
        screenshots.push({ name, viewport: { width, height }, ...metrics })
      }
      await page.reload({ waitUntil: 'networkidle' })
      assert.equal(await page.locator('html').getAttribute('data-theme'), 'light')
      if (width === 375) {
        const menu = page.getByRole('button', { name: '打开导航' })
        await menu.click()
        const drawer = page.getByRole('dialog', { name: '控制台导航' })
        await drawer.waitFor()
        if (evidence) await page.screenshot({ path: path.join(evidence, 'light-375x812-navigation.png'), animations: 'disabled' })
        await page.keyboard.press('Escape')
        await drawer.waitFor({ state: 'hidden' })
        assert.equal(await menu.evaluate(el => document.activeElement === el), true)
        await menu.click()
        await drawer.getByRole('link', { name: '上传', exact: true }).click()
        await drawer.waitFor({ state: 'hidden' })
      } else {
        await page.getByRole('button', { name: '收起侧栏' }).click()
        assert.equal(await page.getByRole('button', { name: '展开侧栏' }).getAttribute('aria-expanded'), 'false')
        await page.getByRole('link', { name: '上传', exact: true }).click()
      }
      await page.getByRole('heading', { level: 1, name: '上传', exact: true }).waitFor()
      await page.reload({ waitUntil: 'networkidle' })
      await page.getByRole('heading', { level: 1, name: '上传', exact: true }).waitFor()
      assert.equal(new URL(page.url()).pathname, '/static/v2/index.html')
      await page.emulateMedia({ reducedMotion: 'reduce' })
      await page.reload({ waitUntil: 'networkidle' })
      const reduced = await page.locator('.spotlight-card__light').evaluate(el => getComputedStyle(el).display)
      assert.equal(reduced, 'none')
      await context.close()
    }
    assert.deepEqual(errors, [])
    assert.deepEqual(violations, [])
    assert.deepEqual(failures, [])
    const result = { verified: true, productionAccess: false, csp, screenshots, requests, errors, violations, failures }
    if (evidence) fs.writeFileSync(path.join(evidence, 'browser-result.json'), JSON.stringify(result, null, 2))
    console.log(JSON.stringify({ ...result, requests: `${requests.length} local static GETs; no interface or external requests` }, null, 2))
  } finally { await browser.close() }
}
run().catch(error => { console.error(error); process.exitCode = 1 }).finally(() => server.close())
