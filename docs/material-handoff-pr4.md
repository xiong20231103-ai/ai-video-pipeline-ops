# PR4：素材交接包存储和值班控制

状态：代码审查用，默认关闭。没有修改云端配置、启动新服务、部署、迁移或重启。本 PR 只实现云端存储与权威值班状态；PR5 才接入本机 drain/恢复/epoch 停写，PR6 完成演练和安装计划。不能因为本 PR 合并就启用双端生产。

## 本期边界

只有一份 material.db 随值班交接，云端不做逐事件业务同步、素材查询投影或冲突合并。交接包完整性、权威 holder/epoch、人工强制接管属于本 PR；本机路径重定位、实际 SQLite 完整性检查、截图/manifest 引用闭合、首次事实并集应用属于 PR5。

PR3 合并后的首次基线合同保持：以公司业务状态为起点，双方 `(platform, video_id)` 的历史使用/明确拒绝/黑名单/移除事实取并集、保留来源，其他状态不双向合并。家里原库及附件仍完整存档。PR4 不收业务事件、不应用事实、不触碰家里接收器账本。

仓库 AGENTS.md 原要求直接推 main；本任务用户明确要求逐 PR 审查、说“合并”才合并，按用户指令仅推审查分支。部署另外批准。

## 配置和鉴权

`cloud/material-handoff.example.json` 是要合入将来私有 `OPS_CONSOLE_CONFIG` 的配置片段，不是可替换整个配置文件的模板；`config.json` 根文件属于原 Dashboard 配置，不挪作云端 handoff 配置。

- `material_handoff_enabled` 默认不设置/false：不挂载新路由，不创建交接数据库或存储目录，原 auth/agent/links/备份/命令路径不变。
- 令牌继续用 HTTPS Bearer 机制，服务端只配置 SHA-256。office/home 各一个不同摘要，且不能与原通用 agent 摘要相同；旧 agent 或浏览器 Cookie 不能代替设备身份执行 acquire/activate/上传/commit/release。
- 配置的两个摘要由将来获批的本地私有设置过程写入，不在聊天/命令行/日志/PR里输出原始令牌，不新增公开查询/签发令牌接口。示例字符串只是占位符，启用前缺失/非法配置会拒绝启动。
- `GET /status` 允许已登录用户或任一设备令牌；包下载只接受设备令牌。强制接管只接受现有用户会话 + 精确 Origin + CSRF，设备令牌不能代替人的确认。
- 普通变更从服务端鉴权确定设备，JSON 不接收任意 `device` 字段。两个来源分别鉴权，不沿用上传素材证据的 ingest URL，也不把日常证据 outbox 当交接包。

存储根默认 `console.db` 旁 `material-handoff/`，建议最终显式 `/var/lib/ops-console/material-handoff`，与旧备份/证据分开；后者默认根可能位于不同挂载，不能随意改为 `/srv` 后漏备份或写权限。包含 `handoff.db`、WAL/SHM 和不可变对象 `objects/*.zip`。正式授权部署前备份配置和原控制台代码/库，并核实服务用户目录写权限、磁盘、反向代理上传上限/超时。此次不改 systemd/Tailscale Serve/云端目录。

## 值班状态和请求幂等

持久状态：`generation`（云端服务世代）、单调 `epoch`、holder、phase、session_id（执行世代标识，非鉴权令牌）、lease_until、last_contact_at、current_package、base_package。SQLite `BEGIN IMMEDIATE` 串行化 acquire/activate/drain/release/force；连接跨进程也共享同一事务约束。DB WAL + synchronous FULL。

状态主线：

```text
idle → acquire → preparing → activate → active → drain → draining
     → upload + commit（仍draining）→ release（绑定committed包）→ idle
```

acquire 返回固定的 base_package 和会话。准备/下载期间不能执行素材业务；PR5 本机恢复与校验完成后用同一个 package_id activate。每次新取得值班权或强制接管都会增加 epoch；旧 generation/epoch/session/device 中任何一个不符都拒绝。

