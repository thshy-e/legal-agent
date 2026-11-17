# 劳法智枢 Legal AI Agent

面向劳动者及法律援助人员的劳动争议辅助系统。使用全国基础法源、广东规则与广深城市资料，通过事实澄清、法源检索、分请求分析、规则计算、用户确认和审查，整理依据可追溯、金额可复核的维权准备草稿。

2026-10-28 本地前端研发版为 v18：真实协同进度外显、审查问题分级、地域覆盖说明、三步事实核对、引用返回与材料准备摘要。后台继续使用 v16 自然咨询与案件流程；本轮不打包，已有 v17/v16 包保留。启动方式及已知限制见[工程交付说明](docs/PROJECT_HANDOFF.md)。学校申报材料与新增配音视频暂缓。

2026-10-25 升级详见 [交付说明](docs/GBA_CASEWORK_IMPLEMENTATION.md)。首期案件协同聚焦经济补偿、违法解除赔偿、代通知金及欠薪；其他七个大湾区内地城市仅覆盖全国和广东规则，港澳实际履行交专业复核。

## 运行

```powershell
.\venv\Scripts\python.exe build_db.py --activate
$env:CASE_MODEL_ENABLED="0"
.\venv\Scripts\python.exe start_server.py
```

访问 <http://localhost:8000>。已有环境可直接运行；新环境使用 `python -m venv venv` 后执行 `pip install -r requirements.txt`。

规则模式无需模型密钥，可完整演示欠薪事实补充、条件测算、确认、草稿和修订。启用模型：配置 `.env` 中的 `DASHSCOPE_API_KEY`、匹配地域/工作空间的 `DASHSCOPE_BASE_URL` 与 `CASE_MODEL_ENABLED=1` 后重启。Judge和Doc使用Qwen-plus；可设置`CASE_REVIEW_MODEL=qwen3.8-max`独立增强审查。v14增加引用分析的一次修订和独立复审，保留前后记录。历史v15补充精确字段纠正和SDK截断异常的真实用量记录，仍保留失败及一次纠正上限。冻结欠薪四阶段单次复测通过，扩展10场景通过9项严格工程预期，剩余1项90秒审查超时并停止出稿。另以一次故意限制16输出token的非法律诊断验证截断用量保存，失败状态保持，不计入案件通过率。这是有限工程验收，尚无法律准确率或普遍稳定性结论。默认演示仍为规则模式，详见[真实验收记录](docs/evaluation/casework_v2/LIVE_SCENARIO_FINDINGS.md)。

## 自然咨询与案件工作区

默认直接聊天，普通问题不再套用完整报告；来源折叠查看。“那试用期呢”“第二点什么意思”读取最近六轮实际问答，不能确定指代时先澄清。明确要求按本人情况计算、分析或生成文书才进入案件核对，解释材料用途不修改案件。工作区保留最新状态，旧卡片标注历史并停止操作。

自然法律解释使用 Qwen-plus（40秒超时，无传输重试，格式/引用最多纠正一次），独立于 CASE_MODEL_ENABLED；后者只控制案件图的模型增强。寒暄、精确法条和规则案件仍可无模型运行。完整测试与真实抽样边界见 [v16验收](docs/evaluation/conversation_v16/FINDINGS.md)。

## v18工作台

新案件按“基本情况—争议与工资—材料持有”分步填写，可切换完整表单；切换和刷新保留本机编辑，明确保存才重新分析。审查问题按处理优先级展示，不表示败诉风险。地域覆盖与本轮实际检索来源分开。点击来源中的返回位置可定位原回答实际引用，未建立引用对应关系时如实说明。

只有当前有效、版本一致的确认草稿展示“材料准备结果”和内部一致性检查状态。编辑事实、案件操作、409或中断待同步时暂停旧稿使用；摘要列出已确认请求、金额、待补材料和主体占位，不表示案件已办结。

验证：146项Python、13项前端状态测试、60案工程核验通过；浏览器完整流程32项、异常与边界19项检查通过。详见[v18研发验证](docs/evaluation/frontend_v18/FINDINGS.md)。这不是法律准确率或六人用户研究，实体手机软键盘仍待测试。

### v17重设计基础（保留）

普通咨询保持自然聊天，点击引用打开对应回答的法律依据；当前案件与Markdown草稿在独立详情区核对。1440px使用三栏，1024px使用抽屉，390px使用全屏详情。事实修改先标记尚未应用，保存后重算、再次确认；历史版本只读，过期409要求同步。现有Markdown渲染库已固定版本并置于本地，缺失时回退纯文本。

新增6项前端行为回归：`node --test tests/frontend_workspace.test.cjs`。截图、真实后端演示、三轮问答及待完成真人验证见[v17验收](docs/evaluation/frontend_v17/FINDINGS.md)。六位同学测试及实体手机软键盘验证仍待实际开展。

## 核心机制

