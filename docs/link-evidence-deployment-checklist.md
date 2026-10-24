# 云端只读素材副本：部署前清单（待Claude审查，未执行）

适用于PR #63的只读版，不包括实验分支的确认、动作流、递交，不包括公司端回写。
本文件只供审查；批准审查不等于部署授权。还需用户明确说“部署”。

## 1. 版本和备份检查

- 记录当前部署代码提交、配置文件版本、service/timer/drop-in状态，保留原有未提交改动。
- 确认证据模块从未部署或记录已有links.db的schema；已有草稿库必须先在隔离副本验证兼容性。
  特别检查旧版review NOT NULL结构；本PR没有自动迁移该旧草稿结构，不能直接覆盖或盲目升级。
- 已有links.db使用SQLite在线backup取得一致性副本，不能只复制主文件而遗漏WAL。
  备份不得与素材业务数据库混用；截图没有多份备份，必须在变更说明中向用户说明这一点。

## 2. 环境变量和配置键（不含任何秘密值）

| 名称 | 类别 | 处理 |
|---|---|---|
| LINK_EVIDENCE_TOKEN | 新增服务环境变量 | 用户本人提供专用Bearer令牌，禁止复用原agent令牌 |
| OPS_CONSOLE_CONFIG | 现有服务环境变量 | 沿用现有配置位置，不在审查输出中打印配置内容 |
| PYTHONDONTWRITEBYTECODE | 现有服务环境变量 | 沿用现有设置 |
| link_evidence_enabled | JSON配置键 | 默认关闭，准备完成且获准部署后才打开 |
| link_evidence_dir | JSON配置键 | 指向独立证据目录 |

本PR不需要公司回写令牌、远程确认或递交开关；旧写开关即使残留也不能注册写路由。
私密环境文件建议为/etc/ops-console/link-evidence.env，由root拥有、模式0600，用户本人填入令牌。
不要运行会把环境变量值展开到聊天、日志或进程参数的命令。

## 3. 目录、属主和权限

| 位置 | 属主/权限 | 说明 |
|---|---|---|
| /srv/ops-console/link-evidence | ops-console:ops-console，0700 | 部署时预先创建，独立证据根目录 |
| links.db及其WAL/SHM | ops-console用户读写，0600 | 业务运行生成，必须同目录允许写入 |
| shots/日期 | ops-console用户读写，目录0700/文件0600 | 临时图片，15天规则及pending保护 |
| db-backups | ops-console用户读写，目录0700/文件0600 | 在线DB备份7份，无图片备份 |

原ops-console.service已有UMask=0077；新增维护service也明确UMask=0077。
不要使用宽松权限来绕过失败，不改变其他项目数据权限。

## 4. systemd和网络核对

原服务使用ProtectSystem=strict，目前只允许/var/lib/ops-console写入。
要在保留原ReadWritePaths的前提下，通过专用drop-in追加证据目录；不修改主服务监听参数。
以下是待审查模板，不是已执行操作：

```ini
# /etc/systemd/system/ops-console.service.d/link-evidence.conf
[Service]
EnvironmentFile=/etc/ops-console/link-evidence.env
ReadWritePaths=/srv/ops-console/link-evidence
```

- 确认合成后ReadWritePaths仍含原/var/lib/ops-console，并新增证据目录。
- 保持127.0.0.1:8000、原Tailscale HTTPS443和原鉴权，不新增公网监听、反向代理入口或匿名媒体路径。
- 审核deploy/ops-link-evidence-maintenance.service与.timer：每日北京时间03:30，Persistent补跑。
  不替换或重置collector的既有03:30备份任务；这只是独立links.db备份。
- systemd-analyze verify检查单位文件后，只有获准部署才daemon-reload、安装/启用timer及按需重启应用。
  审查期间不得运行这些安装或重启操作。

## 5. 部署后验收（仅获准部署后执行）

- 用独立合成来源验证Bearer鉴权、登录会话图片权限、2MiB请求限制和每分钟限速。
- 四个模块路由外，decision、changes、deliveries须为404；确认不会生成素材决定或生产命令。
- 验证同序号只补缺图、旧序号不覆盖新图、pending容量保护、未审核记录过期留链和容量报警。
- 在浏览器检查图片complete且naturalWidth>0，刷新历史再验证，不能只数img元素。
- 用隔离测试目录验证清理日志的张数/字节以及7份可读DB；确认没有截图进入备份。
- 记录云上真实links.db和7份备份总字节；当前隔离小样本大小不能作为生产容量报告。
- 真实业务生产目录、公司队列、收录/放弃、补链和提交接口不用于这些合成验收。

## 6. 回滚顺序

1. 关闭本次link_evidence_enabled，并停止/禁用本次新增维护timer；暂停公司新增上传器，保留outbox。
2. 记录故障版本和部署后新增证据，保留links.db及WAL/SHM，通过在线backup保存现场；不删除链接或图片目录。
3. 恢复这次变更前的代码及对应配置，移除仅本次新增的drop-in/timer，保留原服务配置和collector备份任务。
   按获准的维护窗口daemon-reload并恢复应用；不顺手升级/卸载其他组件。
4. 验证原ops-console页面/原服务正常，新增路由关闭。证据文件保留用于后续修复，旧应用无需读取新证据库。
5. **不恢复或覆盖素材业务数据库，不覆盖部署期间真实用户决定。**
   正常回滚不把证据库回退成旧快照，以免丢失新上传记录；任何schema恢复必须另作兼容方案并保留新数据。

上述步骤尚未执行。Claude审查通过后，仍需用户明确授权部署。