首次云端没有完整包时只允许 office acquire，以经本地审核/备份后的公司基线作为来源；home 不能对空白云端自行开工。office 可以从 preparing 直接 drain、上传首包、release，再按同一普通接手流程恢复/activate。必须在正式双端启用前完成首次完整基线包，不能等公司断电后才发现云端从未有过基线。

默认租约120秒，可配置15–900秒。PR5 应每30秒心跳，下载/打包/上传也须续约。心跳/状态返回云端时间，客户端按“收到响应的本机单调时间 + 剩余有效期并留余量”判断，不依赖本地墙钟完全一致；云端拒绝请求/断网/休眠后未复核时停新共享写入。**超时不自动转移**，也不允许过期 holder 通过 heartbeat/acquire 复活；保留 holder，另一端需人的确认。

设备GET status的execution_allowed只针对鉴权设备；另一端即使看到holder正常值班，也得到false。holder_execution_allowed仅展示当前holder的状态；浏览器会话execution_allowed始终false。PR5不能只看“在线/active”字样，仍须检查本机身份、generation/epoch/session及有效期。

acquire/activate/heartbeat/drain/release/force 都要求稳定 request_id（8–100位ASCII字母、数字、下划线/连字符）。同actor/action/request_id、同内容重复安全；不同内容409。持有者请求重放必须仍通过当前 fence；旧 acquire 回执不能在换班后复活旧会话。重放旧 activate/heartbeat 返回当前状态，不能将 draining 误报成 active。release 回执丢失可在下一端已接手后重取原成功结果，但不会改当前指针/holder；客户端随后查 status，不将旧回执当当前许可。

该幂等表只保存交接控制请求，不是素材业务事件队列；不要求家里接收器每次收任务核云端锁。PR1 独立防意外重复，允许既定正常复用；值班变动不撤销家里已经接收的生产任务。

## API 合同

前缀 `/api/material-handoff/v1`，JSON 请求均只接受列出的字段：

| 接口 | 鉴权/请求 | 结果和边界 |
|---|---|---|
| GET `/status` | 设备Bearer或现有登录会话 | holder、phase、lease、最近联系、current/base包、可选完整候选包、未决计数、存储预留、最近30条审计；不返回设备执行session。 |
| POST `/acquire` | 设备；`request_id` | 新租约preparing、固定base包、generation/epoch/session_id。接管准备权需额外提交控制台选择的generation/epoch以领取自己的reservation。 |
| POST `/activate` | 设备；fence、request_id、`package_id` | 必须等于取得权时base_package；第一次office本地基线可为null，不能当成已下载云端包。 |
| POST `/heartbeat` | 设备；fence、request_id | 续有效租约，不复活已过期或旧epoch。 |
| POST `/drain` | 设备；fence、request_id | 记录交接阶段；本地是否真正drain由PR5负责，不能以云端phase代替本机在途检查。 |
| PUT `/packages/{id}` | 设备；fence请求头、大小/sha头、ZIP流 | 只允许draining；流式验证，持久预留容量、fsync；完成后重新检查fence，再登记staged，不改current。 |
| POST `/packages/{id}/commit` | 设备；fence JSON | 验证整包hash和逐文件manifest，耗时校验后再检查fence；标committed，不自动release。 |
| GET `/packages/{id}` | 设备Bearer | 只下载committed包；响应含X-Package-SHA256/X-Package-Bytes，客户端仍须完整验证。可下载历史完整包，不能下载staged/失败上传。 |
| POST `/release` | 设备；fence、request_id、`package_id` | 只允许draining；包须当前holder/epoch提交且parent等于当前包，事务内更新current并清holder。 |
| POST `/force-takeover` | 登录用户+CSRF；见下 | 原子作废旧epoch、选择完整包并为目标建准备权，记录审计；不激活、不重发未知项。 |

fence JSON：`generation`、`epoch`（整数，非bool）、`session_id`。

