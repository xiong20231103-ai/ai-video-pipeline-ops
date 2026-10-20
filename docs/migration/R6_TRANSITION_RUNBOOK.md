# R0～R6 过渡接线与退休交接

本文件是待 Claude 审查的操作设计，**不是部署授权或生产验收记录**。本 PR 不创建生产计划、开关、端口、任务或批准文件，不恢复 SPC 德语，不发起业务请求。所有示例路径由执行者在本机填写，不包含凭据。H2 五类目录不在范围内。

## 机制与权威

R0～R5 在保留的 Dashboard 进程启动前逐块装载候选函数。沿用同一个 Store、Collector、状态目录、控制命令锁、三类清理锁、票据缓存及 ContextVar；不是运行两个采集器再同步两个数据库。FastAPI 的 endpoint 和实际 dependant.call 同时绑定候选函数，后台扫描与到期待删区清除受同一所有权租约保护。

| 阶段 | 候选范围 | 仍保留的权威 |
| --- | --- | --- |
| R0 | 标准答案与证据门禁，旧函数不替换 | 原 Dashboard 数据与所有函数 |
| R1 | collection_logic 顶层函数和 Collector 实例方法 | 原 Store 实例及尚未迁移的写操作 |
| R2 | 新增云端历史导入/查询，不创建第二个家里投影 | 当前共享数据；历史选择是独立的云端操作 |
| R3 | ordinary_logic 普通命令 | R4 恢复与 R5 清理仍为原算法 |
| R4 | recovery_logic + 工作台协议 2 原期限/撤回 | 原工作台 RecoveryControl 文件和权威锁 |
| R5 | cleanup_logic，复用 H2 待删区 | 同一个 pending_delete 与清理票据 |
| R6 | 组合原生宿主迁入现有代理 | execution.db 与唯一 ExecutionWorker 不变 |

R0～R5 不需要在同端口上同时运行两个 HTTP 服务，因此不采用待选的地址分离方案。最终 R6 才停止旧进程并禁用旧自启，代理仅提供 `127.0.0.1:8765` 的 GET 兼容入口；任何 POST 均拒绝。不新增公网端口、不改 M0 防火墙、不启用 Funnel。

## 单执行者与 18790

过渡期已有 ExecutionWorker 先持久化 sent，再向云端取得 `/start` 的 sendPermitted。StagedBackend 才能在**同一 execution.db** 写入一次性投递许可，向保留宿主发送带原命令 ID、台账 ID 的请求。宿主校验契约、正文、台账 sent 行、期限和许可后，事务内领取一次性 admission；重复请求拒绝，丢回包仍为 unknown，不能重发。

`migration_permits` / `migration_dispatches` 只是现有台账的许可与接收记录，没有第二队列、令牌或执行线程。单有 sent 行不足以投递（它可能写在取得云端许可之前）。许可领取后进程中断，也宁可待人工对账，不能再执行。

18790 源码中 summary、恢复回执、字幕核验为 GET，安全继续/撤回/上传重扫存在独立 POST。没有现有队列许可的 POST 在读正文前即拒绝；不能仅关闭 autoRecovery 就假定不存在手工写入口。Claude 须核实其生效主、备用地址全部指向受门禁的宿主；配置值不写入报告。原闭集命令契约不包含 `/api/control-commands/{id}/cancel`，因此不能通过过渡桥直接撤回已下发的恢复请求；执行中/unknown 仍只能按原编号对账，不能另发请求绕过。协议 2 的撤回算法本身保留、隔离测试保留，未擅自扩充云端契约。

## 各阶段启动前由 Claude 做的事

1. 用户安排流水线空闲期；保持 autoRecovery=false、cleanup=false，暂停云队列并核对 leased/sent/unknown=0、未对账恢复请求=0。不能凭人工勾选替代实际核对。
2. 审查完整批次真实影子：同一构建、同一源身份、完整目标、零差异、零业务请求、零临时区外副作用。R4 另需前 42 条规则，R5 需全部 77 条规则的正反例。隔离样本不能填成真实影子。
3. 备份代码、原任务 XML、状态与原启动参数；确保工作台协议 2 PR 已配对部署。暂停代理并等待合作停止及锁释放；在空闲窗口停止原 Dashboard，再由原任务运行 `python -B -m agent.legacy_host --plan <本机审查计划> --confirm R6_LEGACY_RESTORE_REVIEWED`。这属于 Claude 部署操作，本 PR 不执行。
4. 计划顶层沿用 `R6_LEGACY_START`：显式 legacyRoot/agentState/fenceRoot/fenceId、旧 app SHA256、recoveryModule SHA256 和原工作台 control 目录。transition 段包括 schema=1、stage、build、ledgerId、approvedBy、未来不超过一小时的 expiresAt、上一条 active.json 的 canonical SHA256、影子报告路径和 SHA256、排空/回滚/旧入口禁用核验。R2 之后须 historyReadyVerified=true，实际导入代已 ready 且核对完成。
5. 仅允许 R0→R1→R2→R3→R4→R5，不能跳级。降级要单独 rollbackApproved；同阶段重装要 reinstallApproved；均重新审查和重置观察起点。一次只运行一个保留宿主；不能在已有 Collector 运行后热安装。
6. 初次启动先写 `migration/active.json` 的 prepared 状态。代理的 `migration-settings.json` 只包含 schema=1、计划路径、原始文件 SHA256。计划不得包含令牌或密码。指针必须以现有 atomic_json 原子写入；不与 engine-settings.json 共存。
7. 隐藏启动原有代理任务。代理收到真实 health 的 ok=true 且 collectorRunning=true 后，将记录改为 active，并写入实际 acceptedAt。冷启动只恢复完全相同计划/构建/台账，不延长期限、不重新导入、不重新设观察时间；计划或指针变化时拒绝后端调用，心跳继续报告故障。
8. 通过只读观测确认实例唯一、原命令回执可查、GET 内容一致、采集耗时和页面时延正常。再由用户/Claude 单独决定恢复队列；工具不自动恢复。

