# app.py 启动形态审计（#59）

基线 main `6b68a16a4cfcf2d26cf7427bcee593dbd0fd83d6`；本 PR 不修改 app.py。只做源码审计、抽取定义的合成数据库测试和独立假应用进程夹具，不导入生产应用或读取生产配置。

## 结论：存在启动形态差异，不能宣称无条件等价

旧入口 `python app.py` 先以 `__main__` 执行，再由 7004 行 `uvicorn.run("app:app")` 导入同一文件为 `app`；实际服务和 lifespan 使用第二份模块。bootstrap 直接导入 `app` 一次，向 uvicorn 传这个对象。**CONFIG 读取次数、Store 初始化次数和闲置模块对象数量不同。** 在稳定文件、无并发写入条件下可以证明部分逻辑结果一致；数据库物理写入、锁等待、两次读取之间外部状态变化的效果不能证明相同。

因此报告固定 `startupShapeEquivalent=false` 并列差异，`installationPermitted=false`。这份报告不是安装许可。原 app.py、看门狗、VBS 不改。

## 逐项副作用

| 位置 | 模块级行为及间接副作用 | 旧两遍 / 新一遍 | 证据与限制 |
|---|---|---|---|
| 3–46 import | 标准库、psutil、FastAPI/uvicorn、pending_delete、CleanupTickets | 在同一解释器中相同依赖模块由 sys.modules 缓存；两次执行的是 app 文件，通常不会重载依赖 | 未声称穷尽第三方库内部平台初始化。两个入口均导入同版本依赖；真实宿主导入期间的外部变化未验证 |
| 29 | 新 ContextVar，默认 False；cleanup_source_guard 在装饰时只构造 wrapper | 旧第一份 ContextVar/包装函数闲置；请求使用 app 模块那一份，新也是一份 | 源码没有模块级调用被包装业务函数。对象数量不同，不能称对象身份相同 |
| 48–64、66–68 等常量 | Path(__file__).resolve、路径和字符串、集合；59/102/2541/2542 正则编译 | 路径稳定时值相同，多出一份无服务引用的常量/正则 | 路径元数据查询次数不同；应用目录被移动/链接变化等竞态未证明等价 |
| 65、70、76、79、94 | 五把 threading 锁（3 RLock、2 Lock）和邻接内存缓存 | 旧第一份锁/缓存无人处理请求；服务使用第二份，新使用唯一份 | 不是跨进程命名互斥量，没有模块级获取这些锁后启动业务。额外闲置对象数量属于形态差异 |
| 222–268、4615 | load_config：读取主机名、拼接默认路径，若 config.json 存在则读取并解析，失败使用默认值；没有写配置 | 旧读两次且监听 host/port 取第一份，路由/collector 取第二份；新只读一次并同时用于两者 | **启动形态差异**：文件不变时返回值一致（夹具验证）；若两次读之间修改，监听和业务配置可能不同。新旧不无条件等价 |
| 3000–3083、4616 | Store：mkdir data、创建 RLock、连接 ops.db、启用 WAL、CREATE IF NOT EXISTS、按列补迁移、兼容 UPDATE，然后提交/关闭连接 | 旧顺序执行两次，新一次 | **启动形态差异**：合成库证明重复初始化后逻辑 schema/迁移行相同；不证明数据库/WAL字节、I/O次数、锁等待相同。两次之间有并发写入、迁移中断或旧错误重新出现时未证明等价。构造完成后 SQLite 连接由 finally 关闭，不留模块级数据库句柄 |
| 3309–3348、4617 | Collector 构造：Event、thread=None、内存状态；调用 load_test_reset_state/read_json_object 读取 test_reset_state.json 并 parse_time | 旧创建两份对象，第一份未 start；新一份 | 无模块级线程启动。**启动形态差异**：reset 文件读取次数不同，两次之间发生变化时未证明相同；默认字典和 Event 是闲置对象差异 |
| 6138–6146 | FastAPI、GZipMiddleware、StaticFiles，挂载静态目录；随后路由/异常处理器装饰器注册（含 7003 行之后的云端路由） | 旧第一份 app 未服务；app 模块完整导入后服务第二份，新完整导入一次后服务这一份 | 稳定静态目录时服务对象包含相同定义和路由；StaticFiles 的目录存在检查次数不同，目录变化/权限变化竞态未证明等价 |
| 6126–6135 lifespan（延后执行） | COLLECTOR.start，创建 purge Event 和 purge 线程；退出时设置 Event、停止 collector | 旧只有 uvicorn 导入的 app 进入 lifespan，第一份 __main__ 不进入；新也只有服务 app 进入 | AST 验证 Collector.__init__ 不创建/启动线程，lifespan 只有一次 COLLECTOR.start。控制流均为一个 collector 与一个 purge 线程；没有用生产运行证明其具体时序完全相同 |
| 7003–7010 __main__ | uvicorn.run：配置服务/日志、绑定端口、执行服务生命周期 | 旧走字符串再导入；新对象式执行，日志/异常处理由同版本 uvicorn 完成 | **启动形态差异**：导入次数/时机不同。真实假应用夹具验证 stderr 不导致回退、正常退出 0、服务后退出 23、kill/占用端口不拉旧入口。并非生产程序等价证明 |
| 7015 CleanupTickets | 内存 records={}、RLock、时钟引用；不生成 ticket、不写文件 | 旧服务前只会完成 app 模块那份；__main__ 到 7004 会阻塞，直到服务退出才继续构造闲置那份。新服务前构造一份 | 服务中的 ticket 对象均为空、只在请求时 issue/consume；对象数量/构造时点不同。未调用清理 |
| 文件/日志/OS互斥汇总 | app 模块没有 FileHandler/basicConfig/open 日志句柄的顶层调用，也没有 Windows 命名 mutex；pending_delete 导入时创建模块级 RLock；uvicorn 运行时配置进程日志 | 依赖导入锁缓存一份；额外的 app 内锁如上 | 源码顶层调用清单由 AST 夹具固定，新增调用必须同步审计。不能把“未发现 app 顶层日志句柄”扩张为整个第三方栈绝无句柄 |

Store 兼容 UPDATE 的幂等性仅限测试的逻辑状态：首次把已完成任务的历史 cleanup 错误移到 warning 并清空 error；重复执行不再改变该行。没有把 SQLite 的物理事务效果当作相同。

## 验证范围

- `test_shadow_startup_shape.py`：顶层调用清单、稳定/变化配置读数、真实 Store 定义在临时库的逻辑幂等性、构造函数不启动线程。源代码经 AST 抽取，不导入真实 app。
- `shadow_launcher_process_integration.py`：明确启动 Windows PowerShell 5.1，使用临时假 app/包与随机回环端口；父子进程记录唯一 PID。标准错误先出现，服务仍能运行/正常退出；仅准备失败 75 回退一次；服务后非零、强制结束、端口占用均不回退。
- 没有安装、真实宿主预检、修改生产状态或恢复生产。启动形态差异必须留在后续 Claude 的安装风险核对里，不能因 CI 通过而自动消失。