上传头：`X-Handoff-Generation`、`X-Handoff-Epoch`、`X-Handoff-Session`；`X-Package-SHA256`（小写64位hex）、`X-Package-Bytes`。有Content-Length时必须与声明一致；没有长度也逐块限制。ZIP默认上限2GiB，总容量默认20GiB，额外保留64MiB磁盘余量。全量包先行，没有未经测量的分块协议。

流大小/hash不符、断传/进程崩溃不登记完整包；保留不可下载的未引用对象及容量预留供以后人工检查。同一包ID不同内容或不同世代409；已登记且相同的上传重试返回原结果，不重复写文件。不同尝试并发只可能有一个不可变登记，另一个留不可引用副本，不变更current。

达到容量或磁盘不足返回507，不能为了让新包传完自动删除旧库/旧包/未核对材料。后续维护/扩大容量需另批；任何删除前必须备份并验证可恢复。由于失败尝试也预留最坏大小，503/507不会假装成功。未实现自动历史回收或清理SQL。

## ZIP / manifest v1（PR5 生产者使用）

ZIP只允许普通文件，不接收目录条目、符号链接、加密ZIP、重复/大小写碰撞路径、路径穿越、盘符、Windows保留名/尾点/尾空格/控制字符。不解包、不执行包内代码。

唯一根文件 `manifest.json`（最大4MiB）和 `material.db`。附件仅放 `attachments/`、`review/`、`mf-judge/`、`exemplars/`、`baseline/` 下。机器site/device/mf_device配置、.env、凭据/Cookie目录、WAL/SHM、PID、私钥等路径拒绝。图片/manifest/正反例/首次来源事实可以在这些逻辑目录中保存；绝对路径恢复由PR5完成。

manifest固定字段（不含文件自身的hash，以免循环）：

```json
{
  "format": 1,
  "package_id": "package-fixture-0001",
  "parent_package_id": null,
  "source_device": "office",
  "generation": "<acquire返回的世代>",
  "epoch": 1,
  "schema_version": "material-v1",
  "code_version": "<实际发布代码版本>",
  "created_at": "<带时区的实际打包时间>",
  "unresolved": {"imports": 0, "collector_ops": 0, "attachments": 0, "reconcile": 0},
  "files": [{"path": "material.db", "bytes": 4096, "sha256": "<文件实际SHA-256>"}]
}
```

示例只是字段结构，数值/hash不是可用包。manifest JSON不允许重复键或NaN/Infinity。包ID/设备/generation/epoch/parent必须与当前上传登记相同；所有非manifest文件必须恰好在清单中，大小/hash逐项验证，无遗漏/多余文件。最多30,000个内容文件、展开总量4GiB，仅stored/deflated压缩。云端核对material.db的SQLite文件头和hash，**不把文件头正确称为SQLite完整性/外键检查已通过**，不执行上传库SQL。

PR5在两端对一致副本做integrity_check/foreign_key_check、版本兼容和业务附件引用闭合，再请求activate或正常release。manifest版本字段是客户端报告，云端只保存，不能代替实际兼容性校验。当前normal包collector_ops或attachments非0会拒绝commit；先确认入库或保全到待核对材料并清楚界定已处理状态。imports/reconcile可非0：未知导入不能重建编号重发，也不冻结其他无关工作。

## 控制台强制接管

页面 `/material-handoff`（需现有登录），有返回控制台链接；无新令牌输入，不修改现有V2布局/默认入口。最终部署后可直接打开此路径。本页显示旧holder/租约/最近联系/完整包时间/未决摘要/容量和审计。

用户必须手工选目标和完整包、填写原因、勾选“另一端已停止”确认，默认不勾选，刷新/换包会取消确认。按钮不是自动开工，成功后提示目标设备还须acquire预留、下载校验恢复、activate。回执丢失只重试同request_id，刷新当前权威状态再判断，不假定失败就没执行。

force JSON：request_id、generation、epoch（来自所见状态），target_device、package_id、reason（1–500字）、other_device_stopped=true、confirmation=`另一端已停止，未完成操作作废`。缺确认400，未登录401，Origin/CSRF错误403，过期屏幕epoch409。

