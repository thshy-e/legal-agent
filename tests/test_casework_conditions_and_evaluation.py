"""Regressions for legal-condition omissions and biased experiment inputs."""
from copy import deepcopy
import json
import os
from pathlib import Path
import hashlib
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from legal_ai_agent.casework.models import CaseFacts, empty_case
from legal_ai_agent.casework.conditions import termination_checklist
from legal_ai_agent.casework.calculation import calculate
from legal_ai_agent.casework.knowledge import KnowledgeRegistry, validate_manifest
from legal_ai_agent.casework.roles import retrieve_case_sources, model_analysis
from legal_ai_agent.casework.workflow import CaseWorkflow, CaseConflict
from scripts.run_case_evaluation import build_model_packet, live_variant, can_resume, protocol_digest, MODEL_CONFIG


class LegalConditionsTest(unittest.TestCase):
    def setUp(self):
        self.registry=KnowledgeRegistry()
        self.env=patch.dict(os.environ,{'CASE_MODEL_ENABLED':'0'});self.env.start()
    def tearDown(self):self.env.stop()
    def facts(self,**changes):
        values=dict(workplace='深圳',employer_city='深圳',dispute_date='2026-10-01',start_date='2023-01-01',end_date='2026-09-30',monthly_average='8000',previous_month_wage='9500',initiator='employer',termination_reason='用户填写的理由',termination_basis='article_40',article40_conditions=True,protected_status=False,written_notice_30=False)
        values.update(changes)
        return CaseFacts(**values).model_dump(mode='json')
    def test_article40_general_label_does_not_replace_specific_category(self):
        case=empty_case();result=CaseWorkflow(self.registry).run({'facts':self.facts()},case)['structured']
        self.assertIn('article40_category',result['missing_info'])
        self.assertEqual(next(c for c in result['claims'] if c['id']=='N')['status'],'needs_clarification')
        self.assertIsNone(result['confirmation'])
    def test_agreement_and_worker38_require_their_own_conditions(self):
        _,missing,_=termination_checklist(self.facts(termination_basis='employer_agreement',agreement_reached=False))
        self.assertEqual(missing,['agreement_reached'])
        facts=self.facts(termination_basis='worker_38',initiator='worker')
        _,missing,_=termination_checklist(facts)
        self.assertEqual(set(missing),{'worker38_ground','worker38_conditions','worker38_notice_delivered'})
        facts.update(worker38_ground='unpaid_wages',worker38_conditions=True,worker38_notice_delivered=True)
        checklist,missing,_=termination_checklist(facts)
        self.assertFalse(missing);self.assertTrue(all(not c['evidence_verified'] for c in checklist))
    def test_layoff_procedure_and_continuing_performance_are_not_assumed(self):
        _,missing,_=termination_checklist(self.facts(termination_basis='article_41',layoff_conditions=True))
        self.assertIn('layoff_procedure',missing)
        case=empty_case();result=CaseWorkflow(self.registry).run({'facts':self.facts(termination_basis='illegal_claim',continued_performance='requested')},case)['structured']
        self.assertTrue(any(i['code']=='remedy_conflict' for i in result['review_issues']))
        self.assertNotEqual(next(c for c in result['claims'] if c['id']=='2N')['status'],'conditional')
    def test_inapplicable_alternative_never_displays_a_calculated_amount(self):
        original=self.registry.parameter
        def fixture(city,purpose,when):
            return {'id':'SYNTHETIC_TEST_CAP','value':'30000'} if purpose=='severance_cap' else original(city,purpose,when)
        with patch.object(self.registry,'parameter',side_effect=fixture):
            _,results,_,_=calculate(self.facts(article40_category='incompetence'),self.registry,1)
        self.assertEqual(next(r for r in results if r['claim_id']=='N')['amount'],'32000.00')
        alternative=next(r for r in results if r['claim_id']=='2N')
        self.assertIsNone(alternative['amount']);self.assertEqual(alternative['status'],'not_applicable')
    def test_reference_cases_are_civil_balanced_and_carry_historical_limits(self):
        case=empty_case();case['facts']=self.facts(termination_basis='worker_38',initiator='worker',worker38_ground='unpaid_social_insurance')
        sources=retrieve_case_sources(case,self.registry)
        refs=[d for d in sources if d['kind']=='case']
        self.assertEqual(len(refs),3)
        self.assertTrue(all(d['case_type']=='official_arbitration_award' for d in refs))
        self.assertTrue(any('supports_worker' in d.get('outcome_tags',[]) for d in refs))
        self.assertTrue(any('rejects_worker' in d.get('outcome_tags',[]) for d in refs))
        self.assertIn('spc-labor-II-2025:a19',{d['id'] for d in sources})
        historical=self.registry.by_id('sz-award-2022-8372','深圳','2026-10-01')
        self.assertIn('2025-09-01',historical['limits'])
        case.update(sources=sources,claims=[])
        prompts=[]
        model_analysis(case,runner=lambda prompt:prompts.append(prompt) or '{"arguments":[]}')
        self.assertIn(refs[0]['limits'],prompts[0])
        self.assertIn(refs[0]['holding'],prompts[0])
    def test_case_snapshot_tampering_is_rejected_before_activation(self):
        manifest=json.loads(Path('data/legal_sources/manifest.json').read_text(encoding='utf-8'))
        manifest['cases'][-1]['sha256']='tampered'
        with self.assertRaisesRegex(ValueError,'case hash mismatch'):validate_manifest(manifest)
    def test_rule_change_invalidates_a_confirmed_document(self):
        case=empty_case();workflow=CaseWorkflow(self.registry)
        workflow.run({'facts':{'workplace':'广州','employer_city':'广州','dispute_date':'2026-10-01','wages':[{'start':'2026-09-01','end':'2026-09-30','due':'8000','paid':'0'}]}},case)
        workflow.run({'action':'confirm','expected_case_version':1,'selected_claims':['arrears']},case)
        self.assertEqual(case['status'],'draft_ready')
        with patch('legal_ai_agent.casework.workflow.RULE_VERSION','future-version'):
            with self.assertRaises(CaseConflict):workflow.run({'action':'confirm','expected_case_version':1,'selected_claims':['arrears']},case)
        self.assertEqual(case['case_version'],2);self.assertIsNone(case['document']);self.assertIsNone(case['confirmation'])
    def test_zero_unpaid_balance_cannot_be_confirmed_into_a_claim(self):
        from legal_ai_agent.casework.workflow import CaseInputError
        for due,paid in [('8000','8000'),('100','150'),('0','0')]:
            case=empty_case();workflow=CaseWorkflow(self.registry)
            facts={'workplace':'广州','employer_city':'广州','dispute_date':'2026-10-01','wages':[{'start':'2026-09-01','end':'2026-09-30','due':due,'paid':paid}]}
            result=workflow.run({'facts':facts},case)['structured']
            self.assertEqual(result['status'],'no_supported_claim');self.assertFalse(result['confirmation_required'])
            self.assertEqual(result['calculations'][0]['amount'],'0.00')
            with self.assertRaises(CaseInputError):workflow.run({'action':'confirm','expected_case_version':1,'selected_claims':['arrears']},case)
            self.assertIsNone(case['document'])
    def test_model_output_failure_is_reflected_in_actual_progress_events(self):
        case=empty_case();events=[]
        result=CaseWorkflow(self.registry,model_runner=lambda prompt:'invalid').run({'facts':{'workplace':'广州','employer_city':'广州','dispute_date':'2026-10-01','wages':[{'start':'2026-09-01','end':'2026-09-30','due':'100','paid':'0'}]}},case,lambda name,payload:events.append((name,payload)))['structured']
        completed={p['task']:p['status'] for name,p in events if name=='task_completed'}
        self.assertEqual(completed['analysis'],'failed');self.assertEqual(completed['analysis_review'],'failed')
        self.assertFalse(result['confirmation_required']);self.assertIsNone(result['document'])