- LangGraph 受控协同：接待 → QA 检索 → Judge 分请求分析 → Decimal 计算 → Review 审查 → 用户确认 → Doc 草稿 → 文书一致性审查。
- 所有角色读取同一案件状态。事实有来源与确认标记，材料持有和证据真实性分开；用户主张不直接转成违法认定。
- 按地域、日期筛选法源，精确定位法名条号，保留深圳及广东历史版本与部分废止条款；缺失地方参数不挪用他市数据。
- 修改工资、日期、地域或知识版本后，下游金额、确认和文书失效，过期确认返回 409。
- 文书消费已确认计算对象；停止从生成文字提取金额。未通过关键审查不能交付草稿；只输出可复制 Markdown，不自动提交仲裁。
- 页面显示真实节点进度、事实修订卡、原文与官方来源、请求选择和材料清单，不展示固定胜诉率或证据分数。

**当前限制：** 广深经济补偿封顶适用口径尚待专业核验，因此运行库中的 N/2N 只保留公式、阻止确认；欠薪链路可完整运行。2008 年前工龄、特殊用工、跨市适用未澄清等交专业复核。官方案例及工程测试尚未取得专家背书。详见交付说明，不将本系统输出视为正式法律意见。

## 数据与索引

唯一入口为 `data/legal_sources/manifest.json`：12 份法规版本、2 份指引、18 个官方出处案例参考（含新增 6 份深圳普通仲裁裁决），共 748 条检索记录；6 个地域参数中 2 个封顶参数为 pending。索引独立构建、原子切换并保留上版回退，旧 Chroma 不混入现行答案。

```powershell
.\venv\Scripts\python.exe build_db.py              # 构建候选并验收
.\venv\Scripts\python.exe build_db.py --activate   # 切换并在之后重启服务
.\venv\Scripts\python.exe build_db.py --rollback   # 回退到上一清单索引
```

默认使用词项检索；可用 `--embeddings --activate` 构建向量，再设置 `LEGAL_VECTOR_SEARCH=1` 启用过滤后的融合检索。真实构建已取得748条1024维向量，并通过8项精确检索及地域时间边界检查；这不代表语义检索准确率已经评定。向量接口随聊天兼容地址派生匹配的原生地址，也可单独配置 `DASHSCOPE_EMBEDDING_BASE_URL`。此可选路径需要 DashScope 密钥。旧 `--init/--force` 参数不再使用。

## 验证

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe scripts/run_case_evaluation.py --engineering
.\venv\Scripts\python.exe scripts/run_case_evaluation.py --live
```

60 个冻结任务是公开工程验证集，分组为解除 20、欠薪 10、地域版本 10、多轮修正 10、否定缺失 10。当前使用v2，仅更正v1三个零余额任务的确认预期，输入和金额预期保持不变；v1原集及新行为下57/60的对照报告保留。工程通过率不能替代法律准确率。实际逐案产物见 `docs/evaluation/casework_v2/`；缺密钥时三组模型实验明确为 `not_run`。专家复核及独立盲测尚未完成。

真实实验共180组、360次成功调用；单Agent、协同无审查、协同有审查分别有15、2、8组自动标记，需逐案人工判断。不能把无自动标记比例称为法律准确率，也不能声称增加审查必然改善效果。详见[真实实验记录](docs/evaluation/casework_v2/MEASURED_MODEL_RESULTS.md)。此前公共接口401、40秒超时及未约束格式试跑均另存，未混入本批结果。续跑同时校验数据、知识、协议、采样和Base URL；401/403仍会停止后续请求。

## 入口与结构

- [详细技术文档与核心创新](docs/project/劳法智枢技术架构与核心创新说明.md)：当前实现、架构图、数据模型、角色权限、创新证据和实验边界；同目录有Word阅读版。

- [API 契约](docs/API.md)：原聊天接口与案件字段、409 和 SSE。
- [架构](docs/ARCHITECTURE.md)：案件状态、角色职责和失效机制。
- [角色上下文契约](docs/ROLE_CONTEXT_CONTRACT.md)：各角色读取范围、数据权限与真实复测边界。
- [演示脚本](docs/DEMO_SCRIPT.md)：无需密钥的欠薪修订闭环。
- [比赛技术报告初稿](docs/COMPETITION_TECHNICAL_REPORT.md)：机制、验证证据与尚待完成事项。
- [升级方案交付对照](docs/CONTEST_DELIVERY_STATUS.md)：逐项完成情况与提交前缺口。
- [人工法律复核](docs/evaluation/casework_v2/LEGAL_REVIEW_WORKFLOW.md)：60份规则产物、180份真实模型产物、CSV评分及校验汇总。
- [页面录屏初稿](output/playwright/README.md)：合成输入、真实后端的欠薪确认与修订演示。
- `legal_ai_agent/casework/`：状态、提取、法源、计算、角色与 LangGraph。
- `frontend/casework.js`：事实卡、确认和来源查看。
- `scripts/collect_official_sources.py`、`prepare_legal_manifest.py`：快照及清单准备，不自动认定法源适用。
- `scripts/run_case_evaluation.py`：工程验证与可续跑模型对照。

JSON 会话存储仅支持本机单进程演示；多实例须改为事务数据库。不提交 `.env`、私有会话、索引、Chroma、venv；详见 [上传检查](docs/GITHUB_CHECKLIST.md)。

当前工程回归146项、公开任务60/60。新增[真实角色扩展验收](docs/evaluation/casework_v2/LIVE_SCENARIO_FINDINGS.md)保留全部失败、规则提前终止及用量，不能将工程通过率作为法律准确率。
