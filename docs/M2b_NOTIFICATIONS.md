# M2b 飞书通知

只在云端运行，读取现有缓存和心跳，不增加家里轮询，不执行安全继续或业务命令。首次部署保持关闭；真实手机收到通知的验收必须单独记录。

## 判据

- 当前失败：summary 当前 batch/task 身份匹配，按 component、phase、attemptId、errorCode 建立事件；不用日期汇总失败数，排除完工清理警告，下载补链与通用失败归并。
- 人工核对：源采集年龄加缓存年龄不超过60秒；当前 blocked/stalled/failed、有 attemptId、allowed 与 continueCanRetry 为真、无生产运行/在途命令、旧自动恢复明确关闭。allowed 单独不能证明需要继续。登录失败不称为可以自动继续。
- 离线：代理心跳超过300秒，区别于UI的45秒阈值；busy不算离线。代理在线而引擎检查持续不可用另报；现有合并健康字段不能可靠分辨 Dashboard 与接收器，消息说明此限制。
- 批次生产完成：有效 completed_verified 凭证、receiptHash、正数且一致的计划/完成数及完成时间；历史回填不刷屏，不称为上传完成。
- 已恢复：相同 batch/task 的新鲜正面证据（running/completed且无错误），或新鲜 healthy/busy 心跳。换任务、数据过期、无数据、失败类别变化都不算恢复。基线中未通知的旧问题不补发恢复。

快照通知尽力而为，可能漏掉两次采集间的短暂失败；不宣称有完整事件游标。

## 发送与去重

console.db 持久化基线、源版本、事件键、失败轮次、首次/末次时间、发送批次和回执类型。首次启用对旧问题建立静默基线，重启不重建。持续同一问题只发一次；恢复后再失败为新轮次。不同任务/尝试/错误保留独立事件键，十分钟同类窗口每批最多五条，其余延后。普通事项北京时间00:00–08:00延后，严重连通性事项可发送。

发送前持久化 intent；超时、中断、半截响应、5xx或不能证明成功时记 unknown，不自动重发；明确拒绝记 rejected。没有外部恰好一次保证。登录后 GET /console/notifications 只返回计数和状态，不返回配置或正文。

飞书 HTTPS text 消息，支持可选签名（timestamp 换行 secret 作 HMAC-SHA256 key，空消息，再Base64）。禁用环境代理和重定向，验证TLS，10秒超时，正文低于20KB。仅整数 code/StatusCode=0确认；原始错误不入库。通知文字剔除URL、令牌和系统路径。

协议依据：[飞书官方自定义机器人指南](https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot)。

## 私密配置与启用

用户在云服务器终端运行：

```sh
sudo /opt/ops-console/current/.venv/bin/python /opt/ops-console/current/cloud/notify_admin.py configure
```

依次隐藏输入 Webhook、可选签名密钥（未开启则回车）、可选关键词（没有则回车）。不可在聊天、命令参数或环境变量提供。配置为 /etc/ops-console/notifications.json，root:ops-console 0640；保存前备份并生成校验版本的一键回滚。默认关闭，云端每五秒重读，无需重启家里或云端。

Codex 随后做隔离手机验收：临时数据库和虚拟时钟产生两个真实飞书消息，明确标记“模拟离线”“模拟已恢复”；不使真实家里离线、不改生产通知账本。用户确认手机收到，重复观察无新增。

```sh
sudo /opt/ops-console/current/.venv/bin/python /opt/ops-console/current/cloud/notify_admin.py acceptance
sudo /opt/ops-console/current/.venv/bin/python /opt/ops-console/current/cloud/notify_admin.py status
```

Claude 先关闭家里旧通知发送端（只关闭发送，不影响流水线），交回回执后再启用云端。关闭旧通知与关闭旧自动恢复是两个独立检查项。

```sh
sudo /opt/ops-console/current/.venv/bin/python /opt/ops-console/current/cloud/notify_admin.py enable --legacy-disabled
```

关闭用同一命令 disable，先备份并返回一条回滚命令。关闭/重开保留通知账本，不重发 unknown。

## 备份和回滚

通知配置仅进入既有 CMS 加密云备份的 CLOUD/config.json 内 _notificationRecoveryEvidence 字段；不新增明文成员、不改恢复白名单。公开清单只有长度和哈希。恢复只解到 evidence，不自动加载或启用。

部署脚本 deploy/m2b-upgrade.sh 先备份代码指向、配置、数据库快照、UFW/Serve/IPv4/IPv6，并在切换前生成回滚。只重启云端服务，不改家里进程/任务或网络规则。回滚保留私密凭据但关闭发送，保留两种账本，不回放数据库。部署先暂停/排空队列，切换后 resume --empty-only。

全量隔离回归、协议模拟、Linux权限 smoke、真实OpenSSL加密/隔离恢复分别保存输出。真实手机验收与旧发送端停用完成前，M2b不记为验收通过。