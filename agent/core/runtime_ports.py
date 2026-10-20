"""Explicit native ports and constant allocation. No config discovery or startup."""
from __future__ import annotations
import csv,hashlib,ipaddress,json,os,re,socket,sqlite3,subprocess,threading,time,urllib.error,urllib.parse,urllib.request,uuid
from contextlib import contextmanager,asynccontextmanager
from contextvars import ContextVar
from functools import wraps
from datetime import datetime,timedelta,timezone
from pathlib import Path
from typing import Any
import psutil,pending_delete
from cleanup_tickets import CleanupTickets
from fastapi import HTTPException,Query,Request,Response
from fastapi.responses import JSONResponse,FileResponse

def native_ports(base_dir,state_dir,config):
    base_dir=Path(base_dir);state_dir=Path(state_dir)
    BASE_DIR=base_dir
    DATA_DIR=state_dir
    DB_PATH=state_dir/'projection.db'
    CONFIG=dict(config)
    _CLEANUP_SOURCE_STRICT = ContextVar('cleanup_source_strict', default=False)
    STATIC_DIR = BASE_DIR / 'static'
    CONFIG_PATH = BASE_DIR / 'config.json'
    CONTINUE_COMMAND_NAME = 'continue_current_project.json'
    CONTROL_COMMAND_DIR = DATA_DIR / 'control-commands'
    CONTROL_COMMAND_TTL_SECONDS = 300
    CONTROL_COMMAND_CLAIM_TIMEOUT_SECONDS = 90
    TASK_BOX_RECEIPT_DIR = DATA_DIR / 'task-box-completion-receipts'
    TASK_BOX_RECONCILIATION_DIR = DATA_DIR / 'task-box-reconciliation'
    LEGACY_INVALID_JSON_BACKSLASH = re.compile('(?<!\\\\)\\\\(?!["\\\\/bfnrtu])')
    CONTROL_ACTIONS_PATH = DATA_DIR / 'control_actions.json'
    TEST_RESET_STATE_PATH = DATA_DIR / 'test_reset_state.json'
    CAPCUT_DRAFT_CLEANUP_STATUS_PATH = DATA_DIR / 'capcut_draft_cleanup_status.json'
    CAPCUT_DRAFT_CLEANUP_BACKUP_DIR = DATA_DIR / 'capcut-draft-cleanup-backups'
    CAPCUT_DRAFT_CLEANUP_CONFIRM = 'RECYCLE_SELECTED_CAPCUT_DRAFTS'
    CAPCUT_DRAFT_LOCK = threading.RLock()
    FORMAL_PROJECT_NAMES = ('云手机', '实体机', '黄颢', '真黄颢', 'SPC地板', 'SPC墙板')
    AUDIO_CLEANUP_STATUS_PATH = DATA_DIR / 'audio_cleanup_status.json'
    AUDIO_CLEANUP_BACKUP_DIR = DATA_DIR / 'audio-cleanup-records'
    AUDIO_CLEANUP_CONFIRM = 'RECYCLE_SELECTED_AUDIO_FILES'
    AUDIO_CLEANUP_LOCK = threading.RLock()
    AUDIO_EXTENSIONS = {'.aac', '.flac', '.m4a', '.mp3', '.ogg', '.wav'}
    PRODUCTION_FILE_CLEANUP_STATUS_PATH = DATA_DIR / 'production_file_cleanup_status.json'
    PRODUCTION_FILE_CLEANUP_BACKUP_DIR = DATA_DIR / 'production-file-cleanup-records'
    PRODUCTION_FILE_CLEANUP_INDEX_PATH = DATA_DIR / 'production_file_cleanup_index.json'
    PRODUCTION_FILE_CLEANUP_CONFIRM = 'RECYCLE_SELECTED_PRODUCTION_FILES'
    PRODUCTION_FILE_CLEANUP_LOCK = threading.RLock()
    PRODUCTION_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v'}
    SAFETY_CACHE_TTL_SECONDS = 20.0
    SAFETY_CACHE_LOCK = threading.Lock()
    SAFETY_CACHE: dict[str, Any] = {'payload': None, 'expiresAt': 0.0}
    TASK_REQUIRED_COLUMNS = ('batch_id', 'date_label', 'project', 'material', 'language', 'number', 'sequence', 'video_path', 'audio_path', 'output_path', 'state', 'state_text', 'error', 'source_file', 'source_timestamp', 'remote_pipeline_task_id', 'expected_task_count')
    TASK_OPTIONAL_COLUMNS = ('phase', 'phase_text', 'manifest_id', 'attempt_id', 'heartbeat_at', 'draft_cleanup_status', 'draft_cleanup_warning', 'draft_cleanup_updated_at')
    CONTROL_COMMAND_LOCK = threading.Lock()
    CONTINUE_EXPECTED_FIELDS = ('batchId', 'taskId', 'productionDate', 'manifestId', 'attemptId', 'runGroupId', 'batchKind')
    CONTINUE_EXPECTED_LABELS = {'batchId': '任务箱', 'taskId': '项目', 'productionDate': '日期', 'manifestId': '清单', 'attemptId': '尝试', 'runGroupId': '运行组', 'batchKind': '任务类型'}
    LOCAL_PATH_PATTERN = re.compile('(?i)(?<![A-Za-z0-9])[A-Z]:[\\\\/][^\\"\\r\\n]*')
    SENSITIVE_KEY_PARTS = ('accesstoken', 'access_token', 'password', 'secret', 'authorization')
    CAPCUT_STATE_TEXT = {'Waiting': '等待剪辑', 'Launching': '启动剪映', 'CreatingProject': '创建项目', 'Importing': '导入视频', 'PlacingOnTimeline': '加入时间线', 'MutingOriginal': '静音原轨', 'ImportingAudio': '导入音频', 'PlacingAudioOnTimeline': '加入音频轨', 'ImportingSample': '导入结尾样品', 'PlacingSample': '样品接到末尾', 'AdjustingSampleSpeed': '调整样品速度', 'RecognizingCaptions': '识别字幕', 'ApplyingSubtitleStyle': '应用字幕样式', 'TrimmingFirstCaption': '检查首帧字幕', 'ReplacingMainVideo': '替换主视频', 'Exporting': '2K导出', 'PostProcessing': 'FFmpeg替换第0帧', 'CleaningDraft': '清理草稿', 'RecyclingSource': '等待云端核验与清理', 'Completed': '剪辑完成', 'Failed': '剪辑失败'}
    WAITING_STATES = {'Waiting', 'waiting_capcut', 'waiting_client', 'stopped'}
    RECOVERABLE_DRAFT_REOPEN_ERRORS = {'draft_card_location_failed', 'draft_editor_binding_failed', 'draft_cover_location_failed', 'draft_checkpoint_current_lease_directory_missing', 'draft_checkpoint_current_lease_files_missing'}
    COMPLETED_STATES = {'Completed', 'completed'}
    FAILED_STATES = {'Failed', 'failed', 'validation_failed', 'manual_review'}
    LEGACY_DRAFT_CLEANUP_MARKERS = ('草稿待清理', '草稿索引更新失败', '返回首页并删除本条唯一新增草稿失败')
    PENDING_DELETE_EMPTY_CONFIRM = 'EMPTY_PENDING_DELETE_NOW'
    PENDING_DELETE_PURGE_INTERVAL_SECONDS = 3600.0
    PRODUCTION_FILE_CATEGORY_LABELS = {'subtitle_output': '第1+2步去字幕视频', 'stitch_output': '第4步拼接视频', 'capcut_temporary': '第5步 CapCut 临时成片', 'local_final': '本地正式成片', 'prepared_sample': '任务专属预处理样品', 'capcut_test': 'CapCut 测试及首帧文件'}
    OPEN_RECOVERY_COMMAND_STATES = {'claimed', 'dispatched', 'accepted', 'executing', 'running', 'reconciling', 'reconciliation_required'}
    HEALTH_LOG_KEYWORDS = ('失败', '错误', '异常', 'Traceback', '拒绝访问')
    HEALTH_LOG_IGNORED = ('Ignored cross-date', '已完成第 5 步')
    HEALTH_LOG_ZERO_FAILURES = re.compile('失败\\s*0(?!\\d)')
    HEALTH_LOG_LINE = re.compile('^(\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}) \\[pid \\d+\\] (.*)$')
    _HEALTH_CACHE: dict[str, Any] = {'at': 0.0, 'payload': None}
    STAGE_META = {'download': ('1', '下载与AI去字幕', '工作台', 'workbench'), 'voice': ('2', '批量语音生成', '语音客户端', 'voice'), 'stitch': ('3', 'AI素材拼接', '工作台', 'workbench'), 'capcut': ('4', 'CapCut自动剪辑', 'CapCut客户端', 'capcut'), 'upload': ('5', '最终成片上传', '上传服务', 'upload')}
    TASK_BOX_STALE_SECONDS = 14 * 24 * 3600
    CLOUD_CLEANUP_TICKETS = CleanupTickets()
    return {**globals(),**locals()}

