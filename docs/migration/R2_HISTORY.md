# R2：独立历史台账、证据迁移与耗时模型

基于 R1 #41 / R0 #40。这是新增并行历史来源，不替换 app.py、云端旧缓存或现有任何读写接口，不参与执行、安全继续、清理。家里代理默认循环未接入，不增加轮询/计划任务/进程；云端 history_enabled 缺省 false，只有显式 true 才建独立 history.db 和挂新接口。本 PR 不部署、不启用、不合并。

## 一致证据与传输

输入仅为 R0 验证过的 Snapshot；再次校验来源与文件哈希。只读原 ops.db 的一致副本：tasks、task_history、events、heartbeats、source_health、sqlite_sequence，逐表原主键保留。JSON 收据/对账/reset/交接记录、Fish CSV 等按显式逻辑白名单保留原字节；证据切成128KiB片段，再编码进不超过1MiB的传输块。原媒体、草稿、截图、缓存、配置、密钥和原始日志不会进入新历史数据包；未导出文件清单显式写 coverage，不当作已迁移。

每个来源提供显式 source、单调 sequence、resetGeneration 和 snapshot sourceIdentity；不从任务名猜 alias 或 reset。generationId 绑定整个 manifest（含每块哈希、全量行数/分类计数/有序主键内容哈希和覆盖说明）。独立 schema 校验秘密字段/文本，证据重组后再查 JSON/CSV，避免编码绕过。

full 导入是完整新历史来源；delta 绑定明确的已确认 baseGeneration，包含 insert/update/delete，删除不会让旧版本消失。跨 reset 禁止 delta，必须 full；旧 reset 版本继续可按 generationId 查询。alias 仅在指定 reset 代次内有效，循环/冲突拒绝，原任务 ID 不改写。

云端 staging 不可查询成正式来源。块可乱序、重复块幂等；同 key 跨块冲突拒绝。finish 在独立 history.db 同一事务中验证完整块、所有行/计数/哈希、精确证据重组、alias/reset、timeline 合同，再以 base compare-and-swap 选择新历史来源；不清空 console.db 混合新数据。丢回包只查询同 generationId/补缺块，不创建新 ID，不发任何家里请求。

回退仅在新历史库选择旧 ready generation，保留 sequence highwater，防止旧导出重放覆盖新来源。分页返回 generationId，后续页必须固定它，避免中途导入混页。保留 selection/change 审计。不提供生产恢复或切换旧引擎的功能。

## 容量与门禁

单代最多200,000行、256MiB规范化逻辑内容；每来源最多10个保留代次，云端逻辑配额缺省512MiB。分块写入受已保留字节/行上限约束，不能谎报小配额后填大库。delta 暂存可能先到新增键、后到删除键，因此临时配额显式预留旧代+目标代大小，finish后收回到实际目标大小；不会因缩小历史来源而错误拒绝合法删除同步。SQLite索引/WAL/页开销不计在逻辑配额中，需要实际部署时另留磁盘余量；本轮没有测真实全量大小。超限拒绝，不静默丢历史、不自动删旧 ready 版本。24小时过期的 staging 不可完成；可显式 discard_staging（固定确认短语）释放失败暂存，ready/active 不能删除。

这些是隔离阶段的保守限额，不是生产容量已通过。真实快照若超限、来源缺失或字段未映射，应记录失败/缺口交 Claude 复核，不扩大白名单或自动裁剪。

## 逐项目/逐视频时间与来源口径

参照《生产耗时分析_2026-10-07至10-16.md》，保留以下区别：

| 来源 | 定义位置（只读参考） | 新实现与精度 |
|---|---|---|
| 工作台持久日志 | workbench.py:103–116、2999–3005；后台启动7448附近、voice交接4482附近、step4交接7909 | workbench_log_events；逐行上下文绑定身份。日志秒级 marker 为 reported±1秒；第1/2步合并，不猜下载/去字幕各自时间 |
| 剪映 VideoTask | Core.cs:807–925 | ContractBatchId、RemotePipelineTaskId、CanonicalTaskId/Id、HandoffAttemptId/HandoffManifestId；StartedAt/FinishedAt，缺身份/时区则列 unresolved |
| 剪映子步骤日志 | Core.cs:1501–1510；BatchRunner.cs:1487–1520 | capcut_log_events，明确上下文+步骤名映射。保留原边界及单独 reportedSeconds（Stopwatch四舍五入一位小数），不拿文件名猜所属项目 |
| SQLite 状态采样 | app.py Store.task_history | sampled_task_history 仅状态观察、75秒不确定度。旧行无 attempt/manifest，不能借 tasks 当前身份；需逐行不可变证据映射，否则保留原行并记缺口 |
| 下载/去字幕run、Fish CSV、拼接/上传JSON | 对应证据版本的明确字段映射 | structured_stage_events 支持项目/视频两层开始、结束、失败、人工等待、主动暂停；不使用mtime补时间。未知schema/缺时间/身份列 unresolved，不伪造区间 |

