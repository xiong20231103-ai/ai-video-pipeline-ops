# R1 并行采集与投影（不接管旧引擎）

基于 R0 #40。独立 checked-in collection_logic.py 包含 38 个原业务定义；不运行时读取/解析生产 app.py、不 import 生产应用、不替换旧接口。CollectionSession 对每个实例绑定独立端口和内存 SQLite 投影，50 MiB / 200,000 行上限，超限拒绝，不截断后冒充完整。seed 仅由已核验快照的隔离 DB 提供，不能传线上连接。扫描失败后禁止返回半成品投影，成功重扫才恢复。

没有接到 agent/readonly.py、没有后台线程/计划任务/开关启用，没有新增家里轮询。原 app.py 读写不改；候选类移除了 start/stop/run/reset_runtime、Store 的文件库连接和 clear_all。单次显式 scan 只在快照隔离环境运行。未来真实影子采集必须由 Claude 审查、在空闲期安排，不在生产恢复/M4 期间部署。

## 模块边界与适配器

summary/dashboard/pipeline/task-box/概览/指标/服务源健康/当前项目/字幕投影由新代码执行。收据持久化和归档属于 R2、reconciliation/health/recovery 属于 R4；这些是显式 deferredAdapters，**未宣称 R1 已迁走其副作用**。R0 冻结环境在测试中提供适配器，文件副作用只留 scratch。安全面板 GET 路由仍由标准答案壳层调用，并使用候选事实域；不复制安全继续执行器或清理器。

运行时端口为显式参数，必须包含 provenance 列表中的全部依赖；本 PR 唯一提供的运行入口是已核验快照的离线比较 CLI。不提供直连生产的端口实现。FunctionType 仅为每实例重新绑定已提交的函数 code object，不执行网络下载代码或动态 app 源码；类 staticmethod 也重新绑定。此工具是单线程，不给运行中的代理注入全局 patch。

## 隔离验收

- 同一 sourceIdentity 的 20 场景 × 28 GET 比较状态码、JSON、业务时间/身份、头部、GET 前后文件/表以及外部只读调用；无业务字段豁免。
- AST 对照测试校验 38 个业务定义与固定 f78db5a 原码相同，仅显式移除生命周期/文件连接方法。独立修改候选 overview 后比对必须失败，避免比较器空跑。
- 缺端口、未知写投影、超限、失败后半成品、不同实例配置/Store/Collector 隔离均有测试。
- 真实影子：未运行；切换验收：未开始。560 个合成案例零差异不等于完整生产批次通过。

```text
python -B tools/r1_shadow.py --source <固定f78db5a源码> --snapshot <已验证R0快照> --scratch <全新目录> --out <全新差异报告>
```

输出为 isolated，realShadowPassed=false / switchAccepted=false；既有路径拒绝覆盖。CLI 禁止自动部署或切换。R0 的 source hash、秘密拒绝、写入/网络/进程边界继续有效。请求冻结来源缺失返回旧不可用语义，不回退线上。

## 原实现 → 新实现

行号对应固定 f78db5a app.py 和本 PR collection_logic.py；精确机器表见 r1-provenance.json。

| 定义 | app.py | collection_logic.py |
|---|---|---|
| split_completed_cleanup_warning | 161–180 | 9–28 |
| now_iso | 183–184 | 31–32 |
| parse_time | 187–193 | 35–41 |
| safe_int | 196–200 | 44–48 |
| sanitize_public_value | 203–214 | 51–62 |
| resolve_path | 217–219 | 65–67 |
| read_json_object | 593–602 | 70–79 |
| _workbench_root | 1603–1616 | 82–95 |
| is_test_history_task | 2862–2880 | 98–116 |
| Store | 3000–3306 | 119–402 |
| Collector | 3309–4516 | 406–1561 |
| task_category | 4604–4611 | 1564–1571 |
| capcut_error_code | 4614–4627 | 1574–1587 |
| decorate_pipeline_stages | 4639–4665 | 1590–1616 |
| capcut_stage_for_tasks | 4668–4719 | 1619–1670 |
| current_date_label | 4722–4724 | 1673–1675 |
| pipeline_dates | 4727–4740 | 1678–1691 |
| authoritative_capcut_task_ids | 4743–4756 | 1694–1707 |
| production_capcut_tasks | 4759–4770 | 1710–1721 |
| upload_task_index | 4773–4781 | 1724–1732 |
| _local_or_cloud_final_is_valid | 4784–4805 | 1735–1756 |
| remote_capcut_summaries | 4808–4845 | 1759–1796 |
| task_box_created_at | 4851–4870 | 1799–1818 |
| task_box_sort_key | 4873–4901 | 1821–1849 |
| task_box_payloads | 4904–5171 | 1852–2119 |
| authoritative_active_task_box | 5174–5231 | 2122–2179 |
| pipeline_for_date | 5253–5311 | 2182–2240 |
| overview_payload | 5314–5424 | 2243–2353 |
| public_task_items | 5427–5429 | 2356–2358 |
| public_task_item | 5432–5443 | 2361–2372 |
| public_metrics_payload | 5446–5452 | 2375–2381 |
| service_health_payload | 5455–5483 | 2384–2412 |
| source_status_payload | 5486–5516 | 2415–2445 |
| _current_stage | 5678–5706 | 2448–2476 |
| current_project_status_payload | 5709–5939 | 2479–2709 |
| dashboard_payload | 5942–6012 | 2712–2782 |
| dashboard_summary_payload | 6015–6083 | 2785–2853 |
| subtitle_verification_inventory | 6615–6660 | 2856–2901 |

## Claude 审查及回滚

重点审查独立内存台账、端口绑定的实例隔离、R2/R4 适配器副作用边界、上限和失败半成品门禁。不得给候选 Store 传生产 DB，不得用真实控制接口做“影子”。本 PR 仅准备隔离实现和回放入口，生产真实全批次、性能和切换资格需另记录。回滚 revert 本 PR/移除独立工具，不回写旧库、不触碰旧收据/命令。无自动启用步骤；不合并、不部署。
