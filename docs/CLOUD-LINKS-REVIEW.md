# PR #63 第二轮审查简报（2026-10-24）

## 本轮范围

按Claude意见，将PR #63限定为“云端保存 + 只读查看”。
只保留独立证据库、ingest/listing/shots/page四个路由、只读页面、清理/备份及待安装timer。
移除decide/changes方法、远程操作表的创建、link_delivery.py、写路由和写操作测试。
原有revision字段保留为兼容字段，不产生任何决定或动作。

实验功能及已改为unittest的对应测试保存在独立分支：
https://github.com/xiong20231103-ai/ai-video-pipeline-ops/tree/draft/cloud-link-actions

该分支保持草稿，不合并。批次配额、两地归属、日期语义、未知结果对账、历史截图及真实跨地/WebChat验收
六个阻断项解决前，不将远程确认、动作流、递交纳入main。公司端PR #1本轮不部署。

## 修复和验证

- 同序号重试仅补缺图，不回退状态；已有截图不可被相同或更低序号覆盖。
- pending截图在40天后及容量压力下仍保留；已处理图优先清理。
- 未进入审核记录15天后只清图，链接和原始审核状态保留。
- 容量拒收截图后仍接收链接/状态，并持久化页面告警；恢复后可补图。
- 测试由pytest函数改成unittest.TestCase，不增加pytest依赖。
- 只读分支16项新增测试使用仓库tools/run_isolated_tests.py运行通过。
- 全套隔离回归运行837项，结果OK（1项跳过），其中包含新增只读测试；不是837项另加16项。
- 独立浏览器应加载4张图，实际加载4张，刷新后仍4张；5条历史链接保留，confirmed筛选3条。
  这是合成数据的云端查看页验证，不是真实WebChat验收。

可复现：设置OPS_ISOLATED_PATTERN为test_link*.py后运行python -B tools/run_isolated_tests.py；
不设置该变量则运行CI相同的全套测试。Windows环境需要先缓存platform.platform()时，
可以用python -c调用platform.platform()后runpy执行同一个隔离入口，禁止生产I/O的审计钩子不变。

## 部署边界

单独的部署前清单：docs/link-evidence-deployment-checklist.md。
已列环境变量名（无值）、目录权限、原service需追加的ReadWritePaths、维护任务和准确回滚边界。
这次只改隔离Git副本，没有安装、重启、迁移或修改生产目录。
必须先经Claude再次审查，且用户明确说“部署”，才执行部署。
