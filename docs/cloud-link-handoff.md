# 云端素材副本：保存与只读查看

PR #63 仅实现公司采集链接/状态/展示截图的云端副本，保持现有采集、判图、确认及递交业务不变。
模块默认关闭，不增加监听端口，继续使用现有 loopback 后端和 Tailscale HTTPS。

## 四个接口

| 方法 | 路径 | 权限/用途 |
|---|---|---|
| POST | /api/links/ingest | 专用Bearer令牌，接收来源事件 |
| GET | /api/links | 原有登录会话，分页只读查询 |
| GET | /api/links/shots/{sha} | 原有登录会话，读取展示截图 |
| GET | /links | 原有登录会话，只读页面 |

不注册decision、changes、deliveries路由，不导入或调用CommandQueue来递交素材。
遗留配置中即使误留写功能开关，也不能启用不存在的路由，测试覆盖此边界。

## 数据和幂等

独立SQLite位于证据目录links.db，截图在shots/日期/，截图按SHA256去重。
幂等键为source/platform/video_id/judge_round，来源seq持久化递增。
较新事件更新状态；相同或更低seq不能回退状态或替换已有截图。
若记录尚无截图，重试允许仅补图，保留当前seq、URL、状态、决定时间及元数据。

审核与投递状态独立，confirmed+waiting表示已收录未递交。
尚未进入审核的候选review为空，不伪装成pending或expired。
页面分别显示来源数据库pending数及带来源展示条件标记且有图的可展示数；本模块不重新判图或选择业务队列。

单次请求流式限制2MiB、每分钟60次；JPEG最长边1600、单张600KiB以内，加载校验实际JPEG内容。
令牌由用户本人设置为服务环境变量，不进入仓库、日志或聊天。图片和链接不向公网匿名提供。

## 保留与备份

pending引用的截图不因过期或容量压力删除。已处理截图从决定时间算15天；
历史决定时间未知、未进入审核的记录从首次上传算15天，不用更新时间冒充决定时间。
链接与状态长期保留。容量上限5GiB，先删最旧已处理图；仅剩pending时拒收新图，仍接收链接/状态并报警。
同一张图被多个记录引用时，任一pending引用都会保护它。

每日清理输出删除张数和释放字节；在线SQLite备份保留7份，截图不备份。
维护service/timer仅作为待审查文件提供，当前未安装。

## 验证和后续

测试使用unittest，由tools/run_isolated_tests.py发现，禁止生产网络、进程和目录写入。
部署准备见link-evidence-deployment-checklist.md。审查摘要见CLOUD-LINKS-REVIEW.md。
远程确认、动作流、递交及对应测试保存在独立draft/cloud-link-actions分支，6个阻断项解决前不进入main。