可选包为当前已发布包，或旧holder在本epoch上传并commit、parent正好等于current的最新完整候选；后一种涵盖“包已完整提交但release回执前断电”。只能选committed包，不能选半包/任意历史分叉。控制台明确列包时间，不自动把“最后一次提交”当“所有进度最新”。若从未有完整首包则拒绝，必须先完成首次基线。

事务作废旧epoch，递增后把所选包设current，并为目标建立preparing reservation；不向浏览器返回设备session，目标用自己的令牌和所见generation/epoch acquire领取。准备权同样有租约，目标应及时领取并在恢复过程中续约；过期再次人工确认，不自动释放给另一端。可重复确认同一目标以恢复已过期准备权，仍记录新epoch。

审计记录：用户ID、时间、旧holder/epoch、目标、包、原因，未知操作标needs_reconcile。这里“作废”只指执行许可；不撤销已到家里流水线的任务、不清空PR1账本。PR5逐项查询原导入，查不到标待核对，其他工作可继续。

## 重启、备份恢复和回滚

普通进程重启重用handoff.db，保留generation/epoch/holder/包指针/请求回执/审计；不会清空锁。重启时间超过租约后，旧执行许可失效，仍需确认接管。

云端从旧控制库备份恢复时不能让旧generation重新有效。恢复前停新交接、确认两端素材客户端停止，保存现状控制库和完整objects存储的可恢复副本；恢复DB与对象后保持功能关闭，不先让旧端连入。在获批离线窗口运行下列命令（只是未来执行说明，本轮未运行生产命令）：

```text
python -m cloud.material_handoff_admin recover-generation --root <交接存储根> --backup-dir <独立备份目录> --actor <执行人标识> --confirm-both-devices-stopped-and-cloud-offline
```

命令要求已有控制库，先SQLite Online Backup到全新独立目录、integrity_check、SHA-256/manifest，再核验当前完整包、记录recovery审计并更换generation、增加epoch、清旧holder。objects不改不删，最新完整包指针保留，客户端必须重新acquire/恢复。不能只恢复DB、缺少对应objects还宣布可用；缺包/坏hash会拒绝恢复重置。

控制库备份命令不是完整灾备：其前置条件是管理员另行完整保全objects及原运行配置/发布。回滚应用版本前保持handoff关闭，保全新增对象、控制库和审计。不能回滚控制库后自动继续旧会话；恢复必须更换generation、两端重新确认。生产部署/回滚操作留最终用户批准窗口，PR6给固定版本与现场步骤。

若objects已有包而handoff.db缺失，启动拒绝静默创建空白基线，要求保全并离线恢复。若恢复的旧DB不认识某些仍保留的objects文件，它们仍计入容量，不能假装为可用空间。没有控制库就不能据文件名猜测最新业务水位。

## 验证与后续

`python -B tools/run_material_handoff_tests.py` 使用现有隔离runner：仅仓库/临时目录写，禁止生产网络/进程，仅保留stdlib Windows asyncio内部socketpair豁免；合成平台探测避免Argon2启动cmd，未降低应用网络限制。

涵盖公司→家里→公司、并发抢占、幂等及请求内容冲突、租约过期、原包固定、commit/release顺序、强制接管/CSRF、旧epoch、上传错误、ZIP路径/附件/hash、存储容量、离线控制库备份与换世代，以及原auth/命令队列/备份/links/通知回归。测试的SQLite文件头样例不是生产库，不冒充实际integrity演练。

`node --test tests/material_handoff_ui.test.cjs` 用无网络DOM替身验证未预勾选、读取不变更、刷新重确认、丢ACK复用原请求ID及提示。不是生产浏览器截图验收；PR6现场验证控制台与两端工具。

提交前还进行本PR自审和敏感格式扫描。各PR仍逐个审查、用户说“合并”才合并；本轮不启动PR5、不部署云端、不部署PR3。
