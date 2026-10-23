# 影子回放当前源码版本登记（第二阶段）

## 2026-10-23：PR #68 后续——新版 helper 组合

本分支以 PR #68 的 `12f8d938fce2f073639ca6ea90f4e383a46655b0` 为基线。以下内容补齐该 PR 明确保留的 helper 缺口；下面的 PR #68 审计记录作为历史保留。未读取生产目录、未安装或启动生产程序。

### 固定组合与合同

`SOURCE_HELPER_PROFILES` 仅允许 PR49 LF / d6a7211 CRLF 两个 app.py 精确身份，各自搭配旧 helper `69b8b086e0502c506e75f1644fe2a3d28c8bac94c99c2b54870c2205fb9199e0` 或新版 helper `57631ede4f2199db025163010e12dfe8ecc493784979194b87c4ead83b2aa818`。后者的独立冻结合同为 `contracts/legacy-verified-final-fresh.txt`，正文直接来自基线 Git 对象，规范化文本哈希必须匹配。不会导入可变的候选 helper 作为 Oracle。

快照的 `captureProof.helperHashes` 明确选择 helper；没有新组合声明的历史快照仍走旧 helper。新组合必须额外包含 `helperIdentities`：每个已声明依赖文件的 size、mtimeNs、ctimeNs、device、inode 和原始字节 SHA256。新版 helper 原始字节只允许冻结正文的完整 LF 或完整 CRLF 形式，不允许 BOM、混合换行或单字节变化。新增组合不会将未知源码或 helper 加入白名单。

### 两项行为差异及事实端口

| 新版 helper 原实现 | 隔离回放端口与断言 |
| --- | --- |
| `_digest` 不再有 LRU 装饰器，每次读取当前摘要 | 每次调用均访问 `FreshHelperPorts.digest`，没有结果缓存。固定捕获时点使用该时点的完整对齐摘要；显式 `verifiedFinalReadSequences` 支持同一快照内按顺序记录的多次读取事实。夹具用完全相同的 size/mtime/ctime/dev/inode、不同的两次摘要，证明第二次调用不复用第一次结果。序列耗尽拒绝，不重复最后一项，也不从 scratch 推断。 |
| 摘要前后比较 st_dev/st_ino | helper 独立 Path 端口在摘要前返回 `before`，摘要后返回 `after`。size、mtime、ctime、device、inode 均取自同一条事实；原函数亲自比较这些字段，dev 或 inode 改变时返回 False。端口不修改全局 Path、不读取宿主媒体、不使用 scratch 的文件身份替代生产事实。 |

新版 helper 的函数正文原样执行，替换的只有 QC 文件读取/媒体 Path 及摘要 I/O 端口。QC JSON 仍由 SandboxIO 从同一快照的白名单正文读取。捕获的静态摘要记录必须与 filesystem 的身份和摘要相符；before/after 任一身份字段缺失、摘要缺失、序列缺项均拒绝。错误即使被旧业务代码捕获，也会通过 Oracle 退出检查强制报 `missing_frozen_content_hash`，不能变成“两边同样失败”的零差异。

旧组合仍保留原有冻结 helper、原摘要端口、缺摘要拒绝及 QC 冲突结果；不会把新身份要求倒灌给旧快照。R1 候选和 Oracle 均按同一明确组合绑定 helper。R2–R6 的算法和真实验收门禁没有改变。

新增事实端口及两个冻结 helper 合同一并列入 R6 精确构建清单，避免出现回放模块在仓库中却未进入未来对象包的问题。原 R6 文件集合保留为 `PREVIOUS_R6_FILES`，更新/回滚校验仍接受其完整原集合；隔离夹具演练旧 R6 → 新清单 → 旧 R6，并检查新增文件已撤回。这里只修改包构建定义，不生成或部署代理更新包，不修改任何已安装清单。

### aligned_capture 新增事实与预算

- 文件/目录节点输出实际 device/inode；依赖读取前后与窗口结束再核对完整身份及原始字节 SHA256，内容相同但依赖被替换也拒绝本窗口。
- 新组合的媒体必须在计划 `verifiedFinalMedia` 中逐条列逻辑路径，且已经出现在白名单树的文件清单中；只接受 mp4/mov/mkv。不扩大目录树，不自动发现或读取计划外媒体。
- 对这些媒体，在窗口开始和结束各重新打开一次，以 1 MiB 块计算 SHA256，不使用 DigestCache，不跨窗口累积部分摘要，不存媒体正文。每次记录读取前的路径 stat、打开后的 fstat、读完的 fstat、关闭后的路径 stat；四者必须与本轮目录事实相等。记录 `alignment=single-open-fresh-sha256-v1`、readBytes、before/after 和摘要；第二次读取记录放在 `windowClose`。两个摘要必须相同，避免只靠 stat 放行同 stat 正文改写。回放也要求这些记录完整并相符。
- 两次读取合计受现有 max_hash_bytes 和 64 MiB/轮中的较小值限制；首轮只使用一半额度，为结束复核预留另一半，因此默认单文件超过 32 MiB 将保持待补。仍遵守 20 秒总窗口，不增加额度。预算不够、写入中、结束时摘要或身份变化时，保留 hashPending 并不发布可比较摘要；helper 真正需要该文件时拒绝回放。小文件原有独立 32 MiB 预算保持不变。
- 实际捕获器仅输出一个已对齐时点的 `verifiedFinalMedia`，不会伪造有序变化。`verifiedFinalReadSequences` 是显式多次读取事实端口，目前由隔离夹具验证语义；没有生产侧的实际序列证据时，不声称覆盖真实运行中的跨时点变化。

