"""Bounded Judge/Review feedback, preserving original findings and hard gates."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from legal_ai_agent.casework.models import empty_case
from legal_ai_agent.casework.review_revision import citation_feedback
from legal_ai_agent.casework.workflow import CaseWorkflow


def data(prompt):
    return json.JSONDecoder().raw_decode(prompt.split('\nDATA=',1)[1])[0]


class AnalysisRevisionTest(unittest.TestCase):
    def setUp(self):
        env=patch.dict(os.environ,{'CASE_MODEL_ENABLED':'0'});env.start();self.addCleanup(env.stop)
        fixture=json.loads(Path('data/evaluation/live_scenarios_v1.json').read_text(encoding='utf-8'))
        self.request=deepcopy(next(s['request'] for s in fixture['scenarios'] if s['id']=='S04'))
        self.bad='sz-wage-2022:a30';self.calls=[];self.review_count=0

    def citation_issue(self,context):
        source=next(s for s in context['sources'] if s['id']==self.bad)
        return {'code':'TEST_CITATION','severity':'critical','category':'citation',
                'message':'Synthetic reviewer finding about citation applicability; not a legal opinion.',
                'source_ids':[self.bad],'law_excerpts':[{'source_id':self.bad,'quote':source['original_text'][:120]}],
                'fact_excerpts':[{'field':'employment_status','quote':'active'}]}

    def runner(self,prompt,repeat_issue=False,fail_revision=False):
        context=data(prompt)
        if '的Review角色' in prompt:
            self.calls.append('Review');self.review_count+=1
            issues=[self.citation_issue(context)] if self.review_count==1 or repeat_issue else []
            return json.dumps({'issues':issues},ensure_ascii=False)
        self.calls.append('Judge')
        if context.get('review_feedback'):
            if fail_revision:return 'invalid'
            ids=['contract-law-2012:a30']
        else:ids=[self.bad]
        return json.dumps({'arguments':[{'claim_id':ident,'supporting_evidence':[],'adverse_factors':[],
                              'source_ids':ids,'questions':[]} for ident in context['required_claim_ids']]})

    def test_citation_is_revised_once_and_rechecked_without_changing_facts_or_amount(self):
        case=empty_case();events=[]
        result=CaseWorkflow(model_runner=self.runner).run(self.request,case,lambda event,payload:events.append((event,payload)))['structured']
        self.assertEqual(self.calls,['Judge','Review','Judge','Review'])
        self.assertEqual(result['status'],'awaiting_confirmation')
        self.assertEqual(result['analysis_repair']['attempts'],1)
        self.assertEqual(result['analysis_repair']['status'],'review_passed')
        history=result['analysis_review_history']
        self.assertEqual([r['phase'] for r in history],['initial','after_revision'])
        self.assertEqual(history[0]['facts_sha256'],history[1]['facts_sha256'])
        self.assertEqual(history[0]['issues'][1]['severity'],'critical')
        self.assertIn(self.bad,history[0]['analysis']['arguments'][0]['source_ids'])
        self.assertNotIn(self.bad,result['analysis']['arguments'][0]['source_ids'])
        self.assertEqual(result['calculations'][0]['amount'],'6000.69')
        self.assertIsNone(result['confirmation']);self.assertIsNone(result['document'])
        tasks=[p['task'] for event,p in events if event=='task_started']
        self.assertLess(tasks.index('analysis_review'),tasks.index('analysis_revision'))
        self.assertLess(tasks.index('analysis_revision'),tasks.index('analysis_recheck'))
        self.assertEqual(tasks.count('analysis_revision'),1)

    def test_unresolved_review_stops_without_a_second_revision(self):
        case=empty_case()
        CaseWorkflow(model_runner=lambda p:self.runner(p,repeat_issue=True)).run(self.request,case)
        self.assertEqual(self.calls,['Judge','Review','Judge','Review'])
        self.assertEqual(case['status'],'review_blocked')
        self.assertEqual(case['analysis_repair']['status'],'review_blocked')
        self.assertIsNone(case['document'])

    def test_revision_schema_failure_keeps_original_critical_and_does_not_recheck(self):
        case=empty_case()
        CaseWorkflow(model_runner=lambda p:self.runner(p,fail_revision=True)).run(self.request,case)
        self.assertEqual(self.calls,['Judge','Review','Judge','Judge'])
        self.assertEqual(case['status'],'review_blocked')
        self.assertEqual(case['analysis_repair']['status'],'failed')
        self.assertTrue(any(i['code']=='TEST_CITATION' and i['severity']=='critical' for i in case['review_issues']))

    def test_other_blockers_and_unattributed_issues_are_not_auto_revised(self):
        issue={'code':'citation','severity':'critical','category':'citation','source_ids':['cited']}
        base={'analysis':{'status':'model_augmented','arguments':[{'source_ids':['cited']}]},
              'analysis_repair':{'attempts':0},'model_review':{'issues':[issue]},'review_issues':[],
              'missing_info':[],'failures':[]}
        self.assertEqual(citation_feedback(base,[issue]),[issue])
        for change in ('missing','failure','existing','other_category','uncited','not_from_model','already_revised'):
            case=deepcopy(base);candidate=deepcopy(issue)
            if change=='missing':case['missing_info']=['severance_cap']
            elif change=='failure':case['failures']=[{'stage':'analysis'}]
            elif change=='existing':case['review_issues']=[{'severity':'critical','code':'fact_conflict'}]
            elif change=='other_category':candidate['category']='legal_condition'
            elif change=='uncited':case['analysis']['arguments']=[]
            elif change=='not_from_model':case['model_review']['issues']=[]
            else:case['analysis_repair']['attempts']=1
            with self.subTest(change=change):self.assertEqual(citation_feedback(case,[candidate]),[])

    def test_mutation_during_revision_is_restored_and_blocked(self):
        from legal_ai_agent.agents.judge_agent import JudgeAgent
        real=JudgeAgent()
        class MutatingJudge:
            def analyze_case(inner,case,runner=None):
                result=real.analyze_case(case,runner)
                if case['analysis_repair']['status']=='running':
                    case['facts']['wages'][0]['due']='1';case['calculations'][0]['amount']='0.01'
                return result
        case=empty_case()
        CaseWorkflow(judge=MutatingJudge(),model_runner=self.runner).run(self.request,case)
        self.assertEqual(case['facts']['wages'][0]['due'],'9200.99')
        self.assertEqual(case['calculations'][0]['amount'],'6000.69')
        self.assertEqual(case['analysis_repair']['status'],'blocked')
        self.assertEqual(case['status'],'review_blocked')
        self.assertIsNone(case['document'])

    def test_json_reload_retains_both_reviews_without_reusing_old_feedback(self):
        from legal_ai_agent.memory.memory_manager import ConversationStateStore
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'cases.json';store=ConversationStateStore(path)
            with store.case_transaction('case') as case:
                CaseWorkflow(model_runner=self.runner).run(self.request,case)
            reloaded=ConversationStateStore(path).get('case')['case']
            self.assertEqual(len(reloaded['analysis_review_history']),2)
            self.assertEqual(reloaded['analysis_repair']['attempts'],1)
            seen=[]
            def next_runner(prompt):
                if '的Review角色' in prompt:return '{"issues":[]}'
                seen.append(data(prompt))
                return json.dumps({'arguments':[{'claim_id':'arrears','supporting_evidence':[],
                    'adverse_factors':[],'source_ids':['contract-law-2012:a30'],'questions':[]}]})
            CaseWorkflow(model_runner=next_runner).run({'action':'analyze'},reloaded)
            self.assertNotIn('review_feedback',seen[0])
            self.assertEqual(reloaded['analysis_repair']['attempts'],0)
            self.assertEqual(len(reloaded['analysis_review_history']),3)

    def test_sse_emits_revision_and_recheck_from_the_executed_graph(self):
        from fastapi.testclient import TestClient
        from legal_ai_agent.api import server
        from legal_ai_agent.memory.memory_manager import ConversationStateStore
        with tempfile.TemporaryDirectory() as directory:
            store=ConversationStateStore(Path(directory)/'cases.json')
            workflow=CaseWorkflow(model_runner=self.runner)
            with patch.object(server,'conversation_store',store), patch(
                'legal_ai_agent.casework.workflow.CaseWorkflow',return_value=workflow):
                response=TestClient(server.app).post('/api/chat/stream',json={
                    'workflow':'case','session_id':'revision-sse',**self.request})
            self.assertEqual(response.status_code,200)
            records=[]
            for block in response.text.strip().split('\n\n'):
                lines=block.splitlines()
                records.append((lines[0].removeprefix('event: '),json.loads(lines[1].removeprefix('data: '))))
            started=[p['task'] for event,p in records if event=='task_started']
            completed=[p['task'] for event,p in records if event=='task_completed']
            self.assertEqual(started,completed)
            self.assertEqual(started.count('analysis_revision'),1)
            self.assertEqual(started.count('analysis_recheck'),1)
            self.assertLess(started.index('analysis_revision'),started.index('analysis_recheck'))
            final=next(p['structured'] for event,p in records if event=='done')
            self.assertEqual(final['analysis_repair']['status'],'review_passed')
            self.assertEqual(len(final['analysis_review_history']),2)
            self.assertEqual(final['analysis_review_history'],store.get('revision-sse')['case']['analysis_review_history'])


if __name__=='__main__':unittest.main()
