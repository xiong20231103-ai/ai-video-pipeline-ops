# V2-4：云端入口与登录准备（未切换）

本 PR 只准备代码与切换方案。云端默认 v2_default_enabled 缺省为关闭，旧入口保持；不修改家里 app.py、旧 static 文件、代理、数据库或队列开关，不执行部署。依赖 #37/#38 合并后由 Claude 审查。

## 路由与最小匿名资源

- /login：与 V2 同色板/字体/深浅主题的轻量 HTML 登录、邀请码注册，无新增依赖；不是另起一个 React bundle。
- 匿名仅能加载固定的 /login.js、/login-helpers.js、/login.css（以及原有 /auth/options）；不放开 /static。未登录 GET /static/v2/index.html 只返回登录303，不暴露HTML；V2 JS/CSS、旧页面、备份及业务接口仍401。
- /：未登录 303 到 /login?next=/；已登录且配置 v2_default_enabled **严格为 true** 时 303 到 /static/v2/index.html，否则返回原旧页。缺少构建时拒绝启用。
- /legacy 和 /static/index.html：登录后都返回注入原 cloud-readonly/commands/cleanup/backups 脚本的旧页。V2 的旧版链接改成 /static/index.html，在未修改的家里挂载也有效；云端必须经过该认证别名，不能漏掉队列包装。
- 会话过期：V2 将当前 pathname/search/hash 作为 next 回 /login；登录成功才跳回。登录页只允许 /、/legacy、/static/index.html、/static/v2/index.html，保留合法查询/锚点（浏览器保留的HTTP不可见锚点也恢复）；拒绝外站、双斜杠、反斜杠、控制字符、任意静态/API路径、路径归一化绕过及超长值。
- auth 后端参数、Origin/CSRF、限流、密码哈希、账号上限和安全 Cookie 不改。登录/注册共享提交锁、通用失败文本；成功清空表单。密码/邀请码不进 Storage、日志；仅主题偏好存储。

## 对照与检查

| 原实现 | 本次 |
|---|---|
| cloud/login.html 全部字段、注册折叠 | 同 ID/name/autocomplete/required/maxlength；密码注册 minlength=12；注册默认隐藏，查询明确开放才展示 |
| cloud/login.js auth/options 与 register/login | 同地址、方法、JSON字段、通用错误；新增同源页面回跳与共享防重复 |
| cloud/app.py 根页面注入脚本 | 提取 legacy_page，原路径默认不变，认证旧版别名复用 |
| V2 ReadClient 401 | /login 改为带当前页面 next；API请求、轮询和队列不改 |
| V2 旧版链接 / | 改为 /static/index.html，防根入口启用后循环回V2 |

参考沿用前序 shadcn/React Bits 设计 token 和系统字体；登录页不使用外部 CDN、字体或遥测。无新增依赖。原 368 条函数摘录按实际函数刷新，不复制文件开头；原22条延期项随本PR补实现证据。

## 验收分层

隔离：后端认证/静态保护/显式开关/旧包装/返回白名单；无头浏览器两主题四尺寸，登录成功、失败、邀请码注册、双提交、注册关闭/查询失败、主题、返回目标、凭据不持久化、CSP与控制台。所有HTTP拦截，密码和邀请码均合成。完整业务测试在worktree隔离运行。

未验证：真实生产批次试用、真实影子零差异、切换验收、真实账号登录及部署。本PR没有把它们记成通过。

## 由用户和 Claude 执行的切换门禁及回退

1. #37/#38及本PR通过审查；用户在独立V2入口完成真实生产批次试用并确认切换方案。当前SPC德语暂停不作测试对象，不触发任何业务写操作。
2. 由部署方先备份当前云端 release 链接、systemd unit/drop-in、配置和静态目录到仅root可读的 /root/ops-v2-entry-<UTC时间>/。不显示配置内容。在其中生成 rollback.sh，固定已核实的备份路径：恢复原release/配置并重启**云端** ops-console。部署前交付实际的一条命令 sudo /root/ops-v2-entry-<实际时间>/rollback.sh；此处路径是方案占位，当前未创建服务器备份，不能冒称已有可运行命令。
3. 先以开关关闭部署，在真实云端核对登录/注册、匿名保护、V2、旧页全部只读检查；通知仍启用、cleanup仍关闭、无leased/sent/unknown。不手动发送日报。
4. 用户批准后 Claude 设置唯一开关 v2_default_enabled=true，重启云端服务；家里默认入口不变、不重启家里任何程序。核对根跳转、401回跳、旧入口及业务只读状态。
5. 任一异常执行上述固定回滚命令。紧急使用 /legacy 返回旧页，仍经过同一云端队列保护。旧页至少保留两周，验收未完成不删除。此处与后续R6下线app.py完全分开；R6仍需用户另行确认。

本轮不修改生产配置、不改 tailscale serve/Funnel/防火墙，也不自行打开 cleanup 或恢复SPC德语。
