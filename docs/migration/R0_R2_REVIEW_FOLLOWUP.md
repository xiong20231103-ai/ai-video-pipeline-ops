# R0 / R2 审查修复

仅增加隔离沙箱约束及独立历史数据库的代保留；不启用 history_enabled、不替换 Dashboard，不访问家里生产数据。

## 历史代保留

`HistoryStore(retain_ready=3)` 默认保留每个来源按 sequence 最新的 3 个 ready 代，参数允许 1～8。当前选中代和所有 staging 描述中引用的 baseGeneration 额外保护，不计入这 3 个，可能因此继续触发原来的 10 代/512 MiB 上限；不会为导入成功而牺牲活动数据或未完成导入。

在 begin 的同一事务中清理遗留 ready 代，在 finish 切换成功的同一事务中再次收敛。清理 records、chunks、touched、changes、generations，保留 selections 审计和 highwater。每个 delta 已有完整物化记录，不需要保留祖先链。被清理代的固定分页游标返回 history_generation_missing，客户端需重新从当前代开始；不悄悄换代。SQLite 空闲页复用，不运行 VACUUM；512 MiB 为逻辑保留配额，数据库文件不一定立即缩小。

## 沙箱

目录枚举 os.listdir/scandir/walk、os.path.exists/isfile/isdir/lexists 和 os.utime/chmod 均经过 check。目录/修改类 API 拒绝文件描述符，避免绕过路径检查；显式别名仍映射到 scratch。此机制只用于锁定源码回放，仍不是任意 Python/native 程序的安全隔离环境。

## 验证 / 回退

完整隔离测试 438 项，437 通过、1 跳过，97.813 秒。新增反例证明越界目录元数据与修改均抛 PermissionError；新增 15 次连续导入、跨代回退、staging 基代保护、配额和被清理代拒绝测试。

仅隔离测试通过；真实整批影子和切换未执行。部署前备份独立历史库；回退代码不能恢复已被保留策略清除的旧代，需使用部署前历史库备份。正式启用 history_enabled 之前由 Claude 审查此策略及测试。
