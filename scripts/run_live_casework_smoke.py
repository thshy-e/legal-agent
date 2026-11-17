"""Repeat a frozen synthetic workflow with real Qwen; no arbitration filing."""
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
from legal_ai_agent.casework.models import empty_case
from legal_ai_agent.casework.workflow import CaseWorkflow,CaseConflict,WORKFLOW_VERSION
from legal_ai_agent.config.settings import QWEN_API_KEY,QWEN_BASE_URL
from legal_ai_agent.casework.model_policy import role_profile


def load_fixture(path):
    raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    if digest!=path.with_suffix('.sha256').read_text().strip():
        raise ValueError('Frozen workflow fixture hash mismatch')
    return json.loads(raw),digest


def run_check(output,fixture,fixture_digest):
    case=empty_case();workflow=CaseWorkflow();started=time.monotonic()
    report={'status':'running','inputs':'synthetic','confirmation_actor':'automated_test',
            'base_url':QWEN_BASE_URL,'phases':[],'expert_reviewed':False,
            'workflow_version':WORKFLOW_VERSION,'fixture_sha256':fixture_digest,
            'model_profiles':{role:role_profile(role) for role in ('Judge','Review','Doc')},
            'implementation_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                for name in ('scripts/run_live_casework_smoke.py','legal_ai_agent/casework/roles.py',
                             'legal_ai_agent/casework/workflow.py','legal_ai_agent/casework/calculation.py',
                             'legal_ai_agent/casework/review_grounding.py','legal_ai_agent/casework/fact_checks.py',
                             'legal_ai_agent/casework/facts.py','legal_ai_agent/casework/models.py')}}
    report['implementation_sha256'].update({str(path.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT/'legal_ai_agent/casework').glob('*.py'))})
    def save():
        output.parent.mkdir(parents=True,exist_ok=True)
        temporary=output.with_suffix('.tmp')
        temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(output)
    def phase(name,request,expected_status,expected_amount):
        workflow.run(request,case)
        report['phases'].append({'name':name,'case':deepcopy(case)})
        save();print(name+': '+case['status'],flush=True)
        assert case['status']==expected_status,case['review_issues']
        amount=next(r['amount'] for r in case['calculations'] if r['claim_id']=='arrears')
        assert amount==expected_amount,amount
        calls=case['model_calls']
        assert calls and all(c.get('actual_model')==c['requested_model'] and c.get('usage') for c in calls)
        assert all(next(c for c in reversed(calls) if c['role']==role)['status']=='ok'
                   for role in {c['role'] for c in calls})
    try:
        initial=fixture['initial_amount'];amended=fixture['amended_amount']
        phase('analyze',fixture['initial_request'],'awaiting_confirmation',initial)
        phase('confirm',{'action':'confirm','expected_case_version':1,'selected_claims':fixture['selected_claims']},'draft_ready',initial)
        assert initial+' 元' in case['document']['markdown']
        phase('amend',fixture['amend_request'],'awaiting_confirmation',amended)
        assert case['confirmation'] is None and case['document'] is None and case['case_version']==2
        try:workflow.run({'action':'confirm','expected_case_version':1,'selected_claims':fixture['selected_claims']},case)
        except CaseConflict:report['stale_confirmation_rejected']=True
        else:raise AssertionError('stale confirmation was accepted')
        phase('reconfirm',{'action':'confirm','expected_case_version':2,'selected_claims':fixture['selected_claims']},'draft_ready',amended)
        assert amended+' 元' in case['document']['markdown'] and initial+' 元' not in case['document']['markdown']
        assert fixture['amend_request']['facts']['wage_statement'] in case['document']['markdown']
        assert '考勤' not in [e['name'] for e in case['document']['evidence']]
        report['status']='completed'
    except Exception as exc:
        report.update(status='failed',error=(type(exc).__name__+': '+str(exc)).replace(QWEN_API_KEY,'[redacted]')[:600])
    report['seconds']=round(time.monotonic()-started,3);save()
    print(json.dumps({'status':report['status'],'phases':len(report['phases']),'seconds':report['seconds']}),flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/evaluation/casework_v2/live_workflow_v5/summary.json')
    parser.add_argument('--fixture',type=Path,default=ROOT/'data/evaluation/live_workflow_fixture_v1.json')
    parser.add_argument('--repeat',type=int,default=1)
    args=parser.parse_args()
    if not 1<=args.repeat<=5:parser.error('--repeat must be between 1 and 5')
    fixture,digest=load_fixture(args.fixture)
    outputs=[args.output] if args.repeat==1 else [args.output.with_stem(args.output.stem+f'-run{i+1:02d}') for i in range(args.repeat)]
    if any(p.exists() for p in set(outputs+[args.output])):parser.error('Choose a new output path; existing evidence is not overwritten')
    if not QWEN_API_KEY:raise SystemExit('DASHSCOPE_API_KEY is not configured')
    previous=os.environ.get('CASE_MODEL_ENABLED');os.environ['CASE_MODEL_ENABLED']='1'
    try:reports=[run_check(path,fixture,digest) for path in outputs]
    finally:
        if previous is None:os.environ.pop('CASE_MODEL_ENABLED',None)
        else:os.environ['CASE_MODEL_ENABLED']=previous
    if args.repeat>1:
        summary={'status':'completed' if all(r['status']=='completed' for r in reports) else 'failed',
                 'workflow_version':WORKFLOW_VERSION,'fixture_sha256':digest,
                 'repetitions':args.repeat,'completed':sum(r['status']=='completed' for r in reports),
                 'runs':[{'report':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                          'status':r['status'],'seconds':r['seconds']} for p,r in zip(outputs,reports)],
                 'expert_reviewed':False,'blind_test':False,
                 'scope':'Repeated engineering smoke of one frozen synthetic scenario, not legal accuracy or general reliability.'}
        args.output.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    if any(r['status']!='completed' for r in reports):raise SystemExit(1)


if __name__=='__main__':main()
