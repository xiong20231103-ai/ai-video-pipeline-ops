# AI视频生产线 OPS Dashboard

独立、只读的本地监控页面。现在可以汇总：

- TikHub 下载与 AI 去字幕实时状态。
- 批量语音客户端的批次、成功和失败数量。
- AI 素材拼接实时进度及最近一次生成记录。
- CapCut 第五步逐任务状态。
- CPU、内存、GPU、磁盘、网络和程序在线状态。

五个步骤均显示程序在线状态、当前任务或子阶段、进度、完成/失败/总数、数据来源和最后更新时间。工作台关闭后，第一步会从下载目录恢复当天已处理视频数量，不会因为尚未进入第四步而消失。

“全流程状态”支持按日期查看，默认选择今天。日期来源会自动合并下载文件、语音批次、拼接生成记录和CapCut任务；切换日期时五个步骤会一起切换。

Dashboard 不控制任何生产程序。网盘上传尚未接入时会明确显示“未配置”。

## 快速开始

1. 双击 `安装Dashboard.cmd`。
2. 双击 `启动Dashboard.cmd`。
3. 浏览器访问 `http://127.0.0.1:8765`。

## 只读接口

- `GET /api/health`
- `GET /api/overview`
- `GET /api/pipeline`
- `GET /api/tasks`
- `GET /api/events`

任务每2秒扫描一次，机器心跳每60秒保存一次，历史记录保存到 `data/ops.db`。

## 状态来源

- `TikHub_AI_视频工作台/ops_pipeline_status.json`：工作台每2秒原子更新前三步状态。
- 工作台下载目录：作为第一步历史回退来源，默认从 `workbench_settings.json` 自动识别，也可通过 `config.json` 的 `download_root` 指定。
- `tools/BatchVoiceClient-Portable/data/last_batch_handoff.json`：即使只运行语音客户端，也能恢复最近批次。
- `E:/生成视频/日期/项目/generation_records_*.json`：恢复最近拼接结果。
- `handoff/capcut/*.status.json`：第五步真实状态。

这些路径都在 `config.json` 中配置，复制到家庭电脑后只需按实际目录修改配置。
