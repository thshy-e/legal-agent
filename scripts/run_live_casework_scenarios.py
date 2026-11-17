"""Run frozen synthetic workflow scenarios; expectations never enter role inputs."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from legal_ai_agent.casework.models import empty_case
from legal_ai_agent.casework.model_policy import role_profile
from legal_ai_agent.casework.workflow import CaseWorkflow, WORKFLOW_VERSION
from legal_ai_agent.config.settings import QWEN_API_KEY


def run_scenario(item):
    case = empty_case(); workflow = CaseWorkflow(); phases = []
    started = time.monotonic()
    try:
        # Only request data enters the workflow, never expected statuses/amounts.
        workflow.run(deepcopy(item['request']), case)
        phases.append({'name': 'analyze', 'case': deepcopy(case)})
        expected = item['expected']
        assert case['status'] == expected['status'], 'unexpected analysis status'
        if expected.get('missing_contains'):
            assert set(expected['missing_contains']) <= set(case['missing_info']), 'missing condition lost'
        if expected.get('critical_code'):
            assert any(i['code'] == expected['critical_code'] and i['severity'] == 'critical'
                       for i in case['review_issues']), 'critical rule missing'
        if expected.get('amount') is not None:
            assert next(r['amount'] for r in case['calculations'] if r['claim_id'] == 'arrears') == expected['amount']
        if expected.get('no_notice'):
            assert not any(c['id'] == 'notice' for c in case['claims']), 'unsupported notice claim'
        if expected.get('confirm'):
            workflow.run({'action': 'confirm', 'expected_case_version': case['case_version'],
                          'selected_claims': ['arrears']}, case)
            phases.append({'name': 'confirm', 'case': deepcopy(case)})
            assert case['status'] == 'draft_ready', 'confirmation did not produce draft'
            assert expected['amount'] + ' 元' in case['document']['markdown'], 'draft amount mismatch'
            assert all(case['facts']['evidence'].get(e['name']) == 'claimed_present'
                       for e in case['document']['evidence']), 'invented evidence'
        else:
            assert case['confirmation'] is None and case['document'] is None
        calls = [call for phase in phases for call in phase['case']['model_calls']]
        if not calls:
            assert expected['status']=='no_supported_claim' and case['analysis']['status']=='not_applicable' and case['model_review']['status']=='not_applicable', 'unexpected model skip'
        assert all(c.get('actual_model') == c['requested_model'] and c.get('usage') for c in calls), 'missing actual call metadata'
        for phase in phases:
            phase_calls = phase['case']['model_calls']
            assert all(next(c for c in reversed(phase_calls) if c['role'] == role)['status'] == 'ok'
                       for role in {c['role'] for c in phase_calls}), 'role failed despite expected boundary status'
        status = 'completed'; error = None
    except Exception as exc:
        status = 'failed'; error = (type(exc).__name__ + ': ' + str(exc)).replace(QWEN_API_KEY, '[redacted]')[:600]
    return {'id': item['id'], 'status': status, 'error': error, 'phases': phases,
            'model_call_count':sum(len(p['case']['model_calls']) for p in phases),
            'seconds': round(time.monotonic() - started, 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, default=ROOT/'data/evaluation/live_scenarios_v1.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, choices=range(1, 4), default=3)
    args = parser.parse_args()
    raw = args.fixture.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    if digest != args.fixture.with_suffix('.sha256').read_text().strip(): parser.error('Frozen fixture hash mismatch')
    fixture = json.loads(raw); scenarios = fixture['scenarios']
    outputs = [args.output.with_name(item['id'] + '.json') for item in scenarios]
    if any(p.exists() for p in [args.output, *outputs]): parser.error('Existing evidence is never overwritten')
    if not QWEN_API_KEY: parser.error('DASHSCOPE_API_KEY is not configured')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    os.environ['CASE_MODEL_ENABLED'] = '1'
    report = {'status': 'running', 'workflow_version': WORKFLOW_VERSION, 'fixture_sha256': digest,
              'model_profiles': {r: role_profile(r) for r in ('Judge', 'Review', 'Doc')},
              'scope': 'Public synthetic engineering scenarios; not blind, expert-reviewed or legal accuracy.',
              'expert_reviewed': False, 'blind_test': False, 'workers': args.workers, 'runs': [],
              'implementation_sha256': {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in [Path(__file__).resolve(), *sorted((ROOT/'legal_ai_agent/casework').glob('*.py'))]}}
    def save():
        temp = args.output.with_suffix('.tmp')
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(args.output)
    save(); started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_scenario, item): path for item, path in zip(scenarios, outputs)}
        for future in as_completed(futures):
            result = future.result(); path = futures[future]
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            report['runs'].append({'id': result['id'], 'status': result['status'], 'report': path.name,
                                  'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'seconds': result['seconds']})
            save(); print(result['id'] + ': ' + result['status'], flush=True)
    report.update(status='completed' if all(r['status'] == 'completed' for r in report['runs']) else 'failed',
                  completed=sum(r['status'] == 'completed' for r in report['runs']), total=len(scenarios),
                  seconds=round(time.monotonic() - started, 3))
    save()
    if report['status'] != 'completed': raise SystemExit(1)


if __name__ == '__main__': main()
