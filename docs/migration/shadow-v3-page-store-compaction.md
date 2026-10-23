# v3 证据库：数据库按页去重与每批压缩

## 为什么改

405a0b0 禁用预检（2026-10-23，批次暂停）第 2、3 轮各新增约 23 MiB。Claude 只读实测间隔 2 分钟的两次 `ops.db` 在线备份：

| 去重粒度 | 2 分钟新增 |
|---|---:|
| 64 KiB 块 | 22.56 MiB |
| 4 KiB（SQLite 页） | 2.77 MiB |

各表行数不变，是原地更新。改一行只改一页，64 KiB 切块把它放大约 8 倍。

## 证据库

- `manifest` 中 `kind=sqlite` 的文件按文件头页大小（512–65536 的 2 的幂）切块；其他文件仍为 64 KiB。
- 数据库索引不再逐页列出 3 万多个键，而是 `{"pageSize":4096,"segments":[...]}`：每 256 个页键组成一个"页清单段"对象，同样按内容去重。未变化的段不再占空间，单个快照索引约几 KB。
- 旧的列表格式索引照常读取；恢复时逐页、逐段校验 SHA256，段损坏就拒绝恢复。

## 预检估算

禁用预检按同样的页 + 段布局估算增量，并另给 `databaseNewBytesAt64KiB` 作对比。摘要上限从 32768 提高到 262144，126 MiB 数据库约 3.2 万页。

## 每批压缩（`tools/shadow_store_compact.py`）

一批回放比对结束、结论确认后：

```
python -B tools/shadow_store_compact.py --store <v3>\store --verdict <结论.json> --drop <快照> --keep <关键快照>
```

- 默认只预演，打印可释放字节，不改任何文件；`--apply` 才执行，由用户运行。
- 结论文件 `schema=1`、`batchId`、`conclusion`（accepted / rejected / incomparable）、`snapshots`，必须覆盖所有要删和要留的快照；`pending` 或未覆盖都拒绝。
- 至少保留一个关键快照；批次外的快照及其对象不受影响。
- 先把被删快照的索引移到 `store/retired/<batchId>/`，再删除没有任何剩余快照引用的对象，最后写 `compaction.json`。中途中断只会多留对象，不会留下指向已删对象的快照。
- 采集或写入锁存在时拒绝。不碰比对结果、差异报告、ready 记录和 v1/v2 旧证据。

## 未改

v3 固定容量仍为 2 GiB。提高到 5 GiB 需用户另行明确同意后单独修改。
