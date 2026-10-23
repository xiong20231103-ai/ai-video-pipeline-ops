# 公司采集、云端保存、家里确认 — 开发交付记录

## 当前状态

这是未部署的基础实现，不能称为完整的两地接续功能。
涵盖独立链接库、JPEG校验、序号幂等、云端决定保护、截图保留/容量、只读页面和在线备份。
云端决定API单独关闭，必须先完成公司回写与家里递交的端到端验收才能打开。
链接记录不会自动删除；审核状态与投递状态独立。confirmed + waiting 表示已收录待递交。

## 契约

POST /api/links/ingest：专用环境变量 LINK_EVIDENCE_TOKEN 的 Bearer 鉴权；
每分钟60次，流式限制2MiB。source/platform/video_id/judge_round 构成幂等键；
seq 为来源实例持久化递增序号。url 是原始链接，review/delivery 是独立状态，
decidedAt 为秒级时间戳或 null，image 为base64 JPEG（最长边1600，最大600KiB）。
其他展示元数据（date/category/batch_id/replace_id/home_task_id/conditions/displayable）保存在payload。
旧事件不覆盖新状态，但允许旧截图事件重试修复图片。云端决定不受公司旧事件覆盖。

GET /api/links、/api/links/shots/{sha}、/links 使用现有登录会话。
POST /api/links/{id}/decision 使用登录+CSRF+revision+requestId；默认关闭。
收录不会自动递交。决定时间在云端事务内记录，动作保存操作者与幂等请求ID。

## 隔离验证 / 将来部署

1. 在隔离目录安装 cloud/requirements-test.txt，运行 tests/test_link_evidence.py。
2. 生产部署前保存当前代码版本及配置，使用SQLite在线备份保存 links.db；不得覆盖业务库。
3. 仅显式设置 link_evidence_enabled=true 时挂载功能，link_evidence_dir 指向指定目录。
   LINK_EVIDENCE_TOKEN 由用户放入服务私密环境文件，禁止加入仓库或命令参数。
4. 保持127.0.0.1:8000与现有Tailscale HTTPS代理，不增加监听端口。
5. 每日03:30运行 python -m cloud.link_maintenance；在线备份保留7份，截图不备份。
   该命令尚未安装定时器。备份实际占用必须在部署验收时测量。
6. 公司上传进程计划每天北京时间18:00处理截止该时刻的事件；开机运行后自动追补。
   两边配置都完成、全部端到端测试通过且用户明确说“部署”之后才执行上述生产步骤。

## 回滚

关闭 link_evidence_enabled 和 link_decisions_enabled，停用新增维护/上传任务，恢复上一个代码版本。
保留 link-evidence 与本地outbox，禁止删除未上传事件或恢复旧业务数据库覆盖真实决定。
本次未修改现有主数据库结构，没有状态数据库迁移。

## 尚待完成（禁止据此启用生产）

- 公司采集/展示/决定/递交状态的事件钩子，可靠决定时间、全部正式链接与候选历史补传。
- 云端完整分页及批次冻结、按现有判图/字幕/目标/补链规则评估可展示数量。
- 家里OpenClaw原生截图交付、每日素材递交适配、补链递交适配与接收端幂等回执。
- 云端到公司决定回写与冲突隔离；公司离线期间两地并发的状态所有权。
- 维护计时器、开机启动上传器安装脚本、公司PR、浏览器刷新与跨地全链路测试。

不要用HTTP 200或空数组证明家里已接收：必须保存对应任务与明确逐条回执；
超时结果未知时先查询，禁止直接重新提交。
