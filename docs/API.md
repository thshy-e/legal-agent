# API 契约（2026-10-26）

继续使用 `POST /api/chat` 和 `POST /api/chat/stream`；响应保留 `reply/answer/route/structured`。`workflow` 为 `consultation`（默认）或 `case`，未知值返回 422。旧 `preferred_mode/ui_mode/mode/force_mode` 字段兼容接收，新页面不发送强制模块；咨询统一使用自然问答，字段不能绕过案件确认。明确按本人情况计算、分析、修订或生成文书才进入案件流程；概念及解释性追问保留聊天。

## 自然对话（v16）

响应新增 `structured.presentation.kind`：普通聊天为 `conversation`，案件产物为 `case`。咨询的 `structured.sources` 为本轮校验后实际引用的法源对象，包含 id、title、article、version、url、original_text、地域与效力时间；前端折叠展示。咨询不再附带推断风险、材料、时间线和指标报告。`status` 可为 completed、clarification、retrieval_failed、model_failed、invalid_output。

有 session_id 时保存原问题和实际交付的完整回答，读取最近最多六轮、总计12000字符的上下文；旧摘要标注 legacy_summary，不还原原文。独立新问题不注入旧案工资或金额，追问才读取相关历史。缺少 session_id 的普通请求不读写共享默认会话。精确法条查询也记录进会话，可接着问“这一条是什么意思”。

案件内解释问题只读当前快照，不修改版本。明确的应付/实付工资修订只有在期间唯一时才重算；多期间或“工资改成9000”口径不明时先澄清，旧案件保持有效。结构化 facts、action 和 expected_case_version 保留原契约。

前端优先按 presentation.kind 渲染；旧消息有案件对象则保留案件卡，其他消息仅显示原正文。普通 SSE 在实际处理前发送 thinking，随后发送 route/structured/token/done；token 是已核验正文的传输片段，不是实时模型 token。只有案件节点运行才发送 task_started/task_completed。

## 普通法条咨询

```json
{"query":"劳动法第47条是什么？","session_id":"consult-demo","workflow":"consultation"}
```

精确法名条号使用清单检索，不注入前案。地方问题需补履行地和日期。普通风险/分析问答需要模型密钥，不能给未经依据的胜诉百分比。

## 案件分析与事实补充

案件协同必须提供独立 `session_id`。初次：

```json
{
  "workflow":"case",
  "session_id":"arrears-demo",
  "action":"analyze",
  "query":"没有考勤",
  "facts":{
    "workplace":"广州",
    "employer_city":"广州",
    "dispute_date":"2026-10-01",
    "wages":[{"start":"2026-09-01","end":"2026-09-30","due":"8000.10","paid":"1000"}]
  }
}
```

补充使用同一接口与 `facts` 部分对象，建议携带 `expected_case_version` 防止覆盖旧版本。`wages` 是完整期间列表替换，`evidence` 按材料名合并；不要发送文本金额公式。金额传十进制字符串，非有限值、负金额、欠薪期间重叠、无效日期和额外未知字段返回 422。`null` 可清除可选事实。

主要事实：`workplace/employer_city/dispute_date/start_date/end_date/initiator/termination_reason/termination_basis/monthly_average/previous_month_wage/article40_conditions/protected_status/written_notice_30/employment_type/actual_cross_border_work/cross_city_resolved`，主体信息和 `wages/evidence`。