class ExperimentProtocolTest(unittest.TestCase):
    def test_independent_review_receives_provenance_and_citations_without_judge_opinions(self):
        from legal_ai_agent.casework.roles import review_context,analysis_context
        case=empty_case()
        with patch.dict(os.environ,{'CASE_MODEL_ENABLED':'0'}):
            CaseWorkflow().run({'facts':{'workplace':'广州','employer_city':'广州','dispute_date':'2026-10-01','wage_statement':'与单位约定工资，已正常工作，材料待举证','wages':[{'start':'2026-09-01','end':'2026-09-30','due':'100','paid':'0'}],'evidence':{'考勤':'missing'}}},case)
        case['analysis']={'status':'model_augmented','arguments':[{'claim_id':'arrears','source_ids':['contract-law-2012:a30'],'adverse_factors':['UNVERIFIED_OPINION_SENTINEL'],'supporting_evidence':[],'questions':[]}]}
        context=review_context(case)
        self.assertNotIn('UNVERIFIED_OPINION_SENTINEL',json.dumps(context))
        self.assertEqual(context['facts']['wage_statement'],case['facts']['wage_statement'])
        self.assertEqual(context['fact_provenance']['wage_statement']['source'],'user_structured')
        self.assertFalse(context['fact_provenance']['wage_statement']['evidence_verified'])
        self.assertEqual(context['judge_citations'][0]['source_ids'],['contract-law-2012:a30'])
        self.assertEqual(context['facts']['evidence']['考勤'],'missing')
        self.assertTrue(all(s['kind']=='law' for s in context['sources']))
        self.assertTrue(any(s['kind']=='case' for s in analysis_context(case)['sources']))
    def test_wage_narrative_is_rendered_as_a_statement_and_is_revised_with_the_draft(self):
        case=empty_case();workflow=CaseWorkflow()
        with patch.dict(os.environ,{'CASE_MODEL_ENABLED':'0'}):
            workflow.run({'facts':{'workplace':'广州','employer_city':'广州','dispute_date':'2026-10-01','wage_statement':'合同约定应付100元，已正常提供劳动。','wages':[{'start':'2026-09-01','end':'2026-09-30','due':'100','paid':'0'}]}},case)
            workflow.run({'action':'confirm','expected_case_version':1,'selected_claims':['arrears']},case)
            self.assertIn('合同约定应付100元',case['document']['markdown'])
            workflow.run({'facts':{'wage_statement':'更正：合同约定120元。','wages':[{'start':'2026-09-01','end':'2026-09-30','due':'120','paid':'0'}]}},case)
            self.assertIsNone(case['document']);self.assertIsNone(case['confirmation'])
            workflow.run({'action':'confirm','expected_case_version':2,'selected_claims':['arrears']},case)
        self.assertIn('合同约定120元',case['document']['markdown'])
        self.assertNotIn('合同约定应付100元',case['document']['markdown'])
        self.assertFalse(case['confirmation']['evidence_verified'])
    def test_draft_evidence_warning_preserves_raw_review_but_legal_blocker_stays(self):
        laws=['contract-law-2012:a30','labor-law-2018:a50','arbitration-law-2008:a6']
        for category,status,severity in [('evidence_gap','awaiting_confirmation','warning'),('subject_placeholder','awaiting_confirmation','warning'),('legal_condition','review_blocked','critical')]:
            def runner(prompt):
                if '的Review角色' in prompt:return json.dumps({'issues':[{'code':'synthetic_review','category':category,'severity':'critical','message':'synthetic review finding','source_ids':laws,'fact_fields':['wage_statement'],'missing_fact_fields':['wage_statement'],'law_excerpts':[{'source_id':'contract-law-2012:a30','quote':'用人单位应当按照劳动合同约定和国家规定，向劳动者及时足额支付劳动报酬。'}]}]})
                return json.dumps({'arguments':[{'claim_id':'arrears','supporting_evidence':[],'adverse_factors':[],'source_ids':laws,'questions':[]}]})
            case=empty_case();workflow=CaseWorkflow(model_runner=runner)
            workflow.run({'facts':{'workplace':'广州','employer_city':'广州','dispute_date':'2026-10-01','wages':[{'start':'2026-09-01','end':'2026-09-30','due':'100','paid':'0'}]}},case)
            self.assertEqual(case['status'],status)
            self.assertEqual(case['model_review']['issues'][0]['severity'],'critical')
            finding=next(i for i in case['review_issues'] if i['code']=='synthetic_review')
            self.assertEqual(finding['severity'],severity)
            if category!='legal_condition':self.assertEqual(finding['original_severity'],'critical')
    def test_wage_role_context_does_not_require_termination_only_parameters(self):
        from legal_ai_agent.casework.roles import analysis_context
        registry=KnowledgeRegistry();case=empty_case()
        CaseWorkflow(registry).run({'facts':{'workplace':'广州','employer_city':'广州','dispute_date':'2026-10-01','wages':[{'start':'2026-09-01','end':'2026-09-30','due':'100','paid':'0'}]}},case)
        context=analysis_context(case)
        self.assertNotIn('monthly_average',context['facts'])
        self.assertNotIn('contract-law-2012:a47',{s['id'] for s in context['sources']})
        self.assertIn('arbitration-law-2008:a6',{s['id'] for s in context['sources']})
        self.assertEqual(context['facts']['wages'],case['facts']['wages'])
        # A termination claim must retain its own wage base and Article 47.
        case['claims']=[{'id':'N','laws':['contract-law-2012:a47']}]
        context=analysis_context(case)
        self.assertIn('monthly_average',context['facts'])
        self.assertIn('contract-law-2012:a47',{s['id'] for s in context['sources']})
    def test_parallel_batch_verifies_credentials_before_launching_pool(self):
        from scripts import run_case_evaluation as evaluation
        tasks=[{'id':str(i)} for i in range(3)];rows=[]
        failure={'status':'failed','fatal_configuration_error':True,'http_status':401,'trace':[]}
        with patch.object(evaluation,'live_variant',return_value=failure) as call:
            fatal=evaluation.run_live_rows(tasks,[{}]*3,{},True,rows.append,workers=3)
        self.assertEqual(call.call_count,1);self.assertEqual(fatal['http_status'],401)
        self.assertEqual(len(rows),9);self.assertEqual(sum(r['status']=='not_run' for r in rows),8)
    def test_parallel_batch_preserves_each_task_variant_once_and_resumes_completed(self):
        from scripts import run_case_evaluation as evaluation
        tasks=[{'id':str(i)} for i in range(3)];rows=[]
        previous={'0:single_agent':{'id':'0','variant':'single_agent','status':'completed','trace':[]}}
        with patch.object(evaluation,'live_variant',return_value={'status':'completed','trace':[]}) as call:
            fatal=evaluation.run_live_rows(tasks,[{}]*3,previous,True,rows.append,workers=3)
        self.assertIsNone(fatal);self.assertEqual(call.call_count,8)
        self.assertEqual(len({(r['id'],r['variant']) for r in rows}),9)
    def test_batch_stops_after_one_auth_failure_and_exits_nonzero(self):
        from scripts import run_case_evaluation as evaluation
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);dataset=root/'tasks.json';out=root/'results'
            tasks=[{'id':str(i),'group':'synthetic'} for i in range(3)]
            dataset.write_text(json.dumps({'version':'synthetic-test','tasks':tasks}),encoding='utf-8')
            dataset.with_suffix('.sha256').write_text(hashlib.sha256(dataset.read_bytes()).hexdigest(),encoding='ascii')
            def engineering(task,registry):return {'id':task['id'],'group':'synthetic','passed':True,'errors':[],'artifact':{}}
            failure={'status':'failed','fatal_configuration_error':True,'http_status':401,'trace':[]}
            with patch('sys.argv',['runner','--live','--dataset',str(dataset),'--output',str(out)]), patch.object(evaluation,'KnowledgeRegistry',return_value=SimpleNamespace(data={'digest':'synthetic'})), patch.object(evaluation,'evaluate_task',side_effect=engineering), patch.object(evaluation,'live_variant',return_value=failure) as call, patch('legal_ai_agent.config.settings.QWEN_API_KEY','SYNTHETIC_TEST_KEY'):
                with self.assertRaises(SystemExit) as stopped:evaluation.main()
            self.assertEqual(stopped.exception.code,2);self.assertEqual(call.call_count,1)
            report=json.loads((out/'model_ablation.json').read_text(encoding='utf-8'))
            self.assertEqual(report['status'],'aborted_configuration_error')
            self.assertEqual(sum(r['status']=='not_run' for r in report['rows']),8)
            self.assertTrue(all(not r['trace'] for r in report['rows']))
    def test_v2_changes_only_documented_zero_balance_expectations(self):
        base=Path('data/evaluation')
        v1=json.loads((base/'case_tasks_v1.json').read_text(encoding='utf-8'))
        v2=json.loads((base/'case_tasks_v2.json').read_text(encoding='utf-8'))
        changed=[]
        for before,after in zip(v1['tasks'],v2['tasks']):
            self.assertEqual({k:v for k,v in before.items() if k!='expected'},{k:v for k,v in after.items() if k!='expected'})
            if before!=after: changed.append(before['id'])
        self.assertEqual(changed,['W05','W06','W07'])
    def inputs(self):
        task={'id':'internal-id','name':'GOLD_SECRET','kind':'case','request':{'query':'工资未付'},'expected':{'amount':'GOLD_SECRET'},'expected_source':'GOLD_SECRET','expected_value':'GOLD_SECRET'}
        artifact={'facts':{},'sources':[],'claims':[],'calculations':[],'review_issues':['REVIEW_SECRET'],'analysis':'ANALYSIS_SECRET','status':'draft_ready'}
        return task,artifact
    def test_no_expected_answers_or_production_review_are_shared(self):
        task,artifact=self.inputs();packet=build_model_packet(task,artifact)
        encoded=json.dumps(packet)
        for secret in ('GOLD_SECRET','REVIEW_SECRET','ANALYSIS_SECRET','draft_ready'):self.assertNotIn(secret,encoded)
        self.assertEqual(packet['user_input']['request'],task['request'])
        packet['shared_tools']['facts']['changed']=True
        self.assertEqual(artifact['facts'],{})
    def test_variants_use_distinct_handoffs_and_record_actual_usage(self):
        task,artifact=self.inputs()
        answer=json.dumps({'claims':[],'missing_info':[],'source_ids':[],'allow_document':False})
        for variant,count in [('single_agent',1),('collaboration_no_review',2),('collaboration_review',3)]:
            prompts=[]
            def runner(messages):
                prompts.append(messages)
                return SimpleNamespace(content=answer,response_metadata={'model_name':'reported-model'},usage_metadata={'input_tokens':10,'output_tokens':5,'total_tokens':15})
            result=live_variant(task,{'artifact':artifact},variant,runner)
            self.assertEqual(result['status'],'completed');self.assertEqual(len(prompts),count)
            self.assertTrue(all(c['actual_model']=='reported-model' and c['usage']['total_tokens']==15 for c in result['trace']))
            self.assertNotIn('GOLD_SECRET',json.dumps(prompts))
    def test_timeouts_retain_failed_call_without_fabricating_usage(self):
        task,artifact=self.inputs()
        def timeout(messages):raise TimeoutError('simulated')
        result=live_variant(task,{'artifact':artifact},'collaboration_review',timeout)
        self.assertEqual(result['status'],'failed');self.assertEqual(len(result['trace']),1)
        self.assertIsNone(result['trace'][0]['usage']);self.assertEqual(result['trace'][0]['status'],'failed')
    def test_authentication_failure_is_terminal_and_does_not_expose_key(self):
        task,artifact=self.inputs()
        class SyntheticAuthError(Exception):
            status_code=401
            request_id='synthetic-request'
        def invalid_key(messages):raise SyntheticAuthError('credential=SYNTHETIC_PRIVATE_KEY')
        with patch('legal_ai_agent.config.settings.QWEN_API_KEY','SYNTHETIC_PRIVATE_KEY'):
            result=live_variant(task,{'artifact':artifact},'collaboration_review',invalid_key)
        self.assertTrue(result['fatal_configuration_error'])
        self.assertEqual(result['request_id'],'synthetic-request')
        self.assertEqual(len(result['trace']),1);self.assertIsNone(result['trace'][0]['usage'])
        self.assertNotIn('SYNTHETIC_PRIVATE_KEY',json.dumps(result))
    def test_custom_base_url_reaches_client_and_is_part_of_resume_contract(self):
        from legal_ai_agent.llm.qwen_llm import get_llm
        with patch('legal_ai_agent.llm.qwen_llm.ChatOpenAI') as client, patch('legal_ai_agent.llm.qwen_llm.get_dashscope_api_key',return_value='SYNTHETIC_PRIVATE_KEY'):
            get_llm(model_name='qwen-plus',base_url='https://synthetic.invalid/compatible-mode/v1')
        self.assertEqual(client.call_args.kwargs['openai_api_base'],'https://synthetic.invalid/compatible-mode/v1')
        previous={'dataset_sha256':'a','knowledge_digest':'b','protocol_sha256':protocol_digest(),'model_config':deepcopy(MODEL_CONFIG)}
        previous['model_config']['base_url']='https://different.invalid/v1'
        self.assertFalse(can_resume(previous,'a','b'))
    def test_resume_requires_matching_protocol_and_sampling_config(self):
        previous={'dataset_sha256':'a','knowledge_digest':'b','protocol_sha256':protocol_digest(),'model_config':deepcopy(MODEL_CONFIG)}
        self.assertTrue(can_resume(previous,'a','b'))
        previous['shared_tool_packets_sha256']='tools-before'
        self.assertTrue(can_resume(previous,'a','b','tools-before'))
        self.assertFalse(can_resume(previous,'a','b','tools-after'))
        previous['protocol_sha256']='old';self.assertFalse(can_resume(previous,'a','b'))
        previous['protocol_sha256']=protocol_digest();previous['model_config']['temperature']=1
        self.assertFalse(can_resume(previous,'a','b'))


if __name__=='__main__':unittest.main()
