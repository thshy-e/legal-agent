# 真实模型办案链路验收：固定欠薪案例已通过，泛化待验证

工作空间专用接口已成功接通，60案三组实验完成。v11使用Qwen-plus分析和文书、Qwen3.8-Max审查，固定欠薪案例连续3次完整闭环通过，见[原始汇总](live_workflow_v11_mixed/summary.json)。这与原全Qwen-plus三组实验是不同配置，不构成协同收益或模型优劣结论。当前默认CASE_MODEL_ENABLED=0。以下早期失败原样保留为历史记录。

真实调用先后暴露：最终输出格式不稳定、文书计划遗漏已确认引用、对待补主体资料及证据未核验的过度拦截。已启用JSON格式约束、明确文书确认对象、限制欠薪角色只读取当前请求所需上下文，并增加工资约定及劳动履行陈述；关键法律条件、金额和引用校验保持阻断。

审查使用明确类别。evidence_gap和subject_placeholder按辅助草稿政策列待补警告，原模型级别保留；legal_condition等关键问题仍阻断。最近一次模型仍将已陈述事实的材料未核验归入legal_condition，故整体未通过，不能靠重复试跑挑选成功结果宣称稳定。

所有输入为合成案例，确认动作由验收脚本模拟，不是真实用户同意或仲裁提交。下面七条为早期历史试跑；版本和输入曾按发现的问题调整，不能当相同条件的多次重复实验。

| 记录 | 实际阶段结果 | SHA256 |
| --- | --- | --- |
| [live_workflow_before_claim_scope.json](live_workflow_before_claim_scope.json) | analyze:review_blocked | 1b732c9d15af1614566c2a58055afc94349108333736b473ede9b2f838fe706f |
| [live_workflow_before_doc_contract.json](live_workflow_before_doc_contract.json) | analyze:awaiting_confirmation；confirm:failed | 55279632ee2ab3fd29bc6fadb9df70c8e5baf3328d79631b6e624c9f2e013e1d |
| [live_workflow_before_draft_scope.json](live_workflow_before_draft_scope.json) | analyze:review_blocked | 2fe99a885b32254e906d91ea1494a7e98737eb0ef89e28c66d6b93f3e9b631d7 |
| [live_workflow_before_evidence_context.json](live_workflow_before_evidence_context.json) | analyze:awaiting_confirmation；confirm:draft_ready；amend:review_blocked | b80998334adf20b1490e8490ee6c26f4bf7143cc86126fcd7abffa35ed9b396a |
| [live_workflow_before_review_categories.json](live_workflow_before_review_categories.json) | analyze:awaiting_confirmation；confirm:review_blocked | 53e4b1afb8605354719887d31a5dc6c376171dbea1ead00571d55c4acda7cdef |
| [live_workflow_before_wage_statement.json](live_workflow_before_wage_statement.json) | analyze:review_blocked | bad8106604175f7f47ea532a18ff29c4296479d57b30a07cf03aca7bd7ce2f59 |
| [live_workflow_check.json](live_workflow_check.json) | analyze:review_blocked | fc816e34e08ea5517027b56ab07f1262a75619b331b8a520007817abf8b357b2 |

下一轮应先核定审查的事实缺口、证明材料缺口及阻断规则，并由法学教师或律师复核；再用同一冻结输入重复验收，统计误阻断及遗漏阻断，不能只记录最顺利的一次。生产角色后续变更没有被此前共享工具v4对照实验验证，实验原协议及工具报告已独立保存于model_experiment_provenance.json。

## 冻结输入的连续复测

此后固定同一个欠薪合成案例及修改工资的四阶段脚本，不改变输入来挑选通过结果。输入SHA256为ce76629253a182315fa628c4d26757fee95b7f53f61089370e0eeaa15377dcf8。每个版本预先指定连续运行三次，全部结果及实现文件哈希保留。

| 版本 | 完成完整闭环 | 实际失败 | 报告 |
| --- | --- | --- | --- |
| v5 | 0/3 | Review把事实字段填入法源编号，两次结构化尝试均未通过 | [汇总](live_workflow_v5/summary.json) |
| v6 | 0/3 | 法源编号校验通过，仍在分析审查阶段被错误条件拦截 | [汇总](live_workflow_v6/summary.json) |
| v7 | 0/3 | 新增片段校验后发现重复填写字段不一致及1600 token截断 | [汇总](live_workflow_v7/summary.json) |
| v8 | 0/3 | 两次结构/引用校验未完成，另一次虽片段通过仍错误判断日期先后 | [汇总](live_workflow_v8/summary.json) |
| v10（全Plus） | 0/3 | 明确在职状态及日期工具后仍有结构错误或关键问题误报；一次分析通过后确认被阻断 | [汇总](live_workflow_v10/summary.json) |
| v11（Plus＋3.8-Max审查） | 3/3 | 四阶段均完成，旧确认拒绝、修改后金额与文书同步；耗时190.094/166.344/186.390秒 | [汇总](live_workflow_v11_mixed/summary.json) |

