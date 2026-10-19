# Dashboard V2-2B 任务操作

新增补链、建任务、启动、撤回。见 docs/v2/V2-2B_TASK_PARITY.md；隔离浏览器另运行 scripts/task-browser-check.cjs。未部署。下面阶段说明为继承的基线文档；当前可用操作以上述两阶段增量为准。

# Dashboard V2-2A 上传类操作

本 PR 在 V2-1 上仅接入上传重扫和历史核验，其他业务写按钮仍禁用。逐行对照、双模式语义、回滚见 `docs/v2/V2-2A_UPLOAD_PARITY.md`；补充运行 `node scripts/upload-browser-check.cjs`。全部数据为隔离夹具，未部署。

以下为继承的 V2-1 基线说明，涉及“所有写按钮禁用”的表述仅适用于 V2-1，不含本 PR 新接入的两项上传操作。

# Dashboard V2-1 只读视图

入口 `/static/v2/index.html`，默认深色、可切换浅色，六个 hash 分区与移动端抽屉。支持家里/云端两种模式；所有业务写按钮均禁用并引导到旧页面。生产默认入口未切换。

## 实现与来源

- `src/data/client.ts`：模式识别、同源 GET、超时/重试、202 排队、ETag/304、云端缓存来源和后台刷新。
- `src/data/useDashboard.ts`：沿用旧页的可见/隐藏轮询、完整/summary 合并、健康降级、安全面板及安全继续状态只读查询；切换日期/任务箱取消旧请求。
- `src/data/legacy-formatters.js`：从当前 `static/app.js` 的纯显示函数复制，文件中保留函数及原行号。`presentation.ts` 与 React 视图使用相同状态和数字。
- `src/components/views/`：生产总览、五步流程、任务箱、任务、补链提示、上传、健康、事件、云端来源/命令/备份、待删区只读状态。
- shadcn/ui 固定源码 `ba1503c64472b82256d9de95e2e62c5901a38e8b` 的 `apps/v4/registry/new-york-v4/ui/table.tsx` → `src/components/ui/table.tsx`；只调整 cn 导入。原有 button/card/badge/separator/sheet/tooltip/input/skeleton 继续沿用同一源码与 MIT 许可证。
- React Bits 原有 SpotlightCard 源码保留在工程中，V2-1 内容不使用它；V2-3 再处理动效。许可证文件随产物本地交付。

## 验证

Node 24.19.0；运行目录为 `frontend-v2/`：

```text
npm ci
npm run typecheck
npm run lint
npm test
npm run build
npm run size
npm run check:build
node scripts/readonly-browser-check.cjs
```

`npm test` 含 transport 与新旧页面同数据对比；家里/云端各覆盖 baseline、empty、unconfigured。对比旧 DOM 与新 React 显示的指标、流程行、任务行、任务箱和安全状态；云端回执状态中文与 `cloud/commands.js` 原始 labels 完全比对。它只证明所列隔离夹具的零差异，不代表全部生产数据已经验收。

浏览器脚本用 Playwright headless，不打开窗口；所有请求由本地资产/合成数据 fulfill，未建模请求直接失败，绝不放行真实网络。验证双模式、深浅主题、1920×1080 / 1440×900 / 1366×768 / 375×812、六视图、黄色/红色数据年龄、云端备份及命令查询、写按钮全部禁用、无横向溢出、无控制台错误和 CSP 违规。`V2_EVIDENCE_DIR` 可设置截图目录；本机 Edge 可由 `OPS_UI_BROWSER_PATH` 指定。CI 将截图作为 artifact 上传。

`build` 只重建 `../static/v2/`，产物随源码提交。`check:build` 与 HEAD blob 比对所有产物；应在提交后运行。全部 JS gzip 预算 300 KiB；本次约 126 KiB，静态文件总计约 555 KiB。

## 依赖与边界

无新增运行时依赖。新增开发依赖：`@types/jsdom` 30.0.0（MIT）、`prettier` 3.9.10（MIT），均不进入运行时 JS。固定全部版本见 package-lock.json；运行时依赖、许可证与打包体积见产物 dependencies.json、THIRD_PARTY_NOTICES.txt。

云端旧回执只读兼容 `ops-command-receipts-v1`，查询已有 requestId/cloudCommandId，绝不重发；不会存储密码、令牌或会话秘密。主题/侧栏仅存外观偏好。所有资产本地打包，无 CDN/字体/遥测。

未完成：登录/密码/退出等写操作、各类业务操作、完整批次真实影子和切换验收；功能清单未覆盖项保持未勾选。当前 PR 的截图均为合成隔离数据，界面带“非真实生产”标识。不修改 app.py/cloud/agent/contracts/旧 static 页面，不访问家里生产写接口，不切换默认入口、不部署。

回滚：revert 本 PR 并按原有静态部署方式恢复 `static/v2/`，旧 `/` 入口不受影响，无需重启 Dashboard。