- initiator：`employer/worker/mutual/unknown`。
- employment_status：`active/terminated/unknown`，仅记录用户陈述。明确的当前在职或已离职陈述可从query或wage_statement提取，并保留原句与来源；询问、假设及“没有离职”等表述不反向推断。结构化状态与陈述矛盾时要求澄清，旧确认和文书失效。
- termination_basis：`unknown/employer_agreement/worker_38/article_40/article_41/article_39/voluntary/illegal_claim`。illegal_claim 仅是主张，不是认定。
- evidence：材料名映射 `claimed_present/missing/unknown`；claimed_present 仅表示用户声称持有。
- 文本仅提及、询问、假设材料，或说明单位持有，不自动记作用户持有。文本与结构化材料按名称合并；同名结构化补充优先。`fact_sources["evidence.材料名"]` 记录逐项来源；矛盾陈述保存于 `fact_conflicts`，重试、JSON 重载不会解除阻断，须明确澄清。
- 工资口径：monthly_average 为解除前十二个月应得工资口径；previous_month_wage 为代通知金所需解除前一个月工资，两者不能自动视为相同。
- cross_city_resolved仅表示跨市事实已澄清，不能单独证明补偿参数的法律适用。履行地与单位所在地不同时，N/2N保留公式并要求cross_city_compensation_rule专业核验；即使两城都有数值也不自动选择。

解除条件另行填写；选择解除标签不能替代这些条件：

| 解除类型 | 结构化补充 |
| --- | --- |
| employer_agreement | `agreement_reached` 是否双方已就单位提出的解除达成一致 |
| worker_38 | `worker38_ground` 为 `unknown/unpaid_wages/labor_conditions/unpaid_social_insurance/unlawful_rules/invalid_contract/other`；`worker38_conditions`、`worker38_notice_delivered` 分别记录具体事由条件及告知送达陈述；other 转专业复核 |
| article_40 | `article40_category` 为 `unknown/medical/incompetence/objective_change`；另核对 `article40_conditions/protected_status/written_notice_30` |
| article_41 | `layoff_conditions/layoff_procedure/protected_status` 分别记录法定规模事由、法定程序、保护情形 |
| illegal_claim | `continued_performance` 为 `unknown/not_requested/requested/impossible`；请求继续履行时阻止按赔偿金路径直接确认 |

布尔条件允许 null 表示未知；回答“是”仍仅为用户陈述。`claims[].condition_checklist` 保存逐项状态及 `evidence_verified=false`。前端按当前解除类型显示相关条件。未满足类型条件时不开放请求确认，不适用的 N/2N 备选不显示计算金额。

`structured` 在 `workflow=case` 下包含 `case_version/facts/fact_sources/fact_conflicts/claims/calculations/sources/coverage/missing_info/missing_labels/review_issues/status/confirmation/confirmation_required/document/document_status/revisions/stages/failures/model_calls/knowledge_digest` 等。

金额为字符串或 null。主要状态：`needs_information/review_blocked/no_supported_claim/awaiting_confirmation/draft_ready/document_blocked`。零欠付余额仍返回0.00元核算结果，但为no_supported_claim，不开放追讨零元的草稿确认。模型未启用时 `analysis.status=rules_only`，不表示真实模型协作已运行。

v13中，已排除请求仍在claims展示，状态not_selected；模型只分析其余请求。若请求已全部排除，analysis.status与model_review.status为not_applicable、model_calls为空，表示规则提前终止，不是模型失败或已运行协同。其他关键规则仍会阻断，不开放文书。

模型审查问题可附`law_excerpts[{source_id,quote}]`、`fact_excerpts[{field,quote}]`及`missing_fact_fields`。事实路径如`wages.0.due`，工具路径如`calculations.0.amount`；合并后的`fact_fields`记录涉及的位置。后端校验来源、片段和原值，校验通过不代表法律推理或证据真实性已核验。未知引用、伪造片段等最多纠正一次，失败后仍阻止确认。

## 确认生成草稿

```json
{
  "workflow":"case",
  "session_id":"arrears-demo",
  "action":"confirm",
  "expected_case_version":1,
  "selected_claims":["arrears"]
}
```

确认不可同时修改事实。选择限当前条件允许的 `N/2N/notice/arrears`，N 与 2N、2N 与 notice 不能同时选。存在关键缺失/失败/阻断审查时返回明确的未确认状态，不生成文书。条件完整时进入文书生成及审查，`document_status=reviewed_draft` 才能显示、复制 Markdown。

确认过期返回 HTTP 409：