### 测试和验收边界

新增隔离夹具覆盖：新版组合从捕获到回放；Oracle/R1 候选一致；同 stat 下摘要变化不复用；dev/inode 分别改变时失败；媒体/依赖身份缺失时拒绝；摘要或序列缺失时拒绝；helper 混合换行的单 CR 字节删除拒绝；同正文依赖替换拒绝；每个窗口重新读取摘要；预算不足和写入中不伪造摘要；旧组合继续工作。原 PR #68 中“新版 helper 无身份事实时拒绝”测试保留并更新预期错误，不移除原组合覆盖。

这些是隔离测试，不是完整真实批次证据。realShadowPassed、switchAccepted 仍为 False；不启用 observe、不部署、不恢复生产。Claude 审查重点是组合闭合、字节身份、读前/读后事实、缺项强制拒绝及媒体预算。

## 2026-10-23：d6a7211 精确字节档案与覆盖边界

本次只检查 Git 对象、隔离 worktree 和冻结合同，没有读取生产目录。核对基线为 main `980d3a966607f81a9ea1533f75f8fdf26eed1918`，其中 app.py 最后修改仍为 d6a7211。

### 源码身份核对

| 对象 | SHA256 | 字节数 |
| --- | --- | --- |
| PR49 已登记的 LF 源文本，也是 `git show d6a7211:app.py` | `9b3ebded024ffa5d9db1662b2fe9fd2e3348e0630efd2f24d1c6bdd61f16d84a` | 333693 |
| 用户提供的当前 CRLF 文件，档案 `contracts/legacy-app-d6a7211-crlf.txt` | `a02d25a6787e0b33725695d616a595396aa4280ed4c9049f309ad1f3b9d6e8b7` | 340806 |

后者由 d6a7211 的 Git blob 将全部 7113 个 LF 替换为 CRLF 得到；没有 BOM 或其他字节变化。移除每个 CRLF 中的 CR 后逐字节相等；整个模块 AST、236 个函数/方法、2 个类相等。从 d6a7211 到本次基线没有 app.py 提交。因此 **PR49 到当前 app.py 没有业务行为变化**，这是同一行为的另一个精确字节身份，并非新版业务实现。

原 aligned_capture 通过 read_text 统一换行后会得到 PR49 哈希。因此仅凭提供的 a02d… 原始哈希，不能认定它是现场 unreviewed_capture_source 的根因；现场包版本、实际输入路径和 helper 身份仍需以后只读核对。本 PR 不宣称解决了完整生产采集准入。

档案通过 `.gitattributes` 的单文件 `-text` 保留 CRLF。捕获、安装预检和离线回放的源文件读取改为保留字节身份；删除单个 CR 后即使 Python AST 和统一换行后的文本相同，也必须拒绝。F78/PR49 的原有 LF 合同保留，合成夹具显式写 LF，不增加任意换行或 BOM 白名单。

### Oracle R1–R6 逐项审计

| 模块及现有合同 | PR49 → 当前 app.py 变化 | 现有回放适用范围及限制 |
| --- | --- | --- |
| R1：`r1-provenance.json` 的 38 个函数、Store/Collector、`collection_verified_final.normalize_task` | 无；完整模块文本和 AST 已核对 | 两个精确源码身份共用 PR49 normalizer 和冻结 helper 端口。现有 QC 成功、摘要冲突、缺摘要拒绝继续适用；不能退回 F78 normalizer。 |
| R2：`contracts/history.py`、`contracts/timeline.py`，冻结 SQLite/文件事实 | 无；数据库写入、状态归一化与时间字段生成函数均未变化 | 历史回放仍依赖同一窗口的完整事实；缺失时间、未覆盖阶段不能推断，也不增加历史或真实批次通过标记。 |
| R3：`r3-provenance.json` 的 25 个函数、`contracts/commands.py` | 无；命令目标、参数校验、回执及传输函数未变化 | 原隔离命令回放边界不变；只读采集不能验证 POST 的真实执行。未实际触发的命令仍待验收。 |
| R4：`r4-provenance.json` 的 44 个函数 | 无；expectedTarget、资格证明、运行锁和原编号查询等函数未变化 | 只证明源码身份适配现有隔离回放；不证明工作台配对协议、人工对账或真实安全继续已通过，更不触发安全继续。 |
| R5：`r5-provenance.json` 的 75 个函数，pending_delete/cleanup_tickets 依赖检查 | 无；预览票据、保护条件、回收/删除相关函数未变化 | 保留原 helper 哈希检查。实际清理未触发时仍无真实验收证据，不能为验证执行删除。 |
| R6：`r6-provenance.json` 的 30 个函数、生命周期/退休门禁 | 无；app.py 内相关函数未变化 | 代理、看门狗、进程移交及 14 天退休门槛不由 app.py 哈希证明；本 PR 不更改这些模块和部署方式。 |