R2 继续使用已审查的 `history_export.build_bundle` 与 `history_transfer.transfer`，输入是明确捕获且哈希验证的 Snapshot，不扫描猜测生产路径、不运行隐式历史同步线程。导入沿用同一 generationId 分块续传；ready 之前不选为权威。timeline 只报告证据能支持的阶段时间/失败/等待人工区间；缺身份或时间时保留 unresolved，不能伪造精确耗时与 ETA。最近 N 代 ready 清理及选中代保护已同步 main 的 #46。

## 过渡阶段回退

Claude 暂停/排空/对账、合作停止代理，并在空闲时停止保留宿主。备份当前 active.json 与计划，不恢复旧数据备份覆盖新命令。使用指向较早 stage 的新审查计划、previousSha256 绑定当前记录、rollbackApproved=true，再按原包装入口启动；仍共享现有 Store/状态和唯一台账。验证 health 后重新记录观察起点。代码本身如需降级，使用已校验源码包回滚，先清除/回退对应模式指针，不能让旧源码误读新指针后无门禁回落。

## 最终 R6（须 R5 连续两周无回退）

1. 真实影子、逐块切换均已验收，R5 active 记录连续至少 14 天、期间无回退；旧系统全程可用。最终审查绑定本机 `migration/active.json` 的 canonical SHA256、构建、原台账 ID、全部阶段列表和 acceptedAt。单独填写更早 r5AcceptedAt 无效。
2. 用户/Claude 暂停并对账、备份，停止保留 Dashboard 和禁用其已核对自启。不得停止工作台、接收器等无关程序。确认旧服务已退出。
3. 执行审查后的准备命令：`python -B -m agent.cutover park-transition --plan <R6_PARK计划> --confirm R6_PARK_REVIEWED`。它合作停止现有代理、持有维护锁、备份过渡指针与 active 记录，移除本项目过渡指针；**保留维护，尚未启用原生宿主**。失败不恢复发送。
4. `python -B -m agent.cutover stage --plan <原生settings计划> --confirm R6_STAGE_REVIEWED` 复制白名单 JSON 和只读 SQLite seed 至独立候选状态目录；不复制素材/日志/凭据。再审查生成的库存、seed 和配置哈希，制作最终 R6_SWITCH 审批及原生 engine-settings。所有计划仅留本机，不进 Git。
5. Claude 原子安装已审核原生指针、选择 candidate 所有权，按原维护工具 finish **park journal 中同一个 requestId**，再隐藏启动原任务。旧指针与原生指针共存会拒绝；原生首次成功扫描前写操作拒绝；旧启动项或进程仍活着会拒绝。当前构建、旧记录、配置、seed、证据不一致均拒绝，不回落旧 POST。
6. 验证 loopback GET、18790 无循环锁等待、真实缓存/回执、任务自启/重登/重启、队列与通知。切换验收由用户/Claude 完成，不用隔离测试替代。旧源码、环境、配置、备份和回退任务再保留至少 14 天，不自动删除。

## 最终 R6 一条命令回退

审查计划必须带 `transitionBackup`（第 3 步输出的目录），并绑定原台账、任务定义和旧状态库存：

`python -B -m agent.cutover rollback --plan <本机R6_ROLLBACK计划> --confirm R6_ROLLBACK_REVIEWED`

工具合作停止代理、备份新旧台账、确认没有丢失旧 tasks/history，迁回新期间的白名单状态和投影、收回候选权威、恢复原过渡指针后启动保留宿主。R5 标记重置为 prepared/acceptedAt=null，真实 health 后重新计时。执行台账/凭据不变；云队列始终暂停，启动失败保留维护。任何 unknown/未对账请求、旧库被改动、历史缺行、任务定义不符都拒绝自动回退，交人工处理。

## 验收分层

| 层次 | 本 PR 的状态 | 能说明什么 |
| --- | --- | --- |
| 隔离测试 | 以本次完整回归和 CI 为准 | 合成输入、临时 SQLite、进程内 HTTP、门禁与回滚边界 |
| 完整批次真实影子 | 未运行/未通过 | 必须逐块完整批次、规则零差异才允许申请切换 |
| 切换验收/两周观察 | 未运行/未通过 | 由用户安排，Claude 部署；不在本轮自动执行 |
| 旧进程退休/旧文件保留 | 未执行 | 只能在上述真实门槛满足后进行 |

Claude 重点审查：共享状态的所有方法绑定、旧后台租约、队列许可至宿主 admission 的事务边界、18790 全部备用地址、协议 2 配对、R5 时钟与回退重置、原生模式指针互斥、旧启动项清单、Windows 任务与地址的现场行为。不能把本文件作为这些现场事实已经成立的证明。
