# M1b：加密台账与配置备份

以方案 §11 与审查必改 10/11 为边界。这里只恢复台账/配置，不含视频、音频、剪映草稿、缓存、日志、运行进程、锁或自动执行能力。

## 数据与运行方式

- `agent/backup_policy.py:RULES` 是固定深度逐文件白名单：OPS、工作台、Fish、剪映客户端、生成记录、独立代理配置及 H2 待删区的清单。C/E 盘待删区只取 `pending-delete.json`，不取被移入的媒体。拒绝祖先和匹配项中的链接/重解析点；必需文件缺失、超限、连续不稳定读取均失败，不静默跳过。未来 M2 执行台账需单独加入，当前可重建的 agent.db 不备份。
- 家里每天北京时间 03:00 后首次成功联网时补做当天备份；可从云端请求一次。只增加代理内部备份线程，不增 Windows 任务，不改变 Dashboard 和工作台。
- 已有 Dashboard Python + 已有 Git OpenSSL，无新增 Python 包。短生命周期隐藏子进程打包，限制代理常驻内存；SQLite 用 Online Backup 和完整性检查，JSON 比较打开前/读完后的文件身份并验证完整 JSON。记录采集起止窗口，不保证多个文件处于同一个业务事务。
- 台账与含密钥配置分包，两个包都用 CMS AES-256-GCM + RSA-3072/OAEP-SHA256 加密。RSA 私钥另用口令加密，只保留家里/离线介质，绝不上云。公钥证书可登记云端，云端据此加密自己的数据库备份。参考 [OpenSSL CMS](https://docs.openssl.org/3.0/man1/openssl-cms/)。
- 本地只保留未确认上传包和临时工作文件；确认后删除密文副本。中断后按相同 packageId/内容重试，上传前预留配额，分片校验长度/SHA256，全部齐备才发布。云端只做密文形状和哈希校验；GCM 认证在隔离恢复时检查，不能把云端 SHA256 校验当成已解密验收。
- 默认总配额 **10,000,000,000 bytes**。家里最近 30 个实际备份日期 + 最近 3 个月月初备份，云端数据库最近 14 个实际日期；同一日期保留最新一包。不会补造缺失日期。超额先回收旧日备份，记录实际事件；至少保留每类最新包，空间仍不够则拒收，不虚报成功。未完成上传也占预留配额。
- 回收使用数据库事务加重命名待清除目录，事务失败改回原名，启动时处理进程崩溃留下的中间态。删除失败的垃圾仍计容量，不能用账面删除掩盖物理占用。
- 云端每天 03:30 后在现有单 worker 服务内补做 console.db、备份目录台账和配置的加密快照；没有公钥时等待配置。不增端口、systemd 服务或外部定时任务，不变更 Serve/Funnel/防火墙。
- 登录后页面末尾“异地备份（台账与配置）”可查看实际保留日期/占用/事件，请求备份、校验及下载 manifest.json 与密文。请求和校验需要会话与 CSRF；代理上传需要已有代理令牌，没有私钥上传接口。

## 用户在本机配置（Claude 部署此 PR 的代理包以后）

在用户自己的 PowerShell 依次执行，输入新恢复口令两遍（至少 16 字符）。不要把口令、私钥、代理配置正文发聊天或放进日志：

```powershell
Set-Location -LiteralPath 'E:\Backup\ops-agent'
& "$env:LOCALAPPDATA\TikHubOPS\venv_cuda\Scripts\python.exe" -B -m agent.backup_setup
```

此命令不读取代理令牌，不重启任务，不访问云端。公钥和备份设置写 `%LOCALAPPDATA%\OpsAgent`；加密私钥写 `%LOCALAPPDATA%\OpsAgentRecovery\v1\recovery-key.pem`。立即将整个 v1 文件夹复制到离线介质，恢复口令另存。已有配置/密钥时拒绝覆盖；轮换公钥需要另外审查的本机云端管理员操作，不能自动替换。

## 隔离恢复验收

下载同一包的 manifest.json 和所有 CMS 文件到新目录。用户自己在家里终端运行，`--target` 必须是新的隔离目录，不能位于任何生产根目录；口令只在交互提示中输入：

```powershell
& "$env:LOCALAPPDATA\TikHubOPS\venv_cuda\Scripts\python.exe" -B -m agent.backup_restore --package 'E:\Backup\restore-download-PACKAGE' --target 'E:\Backup\restore-evidence-PACKAGE' --certificate "$env:LOCALAPPDATA\OpsAgentRecovery\v1\recipient.pem" --key "$env:LOCALAPPDATA\OpsAgentRecovery\v1\recovery-key.pem"
```

输出必须 `verified=true`、`automaticExecutionAllowed=false`，核对文件数/大小、哈希与 SQLite integrity_check。所有文件放 `evidence/ROOT/...`，任何 pending/recovery/历史命令都只是证据，不可把服务指向该目录自动重放。人工恢复前检查媒体仍存在、路径匹配、实际进程和草稿 lease、上传台账、未完成命令与幂等身份；跨文件采集窗口内状态可能变化，需要对账。

合成加密/恢复测试不是实际生产备份验收。只有用户配置恢复密钥、真实包已上传且隔离恢复通过后才记 M1b 完成。

## 部署与回滚

- 家里：独立 `E:\Backup\ops-agent` 代码白名单包，沿用已有普通权限优雅更新器。更新前备份，入口打印本次唯一 `rollback.ps1` 命令。不更改计划任务设置、令牌、生产仓库，不重启 Dashboard/工作台/接收器。由 Claude 审查部署。回滚保留已加密备份和私钥，旧版忽略新增备份配置文件。
- 云端：使用提交固定的代码包，备份当前 release 链接、服务、Serve、规则和数据库，生成一条命令回滚后再切换；旧数据库 schema 不变，新增 vault 独立目录，回滚旧代码不删除备份。
- APT/pip：`deploy/m1b-repair-sources.sh` 在任何配置变化前保存全部 sources、pip 配置、UFW、IPv4/IPv6 规则与元数据，并生成回滚脚本。只把已识别的内网 Ubuntu 镜像替换为公网 HTTPS 阿里镜像、pip 替换为官方 PyPI；保留签名验证和 Tailscale 源。不安装或升级包。`apt-get update`、`unattended-upgrade --dry-run --verbose`、PyPI HTTPS 与规则比较任一失败自动恢复配置。干跑输出不代表升级过软件包，见 [Ubuntu 文档](https://ubuntu.com/server/docs/how-to/software/automatic-updates/)；pip 优先级见 [官方配置文档](https://pip.pypa.io/en/stable/topics/configuration/)。
- 进度文件须记录两类实际回滚路径、原始输出；若需整体回滚，另给入口依次调用两份脚本，不操作 M0 防火墙或其他项目配置。

## 检查

`tools/run_isolated_tests.py` 阻断生产网络、进程和目录写入；真实 OpenSSL、SQLite/WAL、隐藏打包/流式上传重试和隔离恢复测试仅用临时合成资料；Windows 任务和 Job/监督器现有测试仍需全绿。网页夹具需验证下载/校验/排队按钮、CSRF、手机无横向溢出。

原有按需通道单元测试的 0.5 秒整体计时包括 Windows 首次 SQLite 初始化；改成因果断言：慢 safety 请求仍被闸门阻塞时，按需请求必须独立完成。没有改变真实链路性能验收目标。
