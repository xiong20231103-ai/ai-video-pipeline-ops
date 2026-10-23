# 接收端核验：d36da0b

核对来源为用户指定私有仓库 ai-video-workbench-suite 的 main，隔离克隆 HEAD 为 d36da0b。
没有连接家里接收服务，没有修改接收端源码或生产文件。

## 实际契约

- 每日素材复用本机递交器生成的正式/DENOR完整任务箱，经已有云端串行命令队列发送到
  POST /api/batches。云端不重新实现语言扩展、音频选择、正式总数或DENOR业务。
- batchId、taskId、runGroupId、clientSubmissionId 与完整任务箱必须冻结。
  接收端 task_receiver.py 的 receive_batch 根据 clientSubmissionId 读取落盘回执，
  比较完整 payloadHash；内容不同返回409，相同返回原回执并标记duplicate。
- 不把HTTP200、命令已获发送许可或空数组当作业务接收成功。
  每日批次核对 ok、clientSubmissionId、batchId、payloadHash 和有序taskIds。
- 补链走父任务 /api/tasks/replenish/{parent}，现有Dashboard转发路径不变。
  接收端按父任务+规范化链接集合判重，支持1至当前缺口条数；重叠集合或父任务正在处理时拒收。
  inherit_replenishment_identity 保留子任务transport batchId/taskId，继承父任务run身份，冲突保留并报告。
- 正常批次回执的写入与任务箱写入之间存在窗口，且未看到直接查询回执的GET接口。
  因此未知结果不能换ID自动重发，保留原命令，先核对接收端记录。这里不宣称无条件exactly-once。

## 本次代码

新增 LinkDelivery 为已收录未递交记录预留唯一递交意图，拒绝同一记录重复预留、链接替换及
每日/补链混用。事务保存冻结请求后再进入已有CommandQueue；崩溃重试仍用相同actor+requestId。
命令sent仅表示获准发送，对外显示awaiting_receipt；明确回执验证后才将素材标成sent。
POST /api/links/deliveries 需要登录、CSRF、confirm=true，link_delivery_enabled 默认关闭。
GET /api/links/deliveries/{id} 查询原命令并核对回执，不产生新发送。

## 验证和剩余条件

隔离运行 test_partial_replenishment、test_task_inbox、test_replenishment_identity 共32项通过；
另运行 test_task_receiver、test_task_inbox、test_replenishment_identity 共29项通过（包含重叠项）。
新增云端测试验证原生批次回执、补链父身份、空回执、命令响应丢失和真实CommandQueue的发送/接收区别。

仍需完成原生任务箱从云端素材生成的接入、完整配额和稳定批次、公司回写、家里OpenClaw入口与浏览器验收。
远程确认及递交开关继续关闭。不得把本次接收端核验当作全链路已验收。
