# v3 启动回退与禁用状态预检

本提交承接捕获核心 PR #58，仅提供可审查的启动和预检代码。**不安装、不运行真实宿主预检、不启用旁听、不恢复生产。**

## 启动路径

VBS、看门狗、健康判断保持原样。`launch.ps1` 仅在独立控制目录已有显式设置时加载 `deploy/shadow-launch.ps1`；无设置直接执行原 `app.py`。设置禁用且非预检模式也走原入口。

可选分支在新 Python 进程中验证提交号、包清单 SHA256、逐文件 SHA256、计划 SHA256、路径非链接和大小限制。导入并使用原 `app.py` 的同一个 FastAPI 对象，地址、端口取原 CONFIG；不再通过字符串二次导入应用。

只有调用 serve 前的准备异常返回专用码 75，允许回到全新原 `app.py` 进程一次。调用 serve 后的异常、绑定失败、SystemExit 或 OS 强制结束都传递原非零结果，交由原看门狗处理，不再启动旧入口。设置/包的本地验证在尚未创建子进程时失败仍走原入口。异常原文、设置内容不进日志。祖先目录检查包括隐藏目录。

Windows PowerShell 5.1 的子进程调用不重定向 stderr，并在脚本块局部使用 Continue；stdout 送 Out-Host，避免污染返回码。LASTEXITCODE 不用局部变量遮蔽原生结果。SHA256 用框架 API，不依赖父 pwsh 的模块发现路径。

原入口与 bootstrap 的 CONFIG/Store 初始化次数不同；不能宣称启动形态无条件等价。完整清单与限制见 [启动形态审计](shadow-v3-startup-shape.md)。预检报告 startupShapeEquivalent=false，不因此获得安装资格。

## 禁用状态预检

`mode=preflight` 必须同时 `enabled=false`。预检在原宿主生命周期启动后，以宿主身份运行后台线程，不绑定 GET、不生成任何 HTTP 请求、不控制进程。

- 动态确认 8765 监听者为本宿主，取得 8766/18790 唯一监听者；代理 PID 只取公开运行状态。记录 PID、父 PID、镜像、参数、创建时间、启动用户名。缺字段、无权读取或参数涉及凭据，都标缺事实，不保存敏感参数或异常原文。
- 只读取明确列出的状态文件，读前后验证身份/大小/时间，超限或变化即失败；缺文件和错误的“明确不存在”声明进入报告。
- SQLite 只读连接在线备份到新 scratch，记录字节数和耗时，随后删除本次 scratch。控制、旧证据、新证据目录不能互相覆盖；旧证据也不能被采集。
- 仅输出一轮读取字节/耗时、数据库备份耗时、进程字段、缺失路径。`deduplicatedIncrementBytes` 和 `forecast12hBytes` 明确为空：单轮静态预检不能测真实变化率，也不证明 12 小时容量。
- 预检失败不阻断原生命周期，原健康路由仍可服务。报告固定 `installationPermitted=false`、`realShadowPassed=false`。

本次预检仍不是完整安装资格检查：目录/媒体实际增量、变化日志、总额度共享锁、独立回放空间和完整依赖闭包尚需接线验证。`observe` 模式故意拒绝启用并回退旧入口，防止有人用初步预检直接激活。

## 隔离验证与后续门禁

夹具覆盖源文件/计划篡改、启用预检冲突、导入路径恢复、原应用对象、原健康响应与生命周期、缺事实、只读 DB、隐私参数、旧证据保护、启动失败回退和成功时不重复启动；没有启动任何真实服务。

顺序仍为：Claude 审查合并 → 精确 Git 对象包与哈希 → 用户执行所需管理员操作 → `enabled=false` 真实宿主预检交 Claude → 补齐预算/接线后获准安装 → 实际 STOP 演练、旧 PID/启动时间不变 → Claude 复核 → 用户自行恢复生产。当前不能写“可以恢复生产”。

## Windows PowerShell 5.1 本地真实进程输出

显式执行 `powershell.exe`（非 pwsh），Python 父夹具创建隐藏进程，假应用、配置、端口均在独立临时环境中。强制结束前核对夹具 runId、PID、创建时间和准确命令路径，结束码原样传至父启动器；没有结束生产程序。

```text
Real process fixture host: Windows PowerShell 5.1.26100.9711
test_forced_child_termination_never_falls_back ... ok
test_occupied_port_never_falls_back ... ok
test_post_start_nonzero_propagates_without_legacy ... ok
test_preparation_failure_allows_exactly_one_legacy ... ok
test_stderr_then_normal_server_no_fallback_or_second_process ... ok
Ran 5 tests in 7.703s
OK
```

stderr 场景同时确认出现 `FIXTURE_STDERR_BEFORE_SERVER` 和 uvicorn `Started server process`，服务能监听并退出 0；仅记录一个 app-import、一个 serve-call，PID 相同，旧入口调用标记不存在。服务后退出码 23、被结束子进程的实际退出码、绑定失败 1 都不进入旧入口。CI 新增独立的同名真实进程步骤，内部再次要求 Windows PowerShell 版本 5.1。
