# V2-0 隔离验收记录

这些截图来自真实 headless Edge 浏览器加载 `static/v2/` 构建产物，**非真实生产**。静态测试服务仅监听随机 loopback 端口；100 次请求全部为本地静态 GET，无接口、外部资源或生产请求。CSP 与执行提示词相同，`errors / violations / failures` 均为空。原始记录见 [browser-result.json](browser-result.json)。

| 视口 | 深色 | 浅色 |
|---|---|---|
| 1920 × 1080 | [截图](dark-1920x1080.png) | [截图](light-1920x1080.png) |
| 1440 × 900 | [截图](dark-1440x900.png) | [截图](light-1440x900.png) |
| 1366 × 768 | [截图](dark-1366x768.png) | [截图](light-1366x768.png) |
| 375 × 812 | [截图](dark-375x812.png) | [截图](light-375x812.png) |

另附 [375 × 812 手机导航抽屉](light-375x812-navigation.png)。1366 × 768 首屏下方仍可正常滚动查看旧页引导与页脚；无横向溢出。页面没有业务弹窗和数据新鲜度状态，故本阶段不伪造黄色/红色新鲜度截图。

浏览器还实际检查了：深浅切换与刷新保持、同页分区与刷新保持、侧栏折叠、手机抽屉 Esc 关闭/焦点返回及选择关闭、减少动态效果。没有点击旧入口或任何生产操作。

本地检查：Node 24.19.0，npm 11.17.0；`npm ci`、typecheck、lint、7 项前端单元测试与 build 均通过；既有 `tools/run_isolated_tests.py` 为 361 项、跳过 1 项，通过（56.709 秒，生产 I/O 封锁）。CI 会从 lockfile 在 Linux 重建，比较提交产物所有文件的集合与内容 SHA256，并运行相同浏览器检查；实际远程终态以 PR checks 为准。

## 产物体积

原始统计：[bundle-size.json](bundle-size.json)，使用 Node gzip 默认级别；Vite 的显示口径略有差异，以本统计为准。

| 组成 | 原始字节 | gzip 字节 |
|---|---:|---:|
| 首入口 JS（React / ReactDOM / shadcn+Radix / Lucide / 应用共享） | 348405 | 110548 |
| React Bits 延迟 JS | 5865 | 2517 |
| 主 CSS（Tailwind + token + 布局） | 41758 | 8577 |
| React Bits 延迟 CSS | 875 | 345 |
| **全部 JS** | **354270** | **113065（110.4 KiB）** |

完整静态目录为 **511527 字节（499.5 KiB）**，包括完整运行时许可证、依赖清单及 manifest。首入口 JS 约 108.0 KiB gzip，全部 JS 仍显著低于 300 KiB。共享 chunk 无法给每个被 tree-shake 的依赖分配独立 gzip 大小，因此不把共享大小重复相加；构建/测试依赖不进入运行时 JS，Tailwind 与 tw-animate-css 仅贡献编译后 CSS。

## 新增直接依赖（全部精确固定，传递依赖由 lockfile 锁定）

| 名称 | 固定版本 | 许可证 | 产物归属 |
|---|---|---|---|
| react / react-dom | 各 19.3.1 | MIT | 首入口共享 JS |
| radix-ui | 1.8.1 | MIT | 首入口共享 JS，仅打包被引用组件 |
| lucide-react | 1.59.0 | ISC | 首入口共享 JS，仅打包被引用图标 |
| class-variance-authority | 0.7.1 | Apache-2.0 | 首入口共享 JS |
| clsx | 2.1.1 | MIT | 首入口共享 JS |
| tailwind-merge | 3.7.0 | MIT | 首入口共享 JS |
| tailwindcss / @tailwindcss/vite | 各 4.3.3 | MIT | 构建工具，输出主 CSS |
| tw-animate-css | 1.4.0 | MIT | 主 CSS；减少动态效果时关闭 |
| vite / @vitejs/plugin-react | 8.3.4 / 6.1.2 | MIT | 仅构建 |
| typescript | 6.0.3 | Apache-2.0 | 仅构建/检查 |
| eslint / @eslint/js | 10.13.0 / 10.0.1 | MIT | 仅检查 |
| typescript-eslint | 8.71.2 | MIT | 仅检查 |
| eslint-plugin-react-hooks / eslint-plugin-react-refresh | 7.1.1 / 0.5.7 | MIT | 仅检查 |
| vitest / jsdom | 5.0.5 / 30.1.3 | MIT | 仅测试 |
| @testing-library/react / dom / jest-dom / user-event | 16.3.3 / 10.4.2 / 7.0.1 / 14.6.8 | MIT | 仅测试 |
| @types/node / react / react-dom | 24.19.2 / 19.3.0 / 19.3.0 | MIT | 仅类型检查 |
| playwright | 1.62.1 | Apache-2.0 | 仅隔离浏览器测试 |
| shadcn/ui 复制源码 | ba1503c64472b82256d9de95e2e62c5901a38e8b | MIT | 首入口共享 JS；8 个基础组件 |
| React Bits SpotlightCard 复制源码 | e12c22192ac7b4b452c5e2feb9b586d74765d696 | MIT + Commons Clause | 延迟 JS / CSS |

逐项机器可读清单由 [public/dependencies.json](../public/dependencies.json) 生成。完整授权声明在 `public/THIRD_PARTY_NOTICES.txt` 和 `public/licenses/`，随静态产物交付。`react-remove-scroll-bar@2.3.8` npm 包未携带 LICENSE，另保留其官方固定 blob 的 MIT 原文（来源详见生成脚本）；没有弱化 React Bits 的 Commons Clause。

## 未验证 / 不在本阶段

尚未接入接口或实际部署，未进行真实影子、生产批次或默认入口切换验收。操作契约、CSRF、排队/新鲜度、读写权限属于后续阶段。当前 PR 只新增源码、静态产物、截图和一份 CI，不改旧页面或后端。回滚为 revert 本 PR，旧入口不受影响。