def normalize_config(base_dir,overrides):
    BASE_DIR=Path(base_dir)
    defaults={'machine_name': socket.gethostname(), 'listen_host': '127.0.0.1', 'listen_port': 8765, 'workbench_dir': '../TikHub_AI_视频工作台', 'workbench_ops_status': '../TikHub_AI_视频工作台/ops_pipeline_status.json', 'download_state_file': '../TikHub_AI_视频工作台/handoff/download/download_batch_state.json', 'download_project_status_file': '../TikHub_AI_视频工作台/handoff/download/project_status.json', 'receiver_status_url': 'http://127.0.0.1:8766/api/pipeline/snapshot', 'control_plane_url': 'http://127.0.0.1:18790', 'download_root': '', 'voice_handoff_file': '../TikHub_AI_视频工作台/tools/BatchVoiceClient-Portable/data/last_batch_handoff.json', 'audio_roots': [], 'generation_output_root': 'E:/生成视频', 'capcut_handoff_dir': '../TikHub_AI_视频工作台/handoff/capcut', 'fourth_step_handoff_dir': '../TikHub_AI_视频工作台/交接记录', 'final_output_root': 'E:/', 'capcut_draft_root': '', 'upload_status_file': '../TikHub_AI_视频工作台/handoff/upload/upload_status.json', 'prepared_sample_roots': [str((BASE_DIR.parent / 'capcut-auto-caption-client' / 'bin' / 'data' / 'prepared-samples').resolve())], 'capcut_test_roots': [str((BASE_DIR.parent / 'capcut-auto-caption-client' / 'bin' / 'data' / 'local-sample-e2e').resolve()), str((BASE_DIR.parent / 'capcut-auto-caption-client' / 'bin' / 'data' / 'first-caption-e2e-output').resolve())], 'isolated_runtime_markers': ['AI视频工作台-内测版-20260724', 'isolated-subtitle-style-lab.profile'], 'baidu_sync_roots': [], 'scan_interval_seconds': 2, 'pipeline_live_after_seconds': 15, 'heartbeat_interval_seconds': 60, 'offline_after_seconds': 180, 'simulation_enabled': True, 'test_history_batch_ids': [], 'test_history_remote_task_ids': []}
    defaults.update(overrides)
    return defaults