normalize_snapshot 只处理 recipe 指定的已声明文件；format 为 capcut_tasks/capcut_log/workbench_log/structured_json/structured_csv。recipe 显式写版本、网络配置标签、rowsPath、身份字段、时间字段或已核对行号上下文。默认不提供生产 recipe，不扫描生产日志或猜对应关系。CLI 支持 --recipes；未提供则 coverage.timelineNormalization=not-requested，不能声称逐步骤历史完整。

timeline保留事件主键、来源SHA/cursor/版本/网络标签、批次/项目/视频/manifest/attempt、时区、失败码、prefetch、精度。相同日志追加后 sourceSHA 变化不导致同一行重复计数，逻辑行身份稳定；不同内容同事件ID拒绝。事件关联缺 start/end、重复 start、未结束区间都作为问题显式输出。

同一项目/视频的并行与预取时间使用区间并集，不直接相加。explicit human_wait_start/end 与 pause/resume 分开；相邻剪映成片完成间隔>15分钟只记 heuristic_unclassified_gap，绝不标为已证实人工等待。日志推算边界/采样不能显示精确 elapsedSeconds，保留 observedSpanSeconds 和 rangeSeconds。

ETA 只取同版本、同网络标签、成功且精确、无显式人工等待/暂停/失败重叠的区间，至少3个样本；要求剩余数量和明确串并行 plan。并行波次取最大、串行波次相加；用户暂停、版本未知、数量/计划未知、样本不足都返回 available=false / expectedAt=null。不自动继续、不承诺未来不会失败。网络直连前后及0.6.21前后不混基线。

## 接口与开关（本轮不启用）

- agent固定令牌认证：POST /agent/history/begin、/agent/history/{id}/chunks/{position}、/finish；GET /agent/history/{id} 查询确认。仅写云端独立历史库。
- 已登录用户只读：GET /console/history/{source}、/records、/timeline?batchId=…&projectId=…。
- 历史来源回退：POST /console/history/{source}/select，现有session+Origin/CSRF，confirmation=ROLLBACK_HISTORY_SOURCE，仅选择同来源ready代次。
- history_enabled=false 时不挂任何新路由、不建历史库，旧页面/缓存/命令不变。清理和autoRecovery开关均不动。

## 隔离用法

```text
python -B tools/r2_history.py export --snapshot <已审R0快照> --source home --sequence 1 --recipes <无密钥schema映射.json> --out <全新私有包目录>
python -B tools/r2_history.py verify-import --package <私有包目录> --new-db <全新临时目录/history.db>
```

工具不覆盖既有包/既有DB，verify-import 只允许新库。无后台线程、无进程启动、无网络、无服务重启、无恢复到生产。recipe和原始真实证据不提交PR。transfer API 未挂到 agent worker，不读令牌，不写agent.db正文副本或新增持久outbox；只保留人工显式隔离包，审查后按现有保密备份策略管理。

## 验收与Claude重点

隔离覆盖全量重导入/delta更新删除、重复块/丢确认重试、缺块/篡改/假计数、CAS冲突、reset/alias循环、回退highwater、固定代次分页、编码秘密拒绝、精确JSON/CSV证据、登录/agent/CSRF、默认关闭、逐项目逐视频时间/重叠/失败等待/采样/缺身份/ETA。

尚未进行任何真实生产导出、完整批次影子、容量/性能验收或切换；不能用合成结果标为真实通过。Claude需审核真实源schema、行号上下文和身份映射、完整旧历史覆盖、限额与性能、历史selection边界，再在空闲期安排只读影子。用户恢复生产/M4期间不部署家里变更。

回滚：保持/恢复 history_enabled=false，或选择新历史库旧ready来源；旧Dashboard始终保留。若未来部署本PR，云端先按现有流程备份再部署，家里仅Claude审查部署；本轮不执行这些步骤。revert 本PR不会改旧台账。R3未开始，R4/R6另需用户确认。
