# R0 完善：冻结输入与只读重放（增量工具，不替换旧引擎）

基于 main f78db5a4bfd32eb5ebeab2c63f6dea48cc26f061。app.py 原文经换行规范化后的 SHA256 固定为 f4d754cd86c524933d3f87da1006167c2fd698e288fcda09992115dc0e1c044e；不接受“调用者换个哈希就运行任意代码”。更新旧引擎版本须另审基线，不自动刷新 golden。

## 范围与三层验收

| 层 | 当前状态 |
|---|---|
| 隔离测试 | 20 组合成输入 × 全部28个GET处理器 = 560响应，含调用前后DB逻辑行、文件变化；严格比较 |
| 完整批次真实影子 | 未部署/未运行，未通过；不拿合成case或模拟零差异代替 |
| 切换验收 | 未开始、无切换能力；旧Dashboard读写、代理循环、云端API都未改 |

新增 agent/core/{snapshot,oracle,sandbox,replay,comparison}.py 和显式 tools/r0_replay.py。导入不构造引擎、不开线程、不接网络、不扫描生产。未提交任何生产状态/日志/凭据，fixtures全合成。旧未提交R0草稿保持原样。

## 固定的输入

- 显式列出的JSON/CSV/日志小文件及内容、size、mtimeNs；每文件32MiB、合计512MiB，超过拒绝。不自动遍历所有磁盘。
- ops.db 用SQLite只读URI和backup取得一致快照，逐表保留逻辑行与哈希，只接受ops的6张表（含sqlite_sequence）；users/sessions等其它库拒绝。连接显式关闭，支持Windows删除测试。
- JSON事实：冻结时钟/时区、机器名、进程PID/命令行/创建时间与状态、磁盘/GPU/系统指标、外部HTTP响应、目录/文件存在及stat。媒体可仅保存元数据，不复制大文件，不允许把空占位文件当真实内容读取。
- 配置采用明确的非敏感settings和逻辑根映射；不复制config.json、.env、接收器/百度授权、通知配置。凭据字段、常见凭据文本/私有Webhook等拒绝捕获，坏JSON仍可作为异常fixture。
- 跨文件窗口：捕获前后检查size/mtime与内容哈希；DB逻辑行前/一致快照/后哈希须一致，否则“不可对齐”，不能当零差异。真实来源的并发状态无法冻结时必须重取或记不可比较。
- manifest含源代码哈希、事实和逐文件哈希，sourceIdentity绑定全部已声明输入；改包、缺文件、路径穿越、符号链接/junction、未声明文件访问均拒绝。它提供一致性校验，不是第三方真实性签名。

## Oracle与副作用

不import生产app。对已审固定源文本做AST重放：保留原函数/类体与GET装饰器，跳过CONFIG/STORE/COLLECTOR/FastAPI顶层构造、mount、middleware和__main__。所有数据根定向全新scratch，线程/子进程启动和真实HTTP均禁止。原GET的收据/对账等文件写入、Store更新和错误日志只发生在scratch，并保存调用前后结果。

原外部请求只由冻结响应端口提供；缺失外部源返回已记录的不可用语义，不退回线上。旧业务可能企图POST时直接拒绝，不能造成第二个执行者；R4完整副作用计划/规则验证不在R0“通过”范围。

pathAliases只把原路径字符串映射到scratch，不授权访问原目录。原证据字节不重写；应用读取/枚举/stat/SQLite及写入统一重映射。比较时仅规范化本次测试根（含JSON转义形式），不忽略任意路径。文件与表中的业务身份、错误、时间和顺序保留。

这是一份针对固定可信代码的单线程回放防误访问保护，不是可运行任意Python/原生代码的安全沙箱。不能嵌入正在运行的多线程代理；CLI显式运行，在独立进程结束后恢复所有patch。生产部署/真实采集由Claude审查后另行安排。

## 比较与真实影子门禁

离线不允许任何字段豁免；null与缺字段、bool与int、数组顺序均区分。实时仅允许observation层显式叶节点：/observation/observedAt、/observation/collectedAt、/observation/metrics/sampleTime。业务payload的updatedAt/requestedAt/expiresAt/manifest/attempt/计数/错误/资格/token/收据哈希均不能豁免；无通配或整对象忽略。

门禁需要real-shadow、真实批次开始和完成、各必需目标的正caseCount、同sourceIdentity/comparable和mismatchCount=0；缺样本/不可对齐/非零差异/外部写或业务请求均阻止。工具永远不执行切换；字典字段不证明真实生产，Claude/用户仍须审核原始完整批次证据。R4/R5的77条规则继续待其模块逐条验收，R0不能代签。

## 用法（仅示例，不在本PR运行生产采集）

在独立worktree，用已有Python环境运行：

```text
python -B tools/r0_replay.py capture --recipe <已审的无密钥recipe.json> --out <全新快照目录>
python -B tools/r0_replay.py replay --source <固定版本app.py> --snapshot <快照> --scratch <全新隔离目录> --out <全新输出.json>
python -B tools/r0_replay.py compare --expected <标准输出.json> --actual <候选输出.json> --out <差异.json>
python -B tools/r0_replay.py gate --report <完整真实影子证据.json>
```

recipe必须显式给frozenAt（带时区）、legacySha256、facts、files和databases；数据库逻辑名用repository/data/ops.db，工作台状态用workbench/handoff/…；原路径与逻辑根通过facts.pathAliases一一登记。逻辑根及文件存在性要完整，不得把“不知道”伪装成空目录。所有输出拒绝覆盖现有目标；真实状态不能提交Git、日志或PR，离线包应按用户备份保密规则保存。

## 已知旧行为与限制

f78db5a app.py:6664–6673 在无当前任务箱时subtitle-verification/current会因selected=None进入原500处理器。golden保留500、异常类型与scratch ApiError事件；不是新代码修复，也不表示生产当前正在发生该错误。输入缺失导致的503/404亦不是“业务成功”。

重放直接执行原GET处理器/异常处理器及自有ETag/响应头，不声称覆盖压缩、CSP、TLS等HTTP传输中间件；原安全测试继续单独运行。before表示初始采集后的、GET序列执行前状态，after包含GET的持久变化；源DB本身另有快照哈希。SQLite表按无序关系行规范化，API数组及有序事件不重排。

## Claude重点审查、部署与回滚

1. 固定源AST启动屏蔽、scratch I/O根及别名、native/HTTP/线程禁止；未改生产app.py。
2. 时间/进程/文件stat/外部响应是否足以覆盖真实批次；missing与不可对齐必须阻止资格，不扩大豁免。
3. SQLite一致窗口、秘密拒绝、全局patch单线程边界及连接释放。
4. fixture不是实际影子；待生产恢复与M4期间不部署该家里工具。Claude可在空闲时部署，先用合成样本，实际采集前再审核recipe。

本PR无自动启动、无配置开关变更、无部署。回滚revert本PR/移除单独工具即可；停止工具进程不会影响旧引擎。不要恢复旧DB台账或修改现有流水线。R1/R2继续增量，R3不做，R4/R6开工另需用户确认。