### 依赖变化是独立缺口，不能借 app.py 身份放行

`verified_final.py` 在 8cbb276 后发生了两项实际行为变化：删除 `_digest` 的 LRU 缓存，每次读取当前文件摘要；在读取前后增加 st_dev/st_ino 一致性校验。其规范化文本 SHA256 为 `57631ede4f2199db025163010e12dfe8ecc493784979194b87c4ead83b2aa818`。

现有 Oracle 使用冻结的 PR49 helper（`contracts/legacy-verified-final-pr49.txt`，规范化文本 SHA256 `69b8b086e0502c506e75f1644fe2a3d28c8bac94c99c2b54870c2205fb9199e0`），并以同一快照的内容摘要事实替代媒体读取。它没有覆盖“缓存 stat 相同但正文变化”及“摘要过程中 inode/dev 变更”的跨读取语义。因此 **不登记新版 helper 组合**。当前 app.py 新档案只支持已覆盖的 PR49 helper；如果现场实际 helper 已更新，采集仍应拒绝，等待补齐对应 Oracle、事实端口与夹具后单独审查。

捕获中 verified_final 的期望哈希改为冻结合同哈希，避免同时拿“仓库当前新版 helper”与“PR49 旧 helper”做两个互相矛盾的比较。pending_delete.py 和 cleanup_tickets.py 检查不变。没有取消任何依赖检查，没有把未知 helper 放进白名单。

### 本次验证要求

隔离测试覆盖：精确 CRLF 合同被捕获并保留 a02d… 身份；Oracle 和候选 R1 均使用原 PR49 行为；删除一个 CR 字节时捕获和 Oracle 都拒绝（即使 manifest 随改动重新计算）；新版 helper 在捕获及 Oracle 两侧都拒绝。既有缺摘要、QC 冲突、原黄金合同断言保留。所有合成回放仍不等于真实影子通过，不安装、不启用 observe、不恢复生产。

本PR基于PR49。只补隔离回放与R1候选版本一致性，不安装新采集器，不切换生产读写权威，不修改迁移指针，不声明真实影子通过。

## 原因

实际Dashboard已部署PR49，源文本SHA256为9b3ebded024ffa5d9db1662b2fe9fd2e3348e0630efd2f24d1c6bdd61f16d84a。原Oracle仅接受f78db5a的f4d754cd86c524933d3f87da1006167c2fd698e288fcda09992115dc0e1c044e；把新源码强行交给旧Oracle会拒绝，把旧源码当生产版本则会漏掉成片归一化修复。

## 已实现

- source_profiles只有两个固定源码哈希，调用者不能自行指定任意基线；PR49配套verified_final.py按规范化文本哈希单独核验。原f78黄金文件、黄金输出和AST断言保留。
- collection_verified_final.normalize_task是PR49原方法的逐字提取，测试逐节点比较AST；仅在source_sha明确为PR49时用于独立R1投影。原默认R1逻辑不变。
- Oracle对新profile的成片摘要读取使用冻结事实端口：必须是同一快照中已验证正文的SHA256，或声明过的文件元数据contentSha256，大小/mtime相符。禁止回放时去读生产媒体文件。
- 哈希事实缺失即使被业务函数捕获并返回failed，也在退出Oracle时强制报missing_frozen_content_hash，不能把“两边同样失败”当成可比较窗口。摘要冲突则正常保留QC失败结果。
- Windows短路径/物理路径先经过同一SandboxIO.check和物理根归一化，不能用字符串前缀放行外部路径。
- R6包清单显式加入两个依赖模块与verified_final.py，避免以后构建产生缺文件；没有部署这个包或启用任何引擎。

## 验证

新增7项：精确源码/依赖拒绝、提取AST、新旧归一化相同、缺哈希拒绝、QC冲突保持失败、只读回放同结果、未知候选profile拒绝。另运行R6包/运行时21项，全部通过。原R1黄金回归与本PR CI结果以PR最终状态为准。

## 尚缺，不能由本PR替代

下一阶段要由可信只读捕获器生成对齐的文件/目录/明确缺失路径、进程、外部响应和媒体摘要事实，并给出捕获时源码版本。任意手工JSON中的contentSha256不等于真实采样证明。当前Snapshot仍realBatchEvidence=false，回放报告仍realShadowPassed=false；本PR没有改这些标记。

必须再接通完整捕获窗口、按模块真实触发覆盖、严格差异与两批门禁；R2时间线、R3命令、R5清理和最后R4的当前版本接线仍需逐项完成。不能把本PR的合成夹具计为真实生产影子。

Claude重点审查：闭合源码白名单、依赖哈希、文件事实端口的读取边界、捕获缺项不可被吞掉、原黄金断言未放宽。合并/安装由Claude安排，本轮不部署不重启；回滚源码PR即可，不涉及生产状态迁移。
