# AI视频生产线 OPS Dashboard

独立、只读的本地监控页面。现在可以汇总：

- TikHub 下载与 AI 去字幕实时状态。
- 批量语音客户端的批次、成功和失败数量。
- AI 素材拼接实时进度及最近一次生成记录。
- CapCut 第五步逐任务状态。
- CPU、内存、GPU、磁盘、网络和程序在线状态。

Dashboard 不控制任何生产程序。网盘上传尚未接入时会明确显示“未配置”。

## 快速开始

1. 双击 `安装Dashboard.cmd`。
2. 双击 `启动Dashboard.cmd`。
3. 浏览器访问 `http://127.0.0.1:8765`。

## 只读接口

- `GET /api/health`
- `GET /api/overview`
- `GET /api/tasks`
- `GET /api/events`

任务每2秒扫描一次，机器心跳每60秒保存一次，历史记录保存到 `data/ops.db`。

## 状态来源

- `TikHub_AI_视频工作台/ops_pipeline_status.json`：工作台每2秒原子更新前三步状态。
- `tools/BatchVoiceClient-Portable/data/last_batch_handoff.json`：即使只运行语音客户端，也能恢复最近批次。
- `E:/生成视频/日期/项目/generation_records_*.json`：恢复最近拼接结果。
- `handoff/capcut/*.status.json`：第五步真实状态。

这些路径都在 `config.json` 中配置，复制到家庭电脑后只需按实际目录修改配置。
