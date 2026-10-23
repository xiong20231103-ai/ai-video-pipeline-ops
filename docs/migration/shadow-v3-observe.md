# v3 旁听模式接线（observe）

本提交把已审查的组件接到 v3 启动入口：`AgentReadObserver` + `DashboardReadBinding`（只旁听 Dashboard 自己已有的 GET）、`CapturePublisher`（稳定窗口采集 + 去重存储）、`DashboardShadowHost` + `attach_lifespan`（生命周期与 STOP）。不安装、不改 `launch.ps1`/看门狗、不增加 HTTP 请求、不发业务 POST。

## 启用条件（任何一条不满足，都在 serve 之前失败，bootstrap 回退原入口）

- 设置 `mode=observe` 且 `enabled=true`（bootstrap 已有的约束）。
- 控制目录里有一份 `preflight-series-*.json`：`status=completed`、`enabled=false`、恰好 3 轮且每轮 `measured`、目录失败与不可测都为 0，`planSha256` 与本次 `capturePlan` 完全一致。初步或失败的预检不能激活旁听。
- 计划 `preflightOnly=false`；容量固定 2 GiB；新证据、旧证据、控制目录互不包含；`app.py` 是原宿主文件。
- `observe.intervalSeconds` 300–3600；`observe.routes` 1–16 条，只允许回环地址，键名由观察器校验端口与命名空间一致。

## 运行与停止

- 每个周期先确认外部事实完整（90 秒内观察到的 GET 响应），再取写锁、检查容量、对齐采集、写入存储。缺事实、源文件未审查、容量不足、窗口内变化都只记 `blocked` 和固定码，不重试、不补请求。
- 每次周期后原子写 `observe-status.json`（状态、固定码、计数，不含路径/正文）。
- 在控制目录创建 `STOP` 文件：1 秒内停止采集线程并恢复 Dashboard 的 urllib；Dashboard 进程、健康路由不受影响。停止后需重启宿主才能再启用。
- Dashboard 正常关闭时，先停止采集再结束原生命周期。

## 已知门禁

- `aligned_capture` 只接受 `agent/core/source_profiles.py` 中已审查的 `app.py`。当前生产 `app.py`（SHA256 `a02d25a6…e8b7`）尚无档案，安装后每个周期都会以 `capture_rejected` 记为 blocked，不会产生证据，直到档案经审查合并。
- 首轮包含数据库全量（约 130 MiB），之后预检实测每轮约 4.6 MiB；`CapturePublisher` 为每次采集预留 6×单次上限+16 MiB，可用于存储的空间约 1 GiB。
- 变化日志、R3/R5/R2 证据、两批完整真实比对仍未覆盖；`realShadowPassed`/`switchAccepted` 永远为 false。
