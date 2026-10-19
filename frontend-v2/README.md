# Dashboard V2-0

独立的 React 布局预览，入口 `/static/v2/index.html`。默认深色，可切换浅色；侧栏折叠、移动端抽屉和六个 hash 分区均为页面内交互。**非真实生产：未连接任何接口，无业务数据、轮询、业务按钮或写入。** 旧入口仍为 `/`。

## 构建与检查

使用 Node **24.19.0** 和 npm **11.17.0**。运行目录为本文件所在 `frontend-v2/`：

```text
npm ci
npm run typecheck
npm run lint
npm test
npm run build
npm run size
npm run check:build
```

`build` 只清空并重建 `../static/v2/`，`base: './'`。将整个产物目录随源码提交；生产端无需 Node。`check:build` 将文件集合（包括新增/遗漏文件）及每个文件的 SHA256 与 HEAD 中的 Git blob 对照，避免只检查已跟踪 diff 的遗漏。更改源码后，先构建并提交产物，再运行该检查。体积检查将**所有** JS chunk 的 gzip 总和限制在 300 KiB 内，比首屏预算更严格。

CI 在 Linux 上从 lockfile 重建；隔离浏览器检查可使用既有 Playwright 和本机 Edge：设置 `OPS_UI_PLAYWRIGHT`（Playwright 包路径）、`OPS_UI_BROWSER_PATH`（浏览器路径），执行 `node scripts/browser-check.cjs`。可选 `V2_EVIDENCE_DIR` 指定截图/证据输出目录。测试服务只绑定随机 loopback 端口，只接受 `/static/v2/` 下的 GET，应用任何外部或接口请求都会令检查失败。CSP 原样使用执行提示词所列值。浏览器由 headless 模式启动，不打开桌面窗口。

## 组件来源与本地适配

| 固定的上游源码 | 本地实现 | 适配 |
|---|---|---|
| [shadcn/ui `ba1503c`](https://github.com/shadcn-ui/ui/tree/ba1503c64472b82256d9de95e2e62c5901a38e8b/apps/v4/registry/new-york-v4/ui) 中的 `button/card/badge/separator/sheet/tooltip/input/skeleton.tsx` | `src/components/ui/` 下同名文件 | `cn` 的导入指向 `@/lib/utils`；组件行为保留上游实现。 |
| [React Bits `e12c221` SpotlightCard.tsx](https://github.com/DavidHDev/react-bits/blob/e12c22192ac7b4b452c5e2feb9b586d74765d696/src/ts-default/Components/SpotlightCard/SpotlightCard.tsx) 与同目录 CSS | `src/components/react-bits/SpotlightCard.tsx/.css` | 调色板读取本项目 token；减少动态效果时不注册动画循环；媒体偏好变化后不再唤醒动画。使用 lazy import，不引入 motion/WebGL。 |

侧栏为上述真实 shadcn Button/Tooltip/Sheet/Separator 的组合，桌面与移动端共享导航定义；没有将自写组件冒充上游 Sidebar。Card 用于旧页引导，Badge 标记预览，Skeleton 仅为按需模块加载的短暂后备；Input 在基础组件中预备，当前空布局未使用。图标来自 `lucide-react`，字体仅系统字体栈。

上游完整许可证随 `public/licenses/` 复制到构建目录。shadcn/ui 是 MIT；React Bits 是 **MIT + Commons Clause**，仅作为本应用组成部分交付，不单独售卖/分发组件包。npm 运行时依赖为 MIT / Apache-2.0 / ISC；固定版本见 `package.json`，全部直接和间接版本见 `package-lock.json`。

## 设计与安全边界

- `src/styles.css` 使用 shadcn CSS token + Tailwind v4，深色层级、文字、语义色按用户原稿；浅色共用同一语义变量。只在顶栏使用玻璃材质，并提供不透明降级。
- React Bits 仅用于空内容面板的轻微指针照明，禁用 ambient、flare、grain。减少动态效果偏好时不显示照明或执行初始动画；没有计时器、循环入场或模拟数据。
- 本地存储只使用 `ops-v2:theme` 与 `ops-v2:sidebar` 两项外观偏好。hash 只保存视图，不新增后端路由；无 cookie、凭据、后端存储或配置读取。
- 通过当前云端 CSP；脚本、样式、图标、许可证全部本地打包，无 CDN、外部字体、图片或遥测。
- V2-0 **没有验证生产部署、真实数据、操作契约、轮询、新鲜度、权限/登录或默认入口切换**。这些属于后续阶段；禁止把本 PR 的隔离测试记为真实影子或生产验收。
- 本 PR 不要求改动 `app.py` / `cloud/` / `agent/` / `contracts/` / 旧页面。回滚为 revert 本 PR；旧入口继续运行。

## 后续部署（本轮不执行）

由 Claude 审查后按用户授权更新新增静态文件；不改默认入口，不需要重启家里 Dashboard。云端同样仅增加静态文件，继续由现有 `/static` 的会话验证保护。回退只移除本 PR 的 V2 静态目录和源码/CI。生产切换必须另行获批。