v6将fact_fields与source_ids分开，在提示Schema中列出允许的法源编号，并在格式纠正时指出具体无效值。独立Review只接收原始陈述、来源、请求与工具结果，不接收Judge的不利意见或参考案例裁判结论。每次调用的实际提示哈希均包含该次纠错信息，避免把不同尝试误记为同一上下文。

最新运行出现：忽略wage_statement中“仍在职”的明确陈述；对已保留两位小数的工资提出额外精度要求；认为地方规则应机械优先，并将未引用地方条文直接视为核心错误。记录中的这些输出均未经专家认可，不能当法律依据。系统保留原始意见并阻断，尚无可靠的自动误报裁定机制；不通过降级critical来制造闭环通过。

v7/v8补齐关系建立、工资支付周期和约定支付日法条，并要求关键法律问题引用原文及原始事实。v8由后端合并字段依赖，输出上限2400，仍只允许一次纠正。引用匹配未解决推理误报：第三次将2026-10-01说成早于2026-01-01，模型关键意见仍被保留并阻断。下一步需要核查具体命题，而非只核对引用存在。六次Review调用、36项中间意见及空白人工记录见[复核包](review_triage_v8/README.md)。该单案例复测不是独立盲测，不代表法律准确率，也不改变此前v4三组实验的结论。当时96项工程测试和公开60案工程集通过，仅证明已覆盖的状态、校验及规则行为。

角色输入与权限详见[上下文契约](../../ROLE_CONTEXT_CONTRACT.md)。默认CASE_MODEL_ENABLED=0保持不变。

生产v9增加跨市补偿参数保护：即使cross_city_resolved为true，也不能直接用单位所在地决定封顶参数；须核验实施条例第14条及约定等关系。v10增加待举证的在职状态、原句来源及日期工具，未解决全Plus闭环的误阻断；v11将Review模型单独配置，配置改变也使旧确认失效。

v11没有更改冻结案例或降低关键问题级别。每次均完成analyze、confirm、amend、reconfirm：欠薪7000.10元修改为8000.10元，版本1的旧确认被拒绝，最终草稿只引用新金额，考勤仍不列为持有材料。三次为同一个合成案例，确认由脚本模拟，不是三类真实案件、盲测或专家复核。

另外启用真实混合模型跑了在职状态冲突、实际跨境履行两个反例，均由既有关键规则阻止确认且未生成文书。原[调用报告](live_guards_v11_mixed.json)保留；临时验证器将第一项规则码错写为employment_status_conflict，导致其自动断言失败。按代码中的employment_statement_conflict核对同一输出后，两项规则均存在，见[复核记录](live_guards_v11_mixed_rechecked.json)。未追加调用或修改模型输出以制造通过。

v11阶段105项工程测试及公开60案通过。混合模型还需更多场景与独立盲测，尤其是解除条件、历史版本和复杂语言；封顶参数和人工法律评分仍待完成。已有全Plus三组实验的15/2/8自动标记结果不变。

后续v13扩展10场景工程预期9/10，其中9项调用真实模型、足额支付由规则终止；深圳2024场景因引用适用问题被审查阻断。v13原四阶段单次复测通过，112项工程测试及公开60案通过。各版本失败、验证器加强及当前逐案结果见[扩展验收说明](LIVE_SCENARIO_FINDINGS.md)，不能将早期v11重复结果当最新版本的三次重复证明。

v14增加一次引用分析修订及独立复审，原冻结四阶段单次完成，196.609秒，见[live_workflow_v14_mixed.json](live_workflow_v14_mixed.json)。HTTP规则模式的金额修订、过期409、重新确认及零余额结果也通过。119项工程测试及60案公开工程集通过。全新10场景8/10和单独受控回放的结果见扩展说明；这些是不同验收，不混合计算通过率，不宣称当前版本已三次重复通过。

v15保留所有关键校验，增强结构化纠正反馈并记录SDK截断的真实元数据。原冻结四阶段单次完成189.203秒，见[live_workflow_v15_mixed.json](live_workflow_v15_mixed.json)；125项回归和60案公开工程集通过。10场景9项严格工程预期通过，1项90秒审查超时保持失败；另一次非法律截断诊断证明元数据保存，不混入案件计数。完整源码清单覆盖所有办案模块，包含观察和引用修订模块。人工法律评分、独立盲测仍待完成。
