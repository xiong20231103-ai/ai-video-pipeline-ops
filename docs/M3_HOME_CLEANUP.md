# M3 家里核心清理合同（待 Claude 审查部署）

本 PR 只实现既有草稿、音频、生产文件三类与待删区的云端预览票据及执行保护。不部署、不合并、不触发生产清理。H2 五类目录扩展尚未完成，也不开放；目录身份、日期全上传核验和租约权威证据合同待用户/Claude 确认。

## HTTP 合同

- GET `/api/controls/cloud-cleanup/capabilities`：协议 1、保留 3 天、永久草稿保护。实际配置不是 3 天时 503。
- POST `/api/controls/cloud-cleanup/preview`：`kind` 为 drafts/audio/production/pending，`ids` 只允许服务端 ID；`includeUnknown` 为布尔。返回原预览及 kind/ids/snapshotToken/ticket/expiresAt/confirm/includeUnknown。pending 只允许空 ID 列表，预览容量及永久清空警告。
- POST `/api/controls/cloud-cleanup/execute`：原样发送上述七个票据字段。ticket 使用服务端随机能力值，绑定选择、快照、确认字符串及额外确认；有效期至多 120 秒；墙钟回拨或单调时间到期均拒绝。一次性消费，重启失效，不保存原始票据到日志。
- pending 确认字符串为 `EMPTY_PENDING_DELETE_NOW`；三类仍为现有三个 `RECYCLE_SELECTED_*` 精确字符串。人工/未知草稿确认必须在预览时确定，不能执行时改票据。
- UI 的测试文件额外确认仍由云端呈现；既有 home 后端没有单独 testConfirmed 字段，不把前端确认虚称为新的服务端授权。

三类原锁内重新盘点，委托原 execute，不复制一套资格判断。音频任一受保护项整体 409；生产文件逐项 blocked，合格项可继续；草稿部分失败时索引只剔除成功项。票据不能代替执行前资格复核。线程锁只保证同一 Dashboard 进程，不宣称跨两个执行器互斥。

## 安全增强与兼容差异

1. H2 `pending_delete.move` 同盘移动、逐文件身份核验、保留三天、可恢复，无永久删除回退。R5-06 原 Shell 回收站条目按用户新 H2 合同替代；不再调用 SHFileOperationW。不新增跨平台生产支持声明，临时测试夹具只验证算法。
2. 永久排除 `E:\JianyingPro Drafts` 及其后代，大小写/分隔符标准化，同时检查原路径及解析后路径。草稿、音频、生产库存将受保护位置标不可选；move 再次拒绝。链接及祖先重解析点拒绝。
3. 清理路径使用 ContextVar 开启严格来源读取：STORE 查询失败、配音交接/上传/项目 JSON 缺失、损坏、类型无效均 503。普通页面查询仍保留原容错行为。源故障时此前可能出现的可清理项目现在将被拒绝，这是有意的失败关闭变化。
4. 草稿快照增加后代文件字节流哈希，能检测同大小内容变更；只在按需草稿盘点发生。相比原来仅根目录 mtime/索引字节的 token 不兼容，升级后旧预览需重新生成。
5. 待删区快照覆盖整个已盘点目录，坏 JSON、不可读目录、重解析点、目标越界、未登记额外内容、文件身份/大小变化、受保护原来源均拒绝。自动到期清理与立即清空复用同一逐 slot 校验；非法 slot 保留供人工核查。显式清空持 pending_delete.LOCK 重盘点后才 purge。

## R5 实际测试映射

测试位于 tests/test_cloud_cleanup_home.py、test_cleanup_protections.py、原 test_ops.py、test_pending_delete.py。下表只描述实际夹具覆盖，不代表真实生产清理已验收。

