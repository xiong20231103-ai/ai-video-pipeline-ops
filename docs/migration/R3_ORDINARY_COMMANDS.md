# R3 普通命令候选模块

开发范围：建任务、补链、开始、撤回、上传重扫、历史上传核验。候选代码、独立回放、原持久执行台账接点和跨进程写门禁交付审查。默认代理仍使用旧 Dashboard；本 PR 不选择候选后端，不改 app.py、cloud/、static/，不安装任务或启动任何程序。

依赖链为 R0 #40 → R1 #41 → R2 #42 → 本 PR。家里部署、启动接线与切换只允许 Claude 在用户安排的空闲期审查执行。R4/R6 仍需用户开工前确认。SPC 德语的主动暂停不构成本模块的测试对象。

## 原码映射

固定源：`f78db5a4bfd32eb5ebeab2c63f6dea48cc26f061`，app.py SHA256 `f4d754cd86c524933d3f87da1006167c2fd698e288fcda09992115dc0e1c044e`。

| 命令 | app.py 函数/行 | 候选 ordinary_logic.py | 实际本地效果 |
|---|---|---|---|
| 建任务 | control_create_task 6415–6423 | 383–391 | POST 接收器 /api/tasks/create |
| 补链 | control_replenish_task 6427–6435 | 394–402 | POST /api/tasks/replenish/{id} |
| 开始 | control_start_task 6439–6441 | 405–407 | POST /api/tasks/{id}/start |
| 撤回 | control_cancel_task 6445–6447 | 410–412 | POST /api/tasks/{id}/cancel |
| 上传重扫 | control_upload_rescan 6700–6709；request_upload_rescan 2832–2859 | 415–424、303–330 | 盘点第四到第五步清单；确保上传 worker；历史核验；写 control_actions |
| 历史核验 | control_upload_verify_history 6713–6722；request_historical_cloud_verification 2759–2829 | 427–436、230–300 | 选择 uploaded 且 cleanupPolicyVersion<2、无 cloudVerifiedAt 的任务；写核验请求；确保 worker；写 control_actions |
| 共同依赖 | receiver_json 2902–2930；_ensure_upload_service_running 2676–2723；save_control_action 2507–2513 | 352–380、147–194、70–76 | 保留 HTTP 错误、3秒接收器超时、隐藏启动及台账行为 |

`r3-provenance.json` 列出全部 25 个定义、每个函数原行号与候选行号，以及 20 个必须显式注入的端口。隔离测试验证逐个 AST 函数体一致（仅移除 HTTP 路由/异常处理注册装饰器），没有新生产算法。工作台启动/恢复桥及安全继续留在 R4；接收器本身的单实例与启动合同仍由接收器负责，R3 不另起工作台。

## 执行合同与一个写入者

`ExecutionWorker(agent, ordinary_backend=...)` 只是显式可选接点，默认值 None。现有 ReadOnlyAgent 启动路径没有注入候选。候选无监听端口、无调度线程、无独立 execution.db、无配置/令牌读取，也不借导入旧 app 获取全局对象。

未来受控宿主必须显式提供配置、路径、Store 事件端口、时钟、HTTP/进程端口，并把一个 OrdinaryCommands 绑定到原来的 ExecutionWorker。不能另起执行 worker、复制原 execution.db 或在影子阶段注入真实写端口。注入接口和 wrapper 是部署准备能力；实际宿主接线与启动入口核对仍待 Claude 的部署审查，本轮未执行。

原云队列 → 原 ExecutionLedger 接收/身份校验 → 持久化 sent → 云端发送许可 → 再查停止与有效期 → 原 worker 选一个后端 → 持久化结果 → 仅重传结果。重复 lease、同 ID 重投、sent 后崩溃、unknown 与已确认收据均沿用原台账，不创建第二份去重表。HTTP 4xx/5xx 是最终 HTTP 回执，不自动重发。候选已开始但结果序列化/读取不完整、结果超界则 unknown；没有“候选失败再发旧 POST”的回退。

`OrdinaryFence` 使用同一 owner.json 和 writer.lock（Windows msvcrt/Linux flock + 进程内锁）：

- prepare 仅能初始化一次，初始 owner=legacy；缺失、损坏、链接/目录联接、锁占用均拒绝写入，不自动重建。
- `FencedDashboard` 包装原 ASGI 应用，所有六类旧 POST 全程持 legacy 锁；candidate owner 时 409，门禁不可用时 503。旧 GET、R4/R5 与其他路由继续交给旧应用。
- 候选先核对包装器的只读 capability：协议、相同 fenceId、owner=candidate、legacyWritesBlocked=true；再持 candidate 锁执行。证明不符直接 not_sent，绝不走旧 POST。
- select 只在同一原生锁内修改 owner。需显式人工审查确认、相同 fenceId、云端暂停/排空、leased/sent/unknown 均为零、旧侧门禁安装与完整影子已审。证据字段是操作员声明，不能冒称独立证明或用测试中的合成值申请切换。没有 worker/CLI 自动调用 select。

