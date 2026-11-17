"""Summarize measured calls and structural checks without inventing legal scores."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics

VARIANTS=('single_agent','collaboration_no_review','collaboration_review')


def summarize(report):
    if report.get('status')!='completed_with_results_requiring_human_review':
        raise ValueError('The primary experiment has not completed')
    rows=report['rows'];seen=set();groups={}
    for row in rows:
        key=(row['id'],row['variant'])
        if key in seen or row['variant'] not in VARIANTS:raise ValueError('Duplicate or unknown experiment row')
        seen.add(key)
    task_sets=[{r['id'] for r in rows if r['variant']==v} for v in VARIANTS]
    if not task_sets[0] or any(ids!=task_sets[0] for ids in task_sets):raise ValueError('Unbalanced task sets')
    for variant in VARIANTS:
        selected=[r for r in rows if r['variant']==variant]
        calls=[c for r in selected for c in r.get('trace',[])]
        completed=[r for r in selected if r['status']=='completed']
        errors=Counter(e for r in completed for e in r.get('automatic_errors',[]))
        usage=[c['usage'] for c in calls if isinstance(c.get('usage'),dict)]
        latencies=[c['seconds'] for c in calls if isinstance(c.get('seconds'),(int,float))]
        groups[variant]={
            'tasks':len(selected),'status_counts':dict(Counter(r['status'] for r in selected)),
            'completed_outputs':len(completed),
            'outputs_without_automatic_flags':sum(not r.get('automatic_errors') for r in completed),
            'outputs_with_automatic_flags':sum(bool(r.get('automatic_errors')) for r in completed),
            'automatic_flags':dict(errors),'call_attempts':len(calls),
            'call_status_counts':dict(Counter(c['status'] for c in calls)),
            'actual_models':dict(Counter(c.get('actual_model','unknown') for c in calls)),
            'calls_with_reported_usage':len(usage),'calls_without_reported_usage':len(calls)-len(usage),
            'reported_tokens':{k:sum(u.get(k,0) for u in usage) for k in ('input_tokens','output_tokens','total_tokens')},
            'role_call_seconds_sum':round(sum(latencies),3),
            'role_call_seconds_median':round(statistics.median(latencies),3) if latencies else None,
            'human_legal_reviews':sum(r.get('legal_human_score') is not None for r in selected),
        }
    return {'tasks_per_variant':len(task_sets[0]),'rows':len(rows),'groups':groups,
            'dataset_sha256':report['dataset_sha256'],'knowledge_digest':report['knowledge_digest'],
            'protocol_sha256':report['protocol_sha256'],'model_config':report['model_config'],
            'scheduling':report.get('scheduling'),'blind_test':False,'expert_reviewed':False,
            'limitations':[
                'Automatic flags assess schema, tool amount consistency, citation eligibility, claim-set alignment and confirmation gates only.',
                'No automatic flag does not prove legal correctness. Claim-set mismatches require human interpretation.',
                'Shared production tools supply facts, calculations and eligible source records to all variants.',
                'Public engineering cases are not an independent blind test.',
                'Parallel role-call durations are not end-to-end latency or deployment throughput.',
                'Unavailable usage is unknown; reported token sums exclude such calls.',
            ]}


def markdown(summary):
    names={'single_agent':'单Agent','collaboration_no_review':'协同无审查','collaboration_review':'协同有审查'}
    workers=(summary.get('scheduling') or {}).get('workers','未记录')
    lines=['# 真实Qwen-plus对照实验记录','',
           f"每组{summary['tasks_per_variant']}个公开工程任务，共{summary['rows']}组；法律人工评分尚待完成，不能据此宣称协同提高法律准确率。",'',
           '| 组别 | 完成结构化输出 | 无自动标记 | 有自动标记 | 调用尝试 | 已报告token | 单次角色耗时中位数 |',
           '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for variant,g in summary['groups'].items():
        lines.append(f"| {names[variant]} | {g['completed_outputs']} | {g['outputs_without_automatic_flags']} | {g['outputs_with_automatic_flags']} | {g['call_attempts']} | {g['reported_tokens']['total_tokens']} | {g['role_call_seconds_median']}秒 |")
    lines+=['','“无自动标记”只表示当前自动检查没有发现问题，仍可能存在法律分析遗漏。请求集合差异需逐案判断，不能直接当作法律错误率。所有失败、无效输出及标记均保留在原始报告。','',
            '三组共享模型、采样、法源和确定性工具结果；最终结构化输出统一使用JSON模式。协同组先执行限长分析，完整组再增加独立审查。初始40秒超时试跑及90秒未约束格式试跑另存历史目录，没有合并进本批结果。','',
            f'本批采用最多{workers}个独立任务并发，表内耗时为单次角色调用时间，不是用户从发问到生成草稿的总耗时。实际模型、逐调用usage、失败及采样配置见model_ablation.json。','',
            '本批协同有审查组的自动标记多于无审查组，增加审查没有在该指标上带来改进。尚未独立复测，也没有法律人工评分；不能宣称稳定优势或因果提升。','',
            '自动检查只覆盖结构、引用存在与适用、工具金额、请求集合和确认门槛，不替代法律人工评分。本批是共享工具条件下的结构化决策实验，生产办案闭环另见live_workflow_check.json。','',
            'JSON模式配置参考：[百炼官方结构化输出说明](https://help.aliyun.com/zh/model-studio/qwen-structured-output)。','']
    return '\n'.join(lines)


def main():
    root=Path(__file__).resolve().parents[1]/'docs/evaluation/casework_v2'
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,default=root/'model_ablation.json')
    parser.add_argument('--output',type=Path,default=root)
    args=parser.parse_args();raw=args.report.read_bytes();result=summarize(json.loads(raw))
    result['report_sha256']=hashlib.sha256(raw).hexdigest()
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'model_ablation_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.output/'MEASURED_MODEL_RESULTS.md').write_text(markdown(result),encoding='utf-8')
    print(json.dumps({'rows':result['rows'],'groups':result['groups']},ensure_ascii=False))


if __name__=='__main__':main()
