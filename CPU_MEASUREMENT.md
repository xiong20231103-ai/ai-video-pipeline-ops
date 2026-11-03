# 常驻 CPU：五分钟隔离测量（2026-11-03）

## 范围与结论

**没有部署，没有更改生产状态，也没有停启服务。下面是隔离读侧回放进程，不是完整生产工作台/HTTP Dashboard 的线上 CPU。** 无法据此宣称用户实测的 76%/95% 已降到下表。cProfile 本身有开销，Windows I/O 和其他作业会造成抖动。

固定数据：4318 个 JSON、83,629,259 字节，快照清单 SHA-256 为 `25b744b9c0ba612ac6b902a21ecd201adfb23f427d6005035bf6c19c6383aa97`。两边从同一不可变快照另复制测量目录。原始数据/路径/凭证不进仓库。第一版漏了真实 date ledger 的 smoke 结果被排除；正式结论仅使用 v2 五分钟记录。

| 读侧回放 | 优化前单核CPU | 优化后单核CPU | 前平均轮询 | 后平均轮询 |
|---|---:|---:|---:|---:|
| 工作台 | 33.80% | 11.31% | 1882.99 ms | 609.16 ms |
| Dashboard | 74.86% | 31.83% | 18820.44 ms | 1880.90 ms |

CPU = process_time / wall_time ×100，100%代表一个逻辑核心，不是整机百分比。包括睡眠预算。工作台周期5秒；Dashboard周期2秒，基线过载只跑16轮，优化版98轮。表含冷启动/SQLite首次投影；优化后去掉首轮的均值分别568.33ms、801.89ms。前后累计时间包含子调用，**不能相加**；ms/次为累计时间/调用次数，并非独占时间。Top10排除回放包装器和time.sleep，但保留原生/标准库热点。

工作台执行真实恢复状态读取、pipeline_snapshot/project_status读取和CapCut阶段同步；持久化 setter 仅检查拷贝注册表后返回False，日志/UI/排队不执行。因此没有证明真实写入成本下降。Dashboard执行真实元数据、状态、工作台和下载状态采集，使用独立空数据库；没有HTTP流量、系统指标、视频/草稿媒体字节扫描。保留失败结果/质检的原检查路径，未运行生成、GPU或收费API。**本实验不能单独验收整进程常驻CPU或线上UI响应延迟。**

实际热点：工作台反复解码和历史终态对账；Dashboard重复SQLite source_result/upsert、路径resolve和JSON。优化后仍有状态遍历、缓存副本和首次SQLite投影成本，不承诺CPU归零。

## 工作台：优化前

测量 300.001 秒，60 轮；单核 CPU 33.80%；平均轮询 1882.99 ms。

| 函数 | 调用次数 | 次/秒 | 累计秒 | ms/次 |
|---|---:|---:|---:|---:|
| `workbench.py:_sync_remote_pipeline_from_capcut` | 60 | 0.200 | 106.338 | 1772.304 |
| `task_inbox.py:load_project_download_statuses` | 19159 | 63.863 | 73.634 | 3.843 |
| `task_inbox.py:_load_project_download_statuses_unlocked` | 19159 | 63.863 | 73.611 | 3.842 |
| `__init__.py:loads` | 42738 | 142.460 | 58.112 | 1.360 |
| `decoder.py:decode` | 42738 | 142.460 | 57.957 | 1.356 |
| `decoder.py:raw_decode` | 42738 | 142.460 | 57.556 | 1.347 |
| `pathlib.py:read_text` | 43159 | 143.863 | 40.041 | 0.928 |
| `~:<method 'read' of '_io.TextIOWrapper' objects>` | 42738 | 142.460 | 26.012 | 0.609 |
| `pathlib.py:open` | 43219 | 144.063 | 13.053 | 0.302 |
| `~:<built-in method _io.open>` | 43219 | 144.063 | 13.005 | 0.301 |

## 工作台：优化后

测量 300.000 秒，60 轮；单核 CPU 11.31%；平均轮询 609.16 ms。

| 函数 | 调用次数 | 次/秒 | 累计秒 | ms/次 |
|---|---:|---:|---:|---:|
| `workbench.py:_sync_remote_pipeline_from_capcut` | 60 | 0.200 | 34.957 | 582.612 |
| `json_read_cache.py:read` | 38807 | 129.357 | 26.437 | 0.681 |
| `task_inbox.py:load_project_download_statuses` | 17666 | 58.887 | 17.796 | 1.007 |
| `task_inbox.py:_load_project_download_statuses_unlocked` | 17666 | 58.887 | 17.781 | 1.007 |
| `~:<built-in method _pickle.loads>` | 38080 | 126.933 | 14.800 | 0.389 |
| `pathlib.py:stat` | 76719 | 255.730 | 6.897 | 0.090 |
| `~:<built-in method nt.stat>` | 76725 | 255.750 | 6.859 | 0.089 |
| `task_inbox.py:load_task_record` | 18079 | 60.263 | 6.393 | 0.354 |
| `json_read_cache.py:file_signature` | 42421 | 141.403 | 4.787 | 0.113 |
| `capcut_handoff.py:load_date` | 2762 | 9.207 | 2.717 | 0.984 |