必须核对所有 launch/watchdog/计划任务/手工启动路径都经过 wrapper。只改一个启动入口而其余仍能启动裸 app 时不准切换；capability 不能证明未来另一入口不会绕过门禁。本 PR 的 `tools/r3_fenced_dashboard.py` 只是未来显式宿主：准备门禁后才导入旧 app，转发 lifespan；本轮没有运行。停用 wrapper 或裸启旧 app 前，必须先把 owner 切回 legacy 并解除候选绑定。

receiver 来源的 `/api/batches`、恢复、清理、测试 reset、任务箱 reconcile、字幕重试预览均不属于候选 allowlist。它们保持原来执行路径，不能借 R3 顺便迁移。

## 固定回放与异常边界

`tests/fixtures/r3/cases.json` 与 expected.json 包含 63 个合成场景。`python -B -m tools.r3_command_replay` 在两个全新的临时根分别重放固定旧函数和候选，比较响应状态/头/正文、前后文件、控制台账、核验请求、转发目标/请求体/超时、隐藏启动参数、错误事件及虚拟时钟。HTTP 和进程端口只记录计划，不建立网络连接或启动进程。

覆盖四类任务命令的成功、400/409/500、3秒超时、IncompleteRead、坏 JSON/错误形状、非本地请求、意外异常；建任务/补链另含坏请求正文。两类上传覆盖无待核验、已在核验、运行文件缺失、启动失败/超时、已有 worker；重扫另含去重、成片丢失和未完成任务。另测故意改变结果确实产生差异。

本 PR 特意保留并单列旧行为，不能将 golden 相同解释为修复：

1. 历史核验请求在检查/启动 worker 前落盘；之后 HTTP 503 仍可能留下请求，用户不能据错误推断“未发生写入”。已有 execution.db 会禁止同一命令自动重发。
2. 旧 rescan 在 worker 未启动时仍返回 accepted/running=true。回放锁定了该兼容行为；启动失败测试通过只表示相容，不等于服务已恢复。本轮不改旧 Dashboard 的业务语义。
3. receiver_json 对 IncompleteRead 由旧总异常边界产生 HTTP500/ApiError；保留该结果。若连错误记录/回执都失败，外层是 unknown。

允许差异只有测试临时根映射为 `$SNAPSHOT`，JSON 序列化的结构表示；随机 ID/时区/时钟都固定，业务时间、计划、计数、错误和任务身份不抹掉。真实影子不可比较的取数窗口必须单列，不能算零差异。

## 验收分层及后续步骤

| 层级 | 状态 | 通过条件 |
|---|---|---|
| 隔离测试/合成标准答案 | 见 r3-acceptance.json 与 PR 最终 CI | 63 场景零差异，台账/门禁/异常测试通过 |
| 完整生产批次真实影子 | 未运行，batchId=null | 同一固定输入/身份，比较资格、目标、拟写请求/索引/清单与操作计划；禁止双发、双启动；异常样本另测 |
| 真实执行及切换 | 未开始 | Claude 审查和空闲部署；用户安排生产后逐类一次执行与回执对账，重复投递不重复执行；影子零差异后才可申请切换 |

不能把63个合成场景、合成 gate 字段、HTTP 返回成功或父模块测试算成真实批次影子通过。R4/R5 的全部规则也没有因此获验收。R3 没有读取生产快照、没有真实业务 POST、没有安装/重启 wrapper、没有选择 owner。

未来切换准备顺序：冻结来源/备份 → 云端暂停并核对在途与 unknown → 核对全部旧启动路径 → 先安装 owner=legacy 的 wrapper → 真实只算不用的完整批次与异常回放 → 人工核对证据 → 空闲时在同一锁内 select(candidate)、为原 worker 注入候选 → 验证旧普通 POST 被拒、新命令回执与去重 → 解除暂停。不要用本项目被暂停的 SPC 德语验证。

## 回退

本轮没有生产变更：撤销本 PR 即撤掉休眠模块，原默认 worker 不受影响。

未来已切换时，先云端暂停 → 查清并排空在途、人工处理 unknown（禁止重投）→ 原生锁内 select(legacy) → 移除候选注入 → 验证旧六类 POST 由 wrapper 放行 → 再解除暂停。owner 与 backend 不一致时应拒绝而非自动降级。保留同一 execution.db，绝不恢复旧台账覆盖新收据。需退回裸 app 时最后才撤 wrapper；具体部署备份/一条回滚命令由 Claude 在真实部署前生成，本轮没有虚构服务器备份。

Claude 重点审查：完整源码映射；显式端口/路径配置；每个启动入口的 wrapper 覆盖；单 worker、sent/unknown 不重发；上传请求先落盘与旧假阳性字段；真实影子输入及不可比较窗口。未满足者维持原后端。
