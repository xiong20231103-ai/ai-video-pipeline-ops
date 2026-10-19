# M2a：命令队列、HTTPS 递交与结果不明

以方案 §11 和审查意见为验收依据。云端配置、命令台账只在云端；代理只保留发送前/发送中证据和未确认回执，云端确认后清除本地正文，保留最小去重凭据。没有修改家里 app.py。

## 部署门禁

云端 `command_queue_enabled=true` 仍不足以执行。必须由已部署代理主动报告执行协议版本及固定 execution.db 身份，且心跳在线、引擎健康；旧代理或缺少 command-settings.json 的新代理仍只采集 GET。execution.db 身份变化会暂停云端下发，禁止把台账丢失当作新代理自动接管。

家里新代码只能由 Claude 审查后部署到独立 E:\Backup\ops-agent，不合并/改生产目录，不重启 Dashboard、工作台、接收器，不安装包。沿用原任务名 OpsConsoleReadonlyAgent 与任务所有权标记；是否执行以能力心跳和非秘密开关为准。新开关由 Claude 在该目录用既有 Python 执行 `python -B -m agent.execution enable`；不需要输入或重读令牌。关闭用 `disable`，只查元数据用 `status`。维护/在途期间拒绝切换。

安全继续还要求云端 H3 部署标记、摘要最近取数及实际扫描年龄合计不超过60秒，并匹配 batchId/taskId/attemptId；任何字段缺失、过期或目标变化都不能发送。发送给旧 Dashboard 时保留 expectedTarget 和同一个 clientRequestId，旧 Dashboard 在锁内作最终409核验。本模块不替换 RecoveryControl。

## 命令协议

- 控制台 POST 必须有登录、Origin、CSRF 和稳定 X-Client-Request-ID；请求内容规范化后摘要不同而ID相同返回409。
- 排队最多100条，发送前有效期最多300秒；仅一个租约/写通道。领取租约60秒，只有发送许可成功后才能调用家里，且本地先用 SQLite FULL 同步持久化 sent。
- 最多一次家里 POST；HTTP超时、截断、连接异常、发送后进程重启都进入结果不明，不能自动重发。云端许可后90秒未收到回执也进入 unknown，不回队列。迟到的确定 HTTP 回执可以按原租约对账。
- 本地只重试上传同一回执；上传确认后清除正文。只有未拿到发送许可的租约可以重新领取，旧租约结果不能覆盖新租约。
- 只保证云队列发送前的撤销/过期。已交家里不能保证中止；结果不明会阻止下一条下发，需核实家里原请求已停止及实际业务结果，填写依据并输入 CONFIRMED_HOME_REQUEST_STOPPED，原命令也不会重试。
- 浏览器保存的只有请求ID、摘要、路径、状态和家里命令ID，没有输入正文。刷新或回包丢失后 GET 查询原编号；撤销请求编号有持久墓碑，拒绝晚到的原POST。终结后必须明确“结束本次回执，允许新操作”，才能让相同输入成为新意图。
- 202不会传给旧业务处理器；创建/补链输入在等待时保留，只有拿到原业务HTTP响应才继续原处理器。云端队列状态、HTTP回执和业务完成分开。安全继续跟踪具体家里 commandId，避免跨设备 current 指针变化；旧缓存的其他命令不能覆盖本次结果。仅有人查看且业务仍在途时，状态键每5秒按需刷新，终结后回到普通缓存节奏。上传/历史核验沿用原业务状态查询。家里HTTP写请求进行中，独立心跳报告引擎忙，不把它误报为家里离线。
- 严格CSP不放宽；云端把原内联任务按钮改为受控委托事件。家里直接访问仍沿用原逻辑。

本期允许：建任务、补链、开始、撤回、安全继续、上传重扫/历史核验、递交器 validate/batches（及白名单中的普通对账/预览）。清理、测试重置和旧版 continue-current 写路径不开放；M3再做清理异步兼容。

## HTTPS 递交器

家里代理调用8766必须使用127.0.0.1：现有 task_receiver.py 的 _require_sender_permission 只对回环免令牌，Tailnet写入即使未配置令牌也会403。代理就在家里这台电脑运行，因此遵守现有回环合同，不读取旧接收器令牌、不改接收器鉴权、不放宽网络规则。8765沿用既有固定引擎地址。

工作台仓库独立PR。仅 https://ops.tail830b6f.ts.net 一个入口，不新增端口，不启用Funnel。递交器不发送登录密码或代理令牌，Serve已认证的Tailnet入口限大小/速率/队列；未登录仅 health、validate、batches、结果查询。状态缓存接口仍需登录。

云端最多等25秒，有家里回执即返回原状态码/正文；否则返回“云端已收件”及查询ID。收件回包丢失，可凭稳定请求ID查询。带令牌的旧HTTP家里递交兼容路径不改变，HTTPS路径不发送该令牌，不走系统代理、不跟随重定向、不跳过证书验证。

若递交器首次POST回包丢失且仍查不到记录，可在已登录云端命令面板输入原请求ID，撤销发送前请求；此操作为登录+CSRF保护，并限定同一Tailnet身份。墓碑生效后递交器查询为cancelled，可结束旧回执；不以404自行推断“从未收到”并重发。

## 暂停、更新、回滚

云上以服务用户运行：

```sh
cd /opt/ops-console/current
sudo -u ops-console env PYTHONPATH="$PWD" .venv/bin/python -B -m cloud.command_admin pause --wait 60
# drained=true 才能更新/回滚家里代理；unknown必须人工核对，不能强行清除。
sudo -u ops-console env PYTHONPATH="$PWD" .venv/bin/python -B -m cloud.command_admin status
# 审查后明确恢复领取（不会重发原 unknown）：
sudo -u ops-console env PYTHONPATH="$PWD" .venv/bin/python -B -m cloud.command_admin resume --empty-only
```

云端 deploy/m2a-upgrade.sh 先保存代码指针、配置、SQLite在线快照、服务/Serve/UFW/IPv4/IPv6规则，生成一条回滚命令，再切换。回滚先暂停领取、撤销尚未领取项并等在途清点通过；unknown时会拒绝切换，必须人工对账。保留新增台账，不回放旧DB，不恢复/放宽防火墙，不改Serve，不碰家里。家里源更新器在 sending/awaiting_ack/unknown 时拒绝停止替换，正文/令牌配置不进入代码包。

首次部署/激活只用 `resume --empty-only`：检查队列为空与解除暂停处于同一事务，避免激活时带出已有业务命令。正常恢复既有排队意图的普通 `resume` 也必须先清点在途。

旧 Dashboard 直连入口在并行期约定只看不点；串行代理不意味着旧入口具有服务端全局写门禁。

## 验证边界

`tools/run_isolated_tests.py` 全部 OPS 测试禁止生产网络/进程和生产写入；`tests/command_transport_integration.py` 用真正127.0.0.1临时HTTP服务及SQLite验证各命令族、422原字节、响应截断、丢回执和重启，不连接100.92.17.9。页面测试 `tests/command_ui_fixture.cjs` 为独立headless浏览器、所有网络拦截的合成数据；CI临时目录安装固定版本Playwright并使用现有Edge，家里不安装任何依赖。当前SPC德语是用户主动暂停，真实生产命令验收必须另选受控测试任务，不能用安全继续恢复它。
