# 人工法律复核操作

工具只导出真实已有产物、校验填写项并汇总人工评分，不会自行给法律评分。当前有60份规则工程产物及180份真实Qwen-plus产物待复核；模型包为 `legal_review_model_live_v1/`，25组自动标记必须逐案查看，不能直接当法律错误率。此前无密钥及公共接口401的包保留为历史记录，不计入本批实验。

## 导出与填写

仓库已生成 `legal_review_engineering_v1/`：`packet.json` 含各案输入和实际输出，去掉开发预期答案；`ratings.csv` 为UTF-8 BOM表格，初始全部pending。它仍使用公开工程案件，不是独立盲测。包摘要绑定数据集、评测报告与知识版本；原报告不被修改。

再次运行评测会更新当前报告文件；首次包对应报告已保存为 `engineering_results_before_auth_probe.json`，旧无密钥模型包对应 `model_ablation_before_auth_probe.json`。首次包保持其原始哈希绑定，不自动指向新结果。

```powershell
.\venv\Scripts\python.exe scripts/legal_review.py export --kind engineering --report docs/evaluation/casework_v2/engineering_results.json --output docs/evaluation/casework_v2/legal_review_engineering_v2
# 真正运行模型后，导出新目录；未运行、失败和无效输出逐行保留在skipped，不交给人工当成正常答案评分
.\venv\Scripts\python.exe scripts/legal_review.py export --kind model --report docs/evaluation/casework_v2/model_ablation.json --output docs/evaluation/casework_v2/legal_review_model_v2
```

命令拒绝覆盖已有导出目录。复核前查看同案`actual_output`与法源原文，复制ratings.csv为个人填写文件，保留全部行及review_id、task_id、variant不变：

- `review_status`：待审为pending；完成后改reviewed。
- `reviewer/reviewer_role/review_date`：真实姓名、身份及YYYY-MM-DD日期，不能填写未来日期。内部核查照实填写。
- 八个维度`facts/region_time/claim_conditions/claim_relations/evidence/calculation/sources/confirmation_document`：分别是事实主张、地域时间、请求条件、请求关系、证据、计算、法源、确认文书。填0错误遗漏、1部分正确、2正确有据、NA不适用；至少一项适用。
- `severe_errors`：JSON数组，无则`[]`；可选代码见下表。不要用逗号拼接的普通文本替代数组。
- `explanation`：具体法律理由与缺陷，不能空白。`source_urls`为支持理由的HTTP(S)原文链接JSON数组，例如`["https://example.org/source"]`；链接存在性和适用性仍由复核人检查。
- `final_legal_assessment`：acceptable可接受、needs_revision需修改、insufficient_information信息不足。记录严重错误或某维度0分时不能同时填acceptable。

| 严重错误代码 | 含义 |
| --- | --- |
| fabricated_source | 虚构法源 |
| wrong_region | 跨地域误用 |
| obsolete_rule | 废止条款当现行 |
| unconditional_compensation | 无条件2N或N+1 |
| fabricated_parameter_or_evidence | 编造参数或持有材料 |
| stale_confirmation | 过期确认生成草稿 |
| document_amount_mismatch | 金额与文书不一致 |

## 校验与汇总

```powershell
.\venv\Scripts\python.exe scripts/legal_review.py summarize --bundle docs/evaluation/casework_v2/legal_review_engineering_v1 --ratings docs/evaluation/casework_v2/legal_review_engineering_v1/ratings.csv --output docs/evaluation/casework_v2/legal_review_engineering_v1/summary-v2.json
```

输出文件必须尚不存在；多人意见分别保存、分别汇总，不覆盖分歧。篡改包、错配或遗漏评分行、非法分数、缺身份日期理由与出处、尚待审却填分等情况会报错。空白表汇总仍为0人审、评分比例null。

按组报告可审产物、已审、待审、维度得分及适用满分、严重错误案件数和各类次数、最终意见分布；NA不进入分母，未运行或失败输出单列。`dimension_point_ratio`只是维度得分占适用满分的比例，不是“法律准确率”。严重错误单独展示，不能被高总分掩盖。

脚本不核验复核人真实身份与律师/教师资质，始终输出`reviewer_identity_verified=false`、`expert_reviewed=false`、`blind_test=false`。取得真实外部复核时，另保存经核对的身份、日期、意见和授权引用记录，再由负责人核定材料表述；不能仅靠填写角色名自动获得专家背书。
