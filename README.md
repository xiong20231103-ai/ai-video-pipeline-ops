# AI视频生产线 OPS Dashboard

设计、审查、迁移与部署说明在私有仓库 ai-video-pipeline-ops-private，不在此处。

独立的本地“监控与安全控制中心”。通过 Tailscale 访问时，可以汇总状态并执行受限的队列确认、撤回、安全继续和上传补传操作：

- TikHub 下载与 AI 去字幕实时状态。
- 批量语音客户端的批次、成功和失败数量。
- AI 素材拼接实时进度及最近一次生成记录。
- 动态任务箱总进度、当前第几项、下一项目及每个项目的最终成片进度。
- CapCut 第五步按正式任务 ID 分组的逐任务状态。
- 百度网盘最终成片的等待校验、上传中、上传完成和上传失败状态。
- CPU、内存、GPU、磁盘、网络和程序在线状态。

五个步骤均显示程序在线状态、当前任务或子阶段、进度、完成/失败/总数、数据来源和最后更新时间。工作台关闭后，第一步会从下载目录恢复当天已处理视频数量，不会因为尚未进入第四步而消失。

“全流程状态”支持按不可变生产日期查看，默认选择最新活动任务箱的投递日期。跨零点不会自动切换到当天；切换任务箱或生产日期时五个步骤会一起切换。

“安全继续”会先由工作台对账，并把第1至第5步的预期数、实际数、阻断原因和结果时间持久显示在页面中；重复点击使用同一个命令 ID，不会重复启动。百度网盘未配置时显示“未配置”；配置后显示真实上传、云端核验和本地清理状态，不会推测或伪造。

## 快速开始

1. 双击 `安装Dashboard.cmd`。
2. 双击 `启动Dashboard.cmd`。
3. 浏览器访问 `http://127.0.0.1:8765`。

需要无人值守时，运行 `安装Dashboard开机启动.cmd`。登录 Windows 后，`dashboard-watchdog.ps1` 会在 Dashboard 异常退出时自动恢复，并将最近启动失败原因显示在页面中。

若 Python 不在常规安装目录，可先设置环境变量 `TIKHUB_OPS_PYTHON` 为可用的 `python.exe`，再运行安装脚本；该本机路径不写入仓库配置。

## 接口

- `GET /api/health`
- `GET /api/overview`
- `GET /api/pipeline`
- `GET /api/tasks`
- `GET /api/events`
- `GET /api/dashboard`：一次返回任务箱、流程、服务健康、第五步、上传、对账及数据源状态。
- `GET /api/controls/continue-current/status`：读取持久化的安全继续对账结果。
- `POST /api/controls/continue-current`：返回幂等命令 ID，并由工作台执行安全对账。
- `POST /api/controls/upload/verify-history`：提交历史百度云文件核验，只查询云端路径和大小，不补传、不删除。
- `GET /api/controls/upload/verify-history/status`：读取历史百度云核验进度和结果。
- `GET /api/controls/production-files`：读取生产文件分类清单、引用关系和保护原因。
- `POST /api/controls/production-files/preview`：预览用户勾选文件及预计释放空间，返回一次性快照令牌。
- `POST /api/controls/production-files/recycle`：再次核验快照后，将仍可清理的文件移入 Windows 回收站。
- `GET /api/controls/production-files/recycle/status`：读取最近一次生产文件清理结果。

任务每2秒扫描一次，机器心跳每60秒保存一次，历史记录保存到 `data/ops.db`。

## 状态来源

- `TikHub_AI_视频工作台/ops_pipeline_status.json`：工作台每2秒原子更新前三步状态。
- 工作台下载目录：作为第一步历史回退来源，默认从 `workbench_settings.json` 自动识别，也可通过 `config.json` 的 `download_root` 指定。
- `tools/BatchVoiceClient-Portable/data/last_batch_handoff.json`：即使只运行语音客户端，也能恢复最近批次。
- `E:/生成视频/日期/项目/generation_records_*.json`：恢复最近拼接结果。
- `handoff/capcut/*.status.json`：第五步真实状态。
- `handoff/upload/upload_status.json`：百度网盘上传任务、进度、失败原因和云端文件 ID。

这些路径都在 `config.json` 中配置，复制到家庭电脑后只需按实际目录修改配置。

浏览器接口仅返回文件名和业务标识，不返回访问令牌、本机绝对路径或敏感配置。单个状态源读取失败时，其余区域保留最后一次成功数据，并单独显示失败来源和数据年龄。

Dashboard 的“管理音频文件”只执行用户手动勾选并二次确认的回收站操作。正在运行、等待恢复、拼接中或 CapCut 处理中任务引用的音频会被锁定；服务端在真正执行前再次核验引用状态。系统不会定时清理音频，也不会因上传完成自动删除音频。音频目录默认从正式任务登记自动识别；如需限制扫描范围，可在本机 `config.json` 中配置 `audio_roots` 数组，该私有路径不得提交到 Git。

Dashboard 的“管理生产文件”用于手动管理第1/2步去字幕视频、第4步拼接视频、第5步临时成片、本地正式成片、任务专属预处理样品及明确测试目录中的文件。打开页面不会删除任何文件；只有用户勾选、预览并二次确认后才会移入 Windows 回收站。默认只勾选云端已经核验且没有活动引用的安全生产文件，测试文件默认不勾选。

上传服务卡片的“核验历史云端文件”用于为旧上传记录补做实时云端查询。它只核对百度云文件 ID、路径和大小，不重新上传、不删除文件、不改变项目完成状态，也不会把旧任务升级为自动清理策略。核验通过后，相应旧文件才具备进入“管理生产文件”手动清理候选的云端证据。

共享去字幕视频只有在全部引用任务完成上传并通过云端核验后才可清理；等待、运行、失败或安全恢复中的任务，以及身份不完整、云端大小不一致、百度同步目录中的文件都会被锁定。公共样品、公共 AI 素材、Logo、配音、配置、日志和草稿不进入该清单。服务端执行前会再次核验快照、引用和文件状态，清理结果不会改变任务或云端记录。

生产文件管理的可选本机配置：

- `prepared_sample_roots`：任务专属 `prepared-samples` 目录列表。
- `capcut_test_roots`：允许手动选择的 CapCut 测试文件目录列表；只扫描明确列出的目录。
- `isolated_runtime_markers`：用于判断隔离工作台或隔离 CapCut 是否正在运行的路径标记列表。
- `baidu_sync_roots`：百度同步盘目录列表；其中任何文件永久禁止由此功能清理。

以上路径均属于本机私有配置，不应提交到 Git。

## 素材交接控制（PR4，默认关闭）

新增云端交接包和单值班端控制的说明、API、包格式及离线恢复世代流程见 [docs/material-handoff-pr4.md](docs/material-handoff-pr4.md)。配置片段在 `cloud/material-handoff.example.json`，不能替换 Dashboard 的根 `config.json`。本功能需要后续本机 PR5/演练 PR6 才能用于双端生产，合并不代表部署批准。