```json
{"detail":{"message":"案件版本已变化，请查看新金额并重新确认。","case_version":2}}
```

知识库、计算规则、工作流版本、模型启用状态或角色模型配置切换也使既有确认失效，依赖版本保存于 `structured.dependencies`，包括不含密钥的model_profile_sha256。先 analyze 获取最新版本及金额，再确认。用户确认仅表示认可输入，不证明证据真实或请求最终获支持。

## SSE

普通接口仍有 `route/structured/token/done`。案件协同另外发送：

- `task_started`：节点实际开始；含 task、case_version。
- `task_completed`：节点实际结束；含 task、status、seconds、case_version。
- `review_issue`：审查发现的具体问题。
- `confirmation_required`：需要用户核对事实、请求、金额。
- `error`：message 及可用时 code；流开始后的错误通过事件返回。

节点顺序 intake → retrieval → analysis → calculation → analysis_review → confirmation，明确确认后才追加 document → document_review。旧的重放文字 token 不代表模型 token，`done.token_count` 是传输片段数；真实 LLM usage 在 `structured.model_calls`。

v14在analysis_review后增加有条件分支：仅对符合修订政策的Judge引用问题运行analysis_revision → analysis_recheck → confirmation，每轮请求最多一次，不循环。对应task_started/task_completed来自实际节点执行；其余关键缺失和失败继续阻止确认。

structured新增analysis_repair（attempts、status、feedback）和analysis_review_history（最近20次初审或复审记录，含case_version、phase、facts_sha256、analysis、model_review、issues、source_refs）。修订失败保留初审关键问题，复审未通过返回review_blocked。历史问题可能已被修订，应以当前review_issues及status决定能否确认；历史内容不代表当前可提交的结论。

对已知过期版本，SSE 开始前返回 HTTP 409。请求字段错误为 422；损坏/不可读取的本地会话文件返回 503，并保留原文件。客户端遇 409 应重取案件并提示再次确认，不能自动重试确认旧金额。

## 欠薪事实补充

facts新增可选wage_statement（最多2000字），用于用户说明工资约定、当期工作履行和在职情况，作为待举证陈述保存来源；不会标为证据已核验。修改后同其他事实一样撤销旧确认与草稿。

`structured.date_checks`给出已填日期的确定性先后比较，包含左右字段、原值、比较符和passed。这只比较输入日期，不判断仲裁时效、工资到期或请求成立。审查可引用`date_checks.0.passed`等工具路径。

Judge和Doc固定使用qwen-plus；Review支持`CASE_REVIEW_MODEL=qwen-plus`（默认）或`qwen3.8-max`。后者使用low推理档、90秒超时和4096输出上限，前者60秒和2400；均无SDK自动重试，结构化纠正仍最多一次。未知模型配置报错，不静默替换。每次调用记录实际模型、配置、用量与耗时；该生产配置不改变已冻结的三组Qwen-plus实验。

v15的model_calls增加metadata_source（model_response或sdk_exception_completion）、output_log_truncated，以及异常中可用时的raw_usage。LengthFinishReasonError在SDK解析时产生，可能尚未形成模型消息；后端保留其completion实际返回的模型名、finish_reason、内容和用量，调用status仍为failed。没有报告的模型保持unknown、usage保持null；不能视为未调用或免费。格式纠正反馈列出invalid_fields的path/type/message，不自动补字段或删关键问题；length结果不作为完整JSON成功返回。工作流升级仍须重新分析和确认。

## v17前端展示（2026-10-27）

公共API与案件模型未改变。前端根据structured.presentation与workflow区分对话和案件，法源按回答绑定，详情面板和未保存编辑只写浏览器UI状态，不写后端事实。请求开始时固定session_id，响应仅更新原会话。事实保存后再走已有分析/失效/确认，409停止确认并由用户显式同步；不自动重试确认。桌面三栏、平板抽屉和手机全屏共用同一状态。Markdown库本地加载，缺失时转义为纯文本。
