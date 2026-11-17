# v17 前端重设计交付与验收（2026-10-27）

前端版本 frontend-20261027-v17；后端沿用 casework-20261026-v16 / conversation-20261026-v16，公共API与法律计算规则不变。主题为明亮白底、深蓝文字与青绿操作。源码使用现有HTML/CSS/JavaScript，未引入新框架。

## 已完成的行为

统一聊天、案件核对、法律依据及文书阅读。普通对话不显示案件长表单；来源按消息绑定，实际引用可打开对应原文。最新案件集中核对，历史版本只读。案件阶段与展开后的协同节点来自后端实际事件，不生成模型内部推理或模拟进度。

事实编辑在本机会话保存为“尚未应用”；切换会话可继续编辑、放弃或保存重算。保存与确认分开。修改工资后，旧金额和草稿失效，重新确认才可复制新版草稿。过期版本409标记需要同步，禁止继续确认和复制，显式重新分析不会自动确认或生成文书。

前端请求绑定原会话，切换后迟到的真实后端结果不覆盖新会话。保留旧浏览器存储格式读取。Markdown依赖按固定版本存放在frontend/vendor，保留上游许可头和来源哈希；加载失败时回退到转义纯文本。

## 验证

- Python回归146项通过；公开冻结工程集60/60，见[逐案结果](engineering/engineering_results.json)。这些是工程检查，不是法律准确率。
- 新增6项Node行为回归：分块SSE解析、历史来源绑定、迟到案件响应隔离、409不自动重试确认、普通问答失败保留有效案件、刷新中断后同步保护。运行 `node --test tests/frontend_workspace.test.cjs`。
- 实际后端浏览器验证：7000.10元确认草稿、应付工资修订后的8000.10元新稿、旧稿失效、未保存编辑取消/保存切换、真实服务端外部修订引发409及同步恢复、刷新历史恢复。
- 实际响应延迟测试通过：代理先取得真实后端结果，再暂停向浏览器交付；此时切换新会话，释放后结果仍归原会话。未替换结果内容。
- 一次浏览器网络中断为主动注入故障，确认普通问答失败不改变已确认案件。控制台累计2条预期网络错误：一次真实409、一次主动ERR_FAILED；未将它们记录为0错误或真实模型失败。
- 1440×1000桌面三栏、1024×900抽屉、390×844全屏详情已检查；未发现横向页面溢出。Escape、焦点返回和背景inert通过；允许页面缩放。桌面Chromium窄屏不能证明实体手机软键盘体验，仍待实机测试。
- [真实三轮聊天](live_chat.json)完成“试用期—转正才签—为何保留记录”，回答与实际来源已保存。仅有浏览器交付结果，未新增完整模型用量遥测，不推算token或调用成本；未进行法律专家评分。原文仍含可能过度概括的法律表达，不能因status=completed认定法律正确。

完整浏览器摘要见[browser.json](browser.json)。验证中有选择器或等待条件引起的脚本重试，修正测试后继续；这些调试未被当作应用成功结果。后端146项测试及源码边界保持原有结论。

## 调研采用依据

本轮参考公开产品页面与帮助文档，没有登录付费产品或核验其宣传准确率。

| 来源 | 采用的交互 | 本项目的取舍 |
| --- | --- | --- |
| [Harvey官方指南](https://help.harvey.ai/articles/getting-started-with-harvey) | 问答、来源及历史关联 | 按回答打开依据，不复制专业工具的全部导航 |
| [CoCounsel官方介绍](https://www.thomsonreuters.com/en/press-releases/2025/august/thomson-reuters-launches-cocounsel-legal-transforming-legal-work-with-agentic-ai-and-deep-research) | 有引导、有人工核对的任务流程 | 用用户阶段和真实节点解释当前进度 |
| [Legora Editor](https://legora.com/product/editor) | 分析转入文书工作环境 | 草稿独立阅读，仅复制Markdown，不宣称富文本或Word导出 |
| [iCourt官方产品页](https://www.icourt.cc/) | 以法律任务组织入口 | 使用欠薪、解除、法条、仲裁材料四类示例，点击后由用户发送 |
| [通义法睿官方文档](https://help.aliyun.com/zh/model-studio/tongyi-farui) | 区分咨询、检索及文书任务 | 对话和案件使用不同展示，继续由后台受控路由 |

## 截图、演示与待办

改版前：output/playwright/conversation-v16-desktop.png与conversation-v16-mobile.png。改版后：同目录frontend-v17-home-desktop.png、source-desktop.png、draft-desktop.png、revised-desktop.png、tablet.png、mobile-home.png、mobile-draft.png及conversation.png。操作录屏frontend-v17-demo.webm为未经配音剪辑的工程演示，使用合成输入和真实后端；未用于声称用户效果。

重现规则演示：先启动本地服务、打开Playwright CLI会话，再执行以下PowerShell（剪掉脚本注释并合为一行，避免Windows原生命令多行参数问题）：

```powershell
$frontendDemoCode=(Get-Content scripts/demo_frontend_v17.js | Where-Object {$_ -notmatch '^\s*//'}) -join ' '
npx --yes --package @playwright/cli playwright-cli -s=labor-v17 run-code $frontendDemoCode
```

六位非计算机专业同学的首次使用验证尚未开展，已提供[任务与记录表](USABILITY_TEST.md)，不冒充真人测试。实体手机键盘与放大也待现场验证。广深补偿封顶口径、法律专家复核与独立盲测沿用原有待办。交付包保留v16回退，不声称已达到比赛最终冻结条件。
