# Dashboard V2 独立预览

React + Vite + TypeScript + Tailwind + shadcn/ui；额外入口 `/static/v2/index.html`，不切换旧页面。双模式：home业务操作直接使用原接口，cloud业务操作只使用既有云端命令队列。生产cleanup开关不在前端启用。安全继续PR #36必须用户亲自确认后才可合并。

## 已实现与范围

只读总览、任务箱/日期/项目筛选、五步流水线、上传、健康/事件/来源/新鲜度；上传重扫与历史核验、补链/建任务/开始/撤回、三类清理及待删区、云端票据、安全继续及原编号回执管理、已登录账号、备份管理、home测试记录重置。五类清理扩展未包含。

用户2026-10-20明确：未登录登录注册继续用云端 `/login`（含邀请码），401仍跳该入口；V2-4另审cloud PR再迁移。功能清单878项实现、22项用户延期（总900）。只有实现/隔离验证，未完成真实生产影子或切换。逐行对照和唯一清单在docs/v2/。

## 本地验证（frontend-v2目录）

```text
npm ci
npm run typecheck
npm run lint
npm test
npm run inventory:check
npm run build
npm run size
npm run check:build
```

check:build与已提交static/v2逐字节比对，应在提交后运行。固定版本见package-lock.json；没有运行时CDN、外部字体、遥测或Node生产依赖。

## 浏览器隔离验收

所有脚本以Playwright无头模式运行；全部请求用本地资产/合成响应fulfill，未知请求失败，不放行真实网络。设置V2_EVIDENCE_DIR保存截图和原始JSON；OPS_UI_BROWSER_PATH可指定本机Edge路径。CI使用Chromium。

```text
node scripts/readonly-browser-check.cjs
node scripts/upload-browser-check.cjs
node scripts/task-browser-check.cjs
node scripts/home-cleanup-browser-check.cjs
node scripts/cloud-cleanup-browser-check.cjs
node scripts/queue-wait-browser-check.cjs
node scripts/safe-continue-browser-check.cjs
node scripts/admin-browser-check.cjs
node scripts/polish-browser-check.cjs
node scripts/memory-browser-check.cjs
```

最后一项实际运行至少10分钟。密码拒绝HTTP400和收件前原requestId查询404属于明确建模的负例，精确URL/状态核对后单列，其它错误仍失败。原始证据保留，不把预期失败写成无错误。

## 依赖、设计与回滚

无新增V2-3依赖；shadcn/Button/Input/Sheet/Table等来源与许可见public/dependencies.json、THIRD_PARTY_NOTICES.txt、licenses/。React Bits固定参考/原生API适配说明在docs/v2/V2-3_POLISH.md；保留其MIT + Commons Clause许可。深浅token统一、减少动态效果关闭动画、已知值不变不重播；数值读屏保留最终文本。

所有家里改动仅worktree/PR；不修改app.py/cloud/agent/contracts/旧static页面，不部署、不重启、不在生产点写按钮。回滚revert对应PR及static/v2产物，旧入口保留。V2-4默认入口切换需用户批准、Claude实施。