## Dashboard：优化前

测量 301.127 秒，16 轮；单核 CPU 74.86%；平均轮询 18820.44 ms。

| 函数 | 调用次数 | 次/秒 | 累计秒 | ms/次 |
|---|---:|---:|---:|---:|
| `app.py:scan_statuses` | 16 | 0.053 | 200.434 | 12527.120 |
| `~:<built-in method builtins.next>` | 169568 | 563.111 | 119.300 | 0.704 |
| `app.py:connection` | 169568 | 563.111 | 119.090 | 0.702 |
| `app.py:upsert_task` | 49104 | 163.067 | 102.212 | 2.082 |
| `app.py:_json` | 35680 | 118.488 | 93.575 | 2.623 |
| `pathlib.py:resolve` | 474400 | 1575.413 | 88.119 | 0.186 |
| `contextlib.py:__exit__` | 84784 | 281.555 | 85.478 | 1.008 |
| `app.py:scan_metadata` | 16 | 0.053 | 79.284 | 4955.231 |
| `<frozen ntpath>:realpath` | 474400 | 1575.413 | 69.490 | 0.146 |
| `app.py:source_result` | 35680 | 118.488 | 67.041 | 1.879 |

## Dashboard：优化后

测量 300.000 秒，98 轮；单核 CPU 31.83%；平均轮询 1880.90 ms。

| 函数 | 调用次数 | 次/秒 | 累计秒 | ms/次 |
|---|---:|---:|---:|---:|
| `app.py:scan_statuses` | 98 | 0.327 | 139.460 | 1423.057 |
| `~:<built-in method builtins.next>` | 10596 | 35.320 | 87.047 | 8.215 |
| `app.py:connection` | 10596 | 35.320 | 87.008 | 8.211 |
| `contextlib.py:__exit__` | 5298 | 17.660 | 81.394 | 15.363 |
| `app.py:_json` | 142520 | 475.066 | 69.161 | 0.485 |
| `app.py:_publish_task_projection` | 6270 | 20.900 | 52.095 | 8.309 |
| `app.py:upsert_task` | 3069 | 10.230 | 52.024 | 16.952 |
| `~:<method 'commit' of 'sqlite3.Connection' objects>` | 5298 | 17.660 | 48.058 | 9.071 |
| `app.py:source_result` | 2229 | 7.430 | 39.791 | 17.851 |
| `~:<method 'close' of 'sqlite3.Connection' objects>` | 5298 | 17.660 | 33.231 | 6.272 |

## 可复现入口与原始证据（仅本机）

外部 opt-in 驱动：`E:\Backup\Documents\New project 3\cpu_profile_lab.py`。它拒绝已有label以免覆盖测量；新label需唯一。只允许 wt-cpu-* worktree，guard拒绝生产写入、网络、进程、媒体字节读取。快照/临时SQLite仅写独立lab。

```powershell
$env:TEMP = 'E:\Backup\Documents\New project 3\fish-review-temp'
$env:TMP = $env:TEMP
& 'E:\Backup\Documents\ai-video-workbench-suite\workbench\.venv\Scripts\python.exe' 'E:\Backup\Documents\New project 3\cpu_profile_lab.py' workbench --root 'E:\Backup\Documents\New project 3\wt-cpu-workbench' --label wb-review-new --seconds 300
& 'C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe' 'E:\Backup\Documents\New project 3\cpu_profile_lab.py' dashboard --root 'E:\Backup\Documents\New project 3\wt-cpu-dashboard' --label dash-review-new --seconds 300
```

基线把root换为相应 `*-baseline`；相同解释器和快照。最终四组记录在 `E:\Backup\Documents\New project 3\cpu-lab-20261103\`：

- `wb-before-v2-5min.json`、`wb-before-v2-5min.pstats`
- `wb-release-final-5min.json`、`wb-release-final-5min.pstats`
- `dash-before-v2-5min.json`、`dash-before-v2-5min.pstats`
- `dash-race-safe-final-5min.json`、`dash-race-safe-final-5min.pstats`

每份final JSON含源文件逐字节SHA-256；已与最终代码逐项核对一致。文档后续提交不改变测量代码。完整5分钟pstats可用Python pstats读取；不提交生产拷贝。
