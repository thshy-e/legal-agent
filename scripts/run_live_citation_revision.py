"""Controlled replay of a recorded citation error, then fresh Judge/Review calls.

The first two role artifacts are explicitly replayed, not billed/new model calls.
This probe is separate from the fresh end-to-end scenario suite.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from legal_ai_agent.agents.judge_agent import JudgeAgent
from legal_ai_agent.casework.models import empty_case
from legal_ai_agent.casework.roles import AnalysisOutput, ReviewAgent, ReviewOutput, review_context
from legal_ai_agent.casework.review_grounding import validate_review_grounding
from legal_ai_agent.casework.review_revision import facts_digest
from legal_ai_agent.casework.workflow import CaseWorkflow, WORKFLOW_VERSION
from legal_ai_agent.config.settings import QWEN_API_KEY


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Existing evidence is never overwritten')
    if not QWEN_API_KEY:parser.error('DASHSCOPE_API_KEY is not configured')
    fixture_path=ROOT/'data/evaluation/live_scenarios_v1.json'
    raw=fixture_path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    assert digest==fixture_path.with_suffix('.sha256').read_text().strip()
    item=next(s for s in json.loads(raw)['scenarios'] if s['id']=='S04')
    seed_path=ROOT/'docs/evaluation/casework_v2/live_scenarios_v13_mixed/S04.json'
    seed_bytes=seed_path.read_bytes()
    seed=json.loads(seed_bytes)['phases'][0]['case']
    events=[];snapshots=[]

    class ReplayJudge(JudgeAgent):
        def analyze_case(self,case,runner=None):
            if not case['analysis_repair']['attempts']:
                assert case['facts']==seed['facts'],'Replay facts drifted'
                parsed=AnalysisOutput.model_validate({'arguments':seed['analysis']['arguments']})
                assert {a.claim_id for a in parsed.arguments}=={c['id'] for c in case['claims'] if c['status']!='not_selected'}
                assert all(set(a.source_ids)<={s['id'] for s in case['sources']} for a in parsed.arguments)
                return deepcopy(seed['analysis'])
            return super().analyze_case(case,runner)

    class ReplayReview(ReviewAgent):
        def review_analysis(self,case,runner=None):
            if not case['analysis_repair']['attempts']:
                assert case['calculations']==seed['calculations'],'Replay calculation drifted'
                old_sources={s['id']:s for s in seed['sources']}
                assert all(s==old_sources.get(s['id']) for s in case['sources']),'Replay sources drifted'
                parsed=ReviewOutput.model_validate(seed['model_review'])
                validate_review_grounding(parsed,review_context(case))
                assert parsed.model_dump()==seed['model_review']
                case['model_review']=parsed.model_dump()
                snapshots.append({'facts_sha256':facts_digest(case),'calculations':deepcopy(case['calculations'])})
                return deepcopy(seed['review_issues'])
            return super().review_analysis(case,runner)

    os.environ['CASE_MODEL_ENABLED']='1'
    case=empty_case();started=time.monotonic()
    report={'status':'running','workflow_version':WORKFLOW_VERSION,'scenario_id':'S04',
            'scope':'Controlled recorded first analysis/review; fresh revision and recheck only. Not a fresh end-to-end trial or legal accuracy.',
            'replayed_roles':['initial Judge','initial Review'],'expert_reviewed':False,'blind_test':False,
            'seed_report':str(seed_path.relative_to(ROOT)).replace('\\','/'),
            'seed_sha256':hashlib.sha256(seed_bytes).hexdigest(),'fixture_sha256':digest,
            'implementation_sha256':{str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [Path(__file__).resolve(),*sorted((ROOT/'legal_ai_agent/casework').glob('*.py'))]}}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    def save():
        temp=args.output.with_suffix('.tmp')
        temp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(args.output)
    save()
    try:
        CaseWorkflow(judge=ReplayJudge(),review=ReplayReview()).run(deepcopy(item['request']),case,
            lambda event,payload:events.append({'event':event,'payload':deepcopy(payload)}))
        assert case['analysis_repair']['attempts']==1
        assert case['analysis_repair']['status']=='review_passed'
        assert case['status']=='awaiting_confirmation'
        assert snapshots[0]['facts_sha256']==facts_digest(case)
        assert snapshots[0]['calculations']==case['calculations']
        assert len(case['analysis_review_history'])==2
        assert 'sz-wage-2022:a30' not in {k for a in case['analysis']['arguments'] for k in a['source_ids']}
        calls=case['model_calls']
        assert {c['role'] for c in calls}=={'Judge','Review'}
        assert all(c.get('actual_model')==c['requested_model'] and c.get('usage') for c in calls)
        assert all(next(c for c in reversed(calls) if c['role']==role)['status']=='ok' for role in ('Judge','Review'))
        assert case['confirmation'] is None and case['document'] is None
        report['status']='completed'
    except Exception as exc:
        report.update(status='failed',error=(type(exc).__name__+': '+str(exc)).replace(QWEN_API_KEY,'[redacted]')[:600])
    report.update(seconds=round(time.monotonic()-started,3),case=case,events=events,
                  fresh_model_call_count=len(case['model_calls']),replay_model_call_count=0)
    save()
    print(json.dumps({k:report[k] for k in ('status','seconds','fresh_model_call_count')}),flush=True)
    if report['status']!='completed':raise SystemExit(1)


if __name__=='__main__':main()
