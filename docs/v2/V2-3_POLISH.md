# V2-3 动效与打磨

仅前端；不改变接口、正文、轮询间隔、写入门禁或默认入口。用户明确将未登录登录/注册留V2-4，现有/login和401跳转不变。

## GitHub源码参考与本地实现

固定参考React Bits提交 `e12c22192ac7b4b452c5e2feb9b586d74765d696`：

| 参考源码 | 本地实现 | 适配与边界 |
|---|---|---|
| [BlurText](https://github.com/DavidHDev/react-bits/blob/e12c22192ac7b4b452c5e2feb9b586d74765d696/src/content/TextAnimations/BlurText/BlurText.jsx) | frontend-v2/src/components/react-bits/Motion.tsx | 保留首次模糊/透明/位移入场，使用原生WAAPI；不引入上游motion依赖，不复制分词/复杂交互选项 |
| [FadeContent](https://github.com/DavidHDev/react-bits/blob/e12c22192ac7b4b452c5e2feb9b586d74765d696/src/content/Animations/FadeContent/FadeContent.jsx) | frontend-v2/src/components/react-bits/Motion.tsx | 保留IntersectionObserver首次可见入场、清理observer；按稳定面板标题记已完成，仅首次，刷新不重播 |
| [CountUp](https://github.com/DavidHDev/react-bits/blob/e12c22192ac7b4b452c5e2feb9b586d74765d696/src/content/TextAnimations/CountUp/CountUp.jsx) | frontend-v2/src/components/react-bits/Motion.tsx | 保留from/to、当前值转下一目标、格式/小数位及仅值变时过渡；使用原生requestAnimationFrame，不引入滚轮数字或motion依赖 |

这些是按本项目选用行为做的原生API适配，不是上游完整组件的逐字复制。已有SpotlightCard保留，所有资产本地打包。React Bits的许可为MIT + Commons Clause，原许可继续随static/v2/licenses/react-bits.LICENSE.md分发；shadcn组件沿用既有固定来源和MIT许可。无新增依赖。

## 改动

- 页面标题BlurText、面板FadeContent、资源数字CountUp；正常5秒数据刷新未变化时不启动动画。数字保留原格式和精度，读屏及data-legacy使用原始最终文本，视觉层aria-hidden。
- 减少动态效果时不启动WAAPI/数值RAF；卸载清理动画、observer和帧。React StrictMode取消的初次动画不误记为已播放。
- 复用shadcn Skeleton；空状态加轻量符号。Toast只在用户操作反馈发生变化时显示一条，5秒关闭/可手动关，不积累队列，不替代原确认弹窗或错误正文。
- 动效包装层显式可收缩，手机不增加横向溢出；保留半透明降级与主题。

## 验证

219项前端测试（新增6项动效/生命周期和3项完整范围校验），typecheck/lint通过；361项隔离业务测试通过（1跳过）。双模式×减少动态效果开/关×四尺寸、深浅主题：32截图与16组计数检查；未变化5秒刷新前后WAAPI/RAF计数完全一致，减少动态效果计数均0，无控制台/CSP错误。

10分钟真实轮询（非假时钟）观察由scripts/memory-browser-check.cjs执行；每分钟CDP显式GC后取JS heap/DOM/listeners，页面每5秒轮询及后台其它原GET保持原间隔。采用1MiB附加合成正文，所有网络拦截，禁止任何POST。原始JSON及JSONL随交付保存。阈值只用于隔离回归：第3分钟后堆趋势<256KiB/分钟、净增长<4MiB、DOM新增<=100、监听器新增<=10；最终数值和局限必须如实记录，不将十分钟当作长期生产证明。

未验证真实生产、完整批次影子、默认切换或家里部署。#36安全继续必须由用户亲自确认才可合并。回滚revert本PR及静态产物；旧页面保留。

## 十分钟原始观察结果

- 时长 603866 ms；559 个全拦截GET，模拟正文附加1MiB；采样时活动HTTP数均0。
- 第3分钟至末次GC后堆：5.565 → 5.713 MiB，净变化 0.148 MiB；回归斜率 27.83 KiB/分钟。不是“零增长”，在所列回归容差内，不能据十分钟证明永无泄漏。
- DOM：907 → 907；事件监听器：165 → 165；documents=1，未随轮询累积。
- 首轮未等请求空闲的样本也保留（600291ms，末端堆跳约1MiB），不隐藏；复采等待请求和页面更新空闲后再GC，避免把大正文在途分配当长期占用。
- 在相同核心轮询基础上，后续固定cloud-sources/system-health动效标识另有离线心跳秒数变化回归，避免标题变化重播；不改采集、缓存、命令或轮询行为。

原始证据保存在本次交付的implementation-tools/v2-polish-evidence/quiescent/memory-result.json、memory-observation.jsonl；实际代码提供scripts/memory-browser-check.cjs供复验。单测219项、双模式减少动态效果32截图、额外离线2截图、全部操作浏览器回归均通过。仅密码HTTP400与原requestId收件前404为预期负例并单列。

后续集成#36摘要目标同步回归（双模式old→new→null）：219前端测试通过。只同步已被taskBoxes.selected引用的当前任务箱，不新增轮询、定时器或数据副本；十分钟核心轮询原始样本保留，另对该目标引用变化定向回归。
