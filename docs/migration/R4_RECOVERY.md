# R4 安全继续与命令对账候选

用户2026-10-20批准连续推进R4～R6，并再次批准工作台请求截止/撤回修复。候选默认仅隔离/影子，不安装权威写宿主，不接生产worker。家里部署/切换仍交Claude；SPC德语主动暂停、autoRecovery关闭、云端cleanup关闭保持原约束。

## 模块与来源

recovery_logic.py机械提取固定f78db5a的44个函数，包括H3锁内expectedTarget比对、同clientRequestId不换目标、请求入队/归档/过期/邮箱对账、Fish/CapCut停点、工作台健康、命令查询/撤回与reconciliation投影。全部函数及行号见r4-provenance.json，测试逐个AST函数体对照，移除的仅HTTP注册装饰器。源码SHA256与R0相同，不导入运行中的app.py。

recovery.py显式注入状态路径、Store、Collector、当前箱/日期/上传投影等端口。各隔离session有独立锁和health cache。普通GET中的对账写入全部限定在R0快照scratch；这不是第二个生产执行者。候选不调用调度器，不注册新计划任务，也不接ExecutionWorker。

## 已批准的刻意安全改变

旧Golden保留历史原样；新协议差异单独测试，不把修复冒称零差异：

- 工作台前置PR https://github.com/xiong20231103-ai/ai-video-workbench-suite/pull/30，RecoveryControl protocol=2，在原OS锁内做截止/撤回/投递/claim检查。
- recovery_transport.py绑定已有RC实例，不动态寻找/导入工作台代码；协议不支持expiryChecked/cancelUnderAuthorityLock时拒绝。
- 提交从已持久化的原命令取requestedAt/expiresAt/commandId，校验完整目标签名；不重算截止。请求被标expired/cancelled/reconciliation_required时不启动工作台。
- 撤回先获RC对独立源与同ID未开始mailbox的持久确认，再公开取消Dashboard台账；丢确认不冒称成功。executing/unknown拒绝撤回，只按原命令对账。
- 无截止的历史未执行请求保留并转人工对账，不补一个新期限；已生成权威命令/alias和已有执行/unknown不受传输TTL终止。原恢复预算、资源守卫及acceptance gate不变。

bind_transport目前也只允许isolated=True，真实宿主接线尚未交付；capability.enabled=false、mode=shadow，不提供send。**此PR是候选与协议适配器，不能直接作为“R4全部完成/可切换”的证据。** R6宿主前还需同权威锁的读写集成、所有旧反向调用路径、完整规则正反边界矩阵以及真实完整批次影子。不能靠把enabled改true绕过。

## 测试证据分层

1. 原44函数逐个AST与行号核对；20个R0固定profile×28 GET（560项）响应、文件/数据库副作用、HTTP只读取数一致。业务时间/目标/计数/状态不忽略。原始行为对比为隔离，不是完整生产批次影子。
2. 14个旧恢复回归与9个H3回归，重绑定到候选命名空间执行；涵盖缺RC、独立请求冲突不覆盖、90秒未领取/桥接失败、活跃会话不解锁、CapCut停点、工作台启动失败结构、工作台当前context、锁内目标比较与同ID冲突。
3. 协议2适配器测原截止不变、协议缺失/降级、目标签名不符、撤回权威确认顺序、丢确认/错误ID不报成功、执行中/unknown拒绝、过期不启动。工作台真实RC临时文件测试见其PR，ops侧使用协议替身，不能冒称跨仓生产联调。
4. R4-01～30、RC-01～12共42条来源见contracts/shadow_rules.json。当前已覆盖上述部分规则的隔离断言，**尚未逐条获得全部正反边界证据，真实影子全部not-run**；不把相关旧测试或560 GET一概记为42条全通过。验收矩阵保留缺项，后续补齐前禁止切换。

## 部署与回退边界

PR按#40→#41→#42→#43→本PR审查；工作台#30为新协议前置。实际部署前Claude须核对原request_id能传到claim、全部启动/对账调用同一权威、旧无截止生产者禁用及已有pending人工清点。不能单独部署工作台协议后继续让旧Dashboard生产无截止请求。

本轮未合并/部署，移除本候选不改变现有运行路径。未来启用后回退必须暂停、排空并人工对账unknown；原ID/截止/权威台账不可回滚覆盖，cancelled/expired/人工对账记录不得复活。旧无截止传输不作为可恢复的“回滚选项”。真实部署时先备份再生成一条回滚命令，本PR不虚构生产备份。
