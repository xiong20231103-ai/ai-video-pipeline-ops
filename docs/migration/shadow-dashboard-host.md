# Dashboard 旁听宿主生命周期（默认关闭）

本次只交付接线与隔离演练，不是家里安装或真实影子验收。app.py、cloud/、agent/ 和旧启动器不变；没有环境变量自动激活，没有计划任务注册，没有业务 POST，没有进程启动/终止，没有引擎切换。

## 为什么需要此补充

旧 Dashboard 的 `control_plane_json` 使用本机 18790，而观察器此前只接受 8765/8766。现在显式允许 18790 的 `control:/api/...` 事实，保持 8766 为 `receiver:/api/...`，拒绝端口/命名空间不一致。绑定验证实际 URL 端口，18790 只接受与原代码一致的回环主机。不会增加 GET 请求来补缺失事实。

## 空闲窗口启动入口的接法

只在显式调用 `DashboardShadowHost(..., enabled=True)` 时绑定指定模块的 urllib 命名空间。默认 enabled=False 时既不换 lifespan，也不换 urllib、不创建线程。

调用方在服务启动前，使用已经审核的 CapturePublisher、精确 GET 路由和进程探针：

```python
from tools.shadow_dashboard_host import DashboardShadowHost, attach_lifespan

host = DashboardShadowHost(
    dashboard.__dict__, publisher, reviewed_routes,
    enabled=explicit_shadow_enabled,
    maintenance=reviewed_maintenance_probe,
)
detach = attach_lifespan(dashboard.app, host)
# 保留原 dashboard.app、CONFIG 的监听地址/端口以及原服务器参数。
# 只在服务器已完全退出后调用 detach()，不能向运行中服务注入。
```

这不是可直接复制到家里启动器的安装命令：publisher、路径闭合计划、进程事实、准确外部路由尚须核实，不能用空探针冒充完整事实。不得导入另一个 app 实例或并行启动第二个 Dashboard 采集器。

原 lifespan 的启动、yield 状态和关闭流程都保留。原启动失败时不开始观察；观察器绑定或采集失败不会抛入原服务。停机先发停止事件，异步等待采集线程至多2秒，再恢复自己持有的 GET 代理。线程仍在收尾则报告 blocked，禁止自动重启/杀死线程；后台线程为 daemon，不阻止进程正常退出。采集器原有硬配额和稳定窗口门禁保持不变。

## 停用、维护和看门狗边界

- 维护探针为 true 时暂停新采集，不增加请求；不删除旧快照、不抹去 blocked 证据。
- `host.status()` 只返回固定码和生命周期状态。原始异常、响应正文、路径不进入状态。
- 首次采集卡住或后续周期超过两倍间隔时 stale=true；采集器返回 blocked 时宿主也显示 blocked，不能只凭线程活着认定健康。
- 看门狗可读状态并报警。本接线没有重启生产程序、重新 POST、清理锁或删除证据的能力。
- 停用：在空闲窗口正常停止宿主，close 完成后 detach；恢复部署前启动入口。已经停止的 host 对象不能再次 start。
- urllib 或 lifespan 已换持有者时拒绝覆盖；回滚不能覆盖别人后续接线。

## 安装前仍缺的项目

1. 宿主实际启动器和看门狗的盘点、备份与精确回滚命令；当前 PR 没有修改它们。
2. 真实文件、明确缺失路径、目录元数据、进程出生身份和外部端口的完整采集计划。
3. 原旁听记录器接近2GiB配额，须保留原证据并核实可用容量，不能默认扩容或删除。
4. R3 端口记录、R5 真实保护/执行及 R2 时间线口径；目前只读回放不能替代这些证据。
5. 两批完整真实零差异报告及操作触发覆盖。realShadowPassed/switchAccepted 始终为 false。

当前真实批次运行期间不得安装，不重启 Dashboard、工作台、上传服务或代理，不开 cleanup/autoRecovery。
