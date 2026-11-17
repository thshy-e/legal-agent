# Scripts

本目录用于放置项目维护、调试和一次性验证脚本。正式运行入口仍保留在根目录：

- `start_server.py`：启动 FastAPI + 前端静态资源服务。
- `build_db.py`：初始化或重建法条/案例知识库。

建议只把可复用、可解释的脚本提交到 GitHub。临时诊断脚本、日志输出和个人本地实验文件不要提交。

- `run_case_evaluation.py`：冻结工程集与真实Qwen对照；未配置密钥明确not_run。
- `legal_review.py export/summarize`：导出真实产物的人工复核CSV，校验填写并单列严重错误；见[操作说明](../docs/evaluation/casework_v2/LEGAL_REVIEW_WORKFLOW.md)。
- `run_live_casework_smoke.py`：真实角色运行冻结欠薪四阶段及过期确认；不覆盖既有报告，重复次数预先固定。
- `probe_truncated_completion.py --output <新的JSON路径>`：一次非法律、16输出token上限的真实Qwen诊断，验证SDK截断异常的实际模型、结束原因及用量记录。无SDK重试，不计案件通过率；unknown用量不推定为零，原始调用仍记failed。
- `run_live_casework_scenarios.py --output 路径 --workers 3`：冻结10个公开合成场景，独立案件并发；预期结果不传给角色，金额/边界与角色完成均核对，规则提前终止单列。不是盲测或法律准确率，输出必须使用新目录。

# 引用修订受控探针

`python scripts/run_live_citation_revision.py --output <新的JSON路径>`：回放v13 S04中已保存的首轮Judge/Review产物，然后真实调用Judge修订与Review复审。回放产物先校验事实、金额、法源及引用片段；回放不计新模型调用。此探针用于验证指定引用失败的反馈闭环，不能当作全程新调用、独立盲测或法律准确率。新调用用量及节点事件保存于报告，禁止覆盖旧证据。完整新调用的扩展场景继续使用run_live_casework_scenarios.py。


## v16自然咨询抽样

`python scripts/run_live_conversation.py --output <新的json路径>` 使用合成输入和临时会话，记录实际 Qwen 模型、用量、耗时及完整输出。最多一次格式纠正，不覆盖已有证据；仅为多轮工程观察，不作为法律准确率。

### v17前端验证

`node --test tests/frontend_workspace.test.cjs`运行6项前端控制器行为测试。`demo_frontend_v17.js`是供Playwright CLI run-code读取的实际后端规则演示，非独立Node程序；调用命令、截图和真人待办见`docs/evaluation/frontend_v17/FINDINGS.md`。

### v18本地研发验证

当前`node --test tests/frontend_workspace.test.cjs`为13项行为测试。`check_frontend_v18.js`先执行普通聊天、真实法条、三步输入、保存、确认、修订和三档布局验证；`check_frontend_v18_failures.js`随后验证真实409、显式同步、历史只读、迟到响应隔离、跨境阻断及地域边界。两者使用合成数据和实际后端；网络中断为主动注入，实时进度检查只延迟真实事件传输，不替换内容。第一份脚本包含一次解释性追问，可能产生真实Qwen调用。

启动127.0.0.1:18080规则案件服务、打开独立浏览器会话后依次执行：

```powershell
npx --yes --package @playwright/cli playwright-cli -s=labor-v18 open http://127.0.0.1:18080/ --headed
npx --yes --package @playwright/cli playwright-cli -s=labor-v18 run-code --filename scripts/check_frontend_v18.js
npx --yes --package @playwright/cli playwright-cli -s=labor-v18 run-code --filename scripts/check_frontend_v18_failures.js
```

CLI对话保护可能提前结束控制台输出；最终成功报告分别保存在测试浏览器localStorage的`laborhub_frontend_v18_check`与`laborhub_frontend_v18_failure_check`中。使用`--raw eval '() => JSON.parse(localStorage.getItem("laborhub_frontend_v18_check"))'`提取，并检查返回非null。既有v17演示脚本不适配新增引导与多处复制按钮，v18使用上面两份脚本。本轮不运行打包脚本。