| 规则 | 测试/实际证据 |
|---|---|
| R5-01～03 | test_types_paths_limits_and_confirmation_cannot_bypass；test_ticket_exact_fields_single_use_and_restart；原 selected 函数类型/数量/不存在对象分支保持 |
| R5-04～05 | test_execute_delegates_existing_category_semantics；test_expired_ticket_rejected_before_delegation；原 execute 内锁和 fresh inventory 不变 |
| R5-06（新 H2） | pending tests: file_move_is_recorded_and_verified / directory_move_verifies_every_file / fake_success_is_detected / identity_mismatch_is_detected / partial_directory_move_is_detected / cross_volume_is_refused / rename_error_never_deletes / restore_returns_item |
| D01 | 原 inventory 只从显式根/本用户默认根；test_forbidden_draft_root_is_never_eligible |
| D02 | test_draft_missing_duplicate_and_recent_identity_are_protected；原 test_capcut_draft_preview_blocks_while_capcut_is_running |
| D03 | 原 test_capcut_draft_inventory_classifies_and_hides_paths；test_draft_unknown_requires_extra_confirmation |
| D04 | test_draft_snapshot_detects_same_size_descendant_edit；原 test_capcut_draft_cleanup_rejects_stale_snapshot；test_draft_timestamp_seconds_microseconds_and_fallback |
| D05 | test_draft_backup_failure_never_moves_or_mutates_index |
| D06 | 原 test_capcut_draft_cleanup_removes_exact_index_entry_and_is_idempotent |
| D07～08 | test_draft_partial_failure_retains_failed_index_and_rechecks_process |
| A01～02 | test_audio_reference_sources_deduplication_and_handoff_terminal_states；test_audio_wait_failed_recovery_references_and_producer_recent_protected |
| A03 | test_audio_missing_roots_and_manifest_failure_fail_closed；test_missing_store_source_fails_closed_audio_and_production；test_cleanup_handoff_missing_or_malformed_never_authorizes_orphans |
| A04～05 | test_audio_filters_extensions_and_snapshot_tracks_active_reference_change；原 test_audio_inventory_protects_active_task_and_hides_absolute_path |
| A06 | test_audio_mixed_selection_is_all_or_reject_and_no_move；原 test_audio_cleanup_direct_call_cannot_bypass_active_reference |
| A07 | test_audio_missing_roots_and_manifest_failure_fail_closed；原 test_audio_cleanup_rechecks_snapshot_and_recycles_exact_file |
| A08 | 原 execute 部分失败分支保留；原成功移动 test_audio_cleanup_rechecks_snapshot_and_recycles_exact_file。见下文未穷举边界 |
| P01 | test_canonical_identity_and_replenishment_aliases；原 canonical/remote/inbox 解析保持 |
| P02～03 | test_cloud_verification_every_required_field_negative；原 test_production_file_inventory_protects_active_or_unverified_tasks |
| P04～09 | test_production_registration_protections_and_path_deduplication（缺项目/未完成/无上传/共享未核验/样品未登记/活动测试/同路径/百度）；原 test_production_file_inventory_uses_exact_registered_paths_and_safe_defaults |
| P10 | test_production_manifest_failure_prevents_every_move；原 test_production_file_cleanup_recycles_exact_file_and_rejects_stale_snapshot |
| P11～13 | test_production_partial_protected_and_failed_index_preserves_old；原生产文件精确成功移动测试 |
| 票据/清空新保护 | test_ticket_clock_rollback_monotonic_expiry_and_mutable_input；test_ticket_capacity_is_bounded；test_pending_snapshot_change_blocks_empty_and_never_calls_purge；test_pending_invalid_json_refuses_preview；test_pending_unregistered_replaced_payload_and_protected_receipt_never_purge；test_pending_permission_error_never_becomes_empty_inventory |

尚不把以下边界声称为逐一穷举：默认草稿根在不同 Windows 用户下的实机行为；Windows 所有 reparse 类型的真实文件系统变体；部分失败后的磁盘再次断线；生产临时/成片所有历史字段组合。代码分支保留，后续 Claude 审查/部署仍需复核。隔离测试不代表已执行真实删除。

## H2 五类扩展缺失证据

当前 `_production_file_inventory` 仅从下载 checkpoint 的 completed.outputPath 及上传登记精确路径建文件对象；`_canonical_task_aliases` 只处理 imported inbox 身份；`_production_active_projects` 仅项目状态与 STORE 未完成记录。没有 quarantine 目录登记协议，也没有 task-draft-roots 当前租约权威读取合同。`_cloud_verification` 证明的是单个上传项，不能将某个目录名或日期相似性升级为整批完整/当日应上传总数的证明。不得据此授权五类目录删除。

## 部署与回滚（仅交接，不执行）

Claude 在流水线空闲时审查 PR。先备份 home 引擎源码/环境及现有待删区记录，再部署本 PR；仅在能力接口返回协议 1 后才允许云端入口。云端代理与页面属于另一 PR，必须同时审查能力门禁与未知结果不重发。

回滚先暂停云端领取，清点 sent/unknown，不把未知命令重排；待无在途后由 Claude 退回部署前代码并重启 Dashboard。新旧预览均废弃，必须重盘点。待删区内容和 receipts 保留，不能因回滚代码删除或重放它们。此 PR 不自动执行任何部署/回滚，不触发 SPC 安全继续。
