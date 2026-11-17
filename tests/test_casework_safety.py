from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from legal_ai_agent.casework.models import empty_case, CaseFacts
from legal_ai_agent.casework.knowledge import KnowledgeRegistry, applicable, cn_number, build_index
from legal_ai_agent.casework.calculation import calculate, service_units
from legal_ai_agent.casework.workflow import CaseWorkflow, CaseInputError
from legal_ai_agent.casework.roles import ReviewAgent, model_analysis, structured_role, ReviewOutput, DocumentPlan

class CaseworkSafetyTest(unittest.TestCase):
    def setUp(self):
        self.registry=KnowledgeRegistry();self.case=empty_case();self.env=patch.dict(os.environ,{'CASE_MODEL_ENABLED':'0'});self.env.start()
    def tearDown(self):self.env.stop()
    def run_case(self,**req): return CaseWorkflow(self.registry).run(req,self.case)['structured']
    def base(self,**changes):
        values=dict(workplace='广州',employer_city='广州',dispute_date='2026-10-01',start_date='2023-01-01',end_date='2025-12-31',monthly_average='8000',previous_month_wage='9500',initiator='employer',termination_reason='单位称不能胜任，培训后仍不能胜任',termination_basis='article_40',article40_category='incompetence',article40_conditions=True,protected_status=False,written_notice_30=False)
        values.update(changes)
        return CaseFacts(**values).model_dump(mode='json')
    def test_region_and_historical_version_isolation(self):
        gz=self.registry.search('深圳市员工工资支付条例第22条','广州','2026-10-01');self.assertEqual(gz,[])
        old=self.registry.search('深圳市员工工资支付条例第22条','深圳','2025-12-04')
        new=self.registry.search('深圳市员工工资支付条例第22条','深圳','2025-12-05')
        self.assertEqual(old[0]['source_id'],'sz-wage-2022');self.assertEqual(new[0]['source_id'],'sz-wage-2025')
        self.assertNotEqual(old[0]['original_text'],new[0]['original_text'])
    def test_law_identity_exact_article(self):
        a=self.registry.search('劳动法第47条',on_date='2026-10-01')[0]
        b=self.registry.search('劳动合同法第47条',on_date='2026-10-01')[0]
        self.assertIn('工资分配',a['original_text']);self.assertIn('经济补偿',b['original_text'])
        self.assertEqual(cn_number('一百零七'),107)
    def test_partially_repealed_article_preserves_only_surviving_paragraph(self):
        query='最高人民法院关于审理劳动争议案件适用法律问题的解释（一）第32条'
        old=self.registry.search(query,on_date='2025-08-31')[0]
        new=self.registry.search(query,on_date='2025-09-01')[0]
        self.assertIn('享受养老保险待遇',old['original_text'])
        self.assertEqual(new['paragraph'],2)
        self.assertTrue(new['original_text'].startswith('企业停薪留职人员'))
        self.assertNotIn('享受养老保险待遇',new['original_text'])
    def test_independent_review_and_document_model_contracts(self):
        self.case.update(sources=[{'id':'verified-law'}],confirmation={'selected_claims':['arrears']},
                         claims=[{'id':'arrears','laws':['verified-law']}],calculations=[{'claim_id':'arrears','amount':'7000.10'}])
        self.case['facts']['evidence']={'工资流水':'claimed_present','考勤':'missing'}
        import json
        good={'requests':[{'claim_id':'arrears','amount':'7000.10','source_ids':['verified-law']}],'evidence_names':['工资流水']}
        prepared=structured_role(self.case,'Doc',DocumentPlan,{},'',lambda p:json.dumps(good))
        self.assertEqual(prepared,good)
        bad=deepcopy(good);bad['requests'][0]['amount']='8000.10'
        attempts=[]
        def wrong(prompt): attempts.append(prompt);return json.dumps(bad)
        self.assertTrue(structured_role(self.case,'Doc',DocumentPlan,{},'',wrong)['failed'])
        self.assertEqual(len(attempts),2)
        reviewed=structured_role(self.case,'Review',ReviewOutput,{},'',lambda p:'{"issues":[]}')
        self.assertEqual(reviewed,{'issues':[]})
        bad_review='{"issues":[{"code":"test","severity":"critical","message":"x","source_ids":["invented"]}]}'
        self.assertTrue(structured_role(self.case,'Review',ReviewOutput,{},'',lambda p:bad_review)['failed'])
    def test_minimum_parameters_are_dated_and_not_cap_parameters(self):
        self.assertEqual(self.registry.parameter('深圳','minimum_monthly_wage','2026-08-31')['value'],'2520')
        self.assertEqual(self.registry.parameter('深圳','minimum_monthly_wage','2026-09-01')['value'],'2700')
        self.assertIsNone(self.registry.parameter('深圳','severance_cap','2026-10-01'))
    def test_missing_city_parameters_preserve_formula_and_block_confirm(self):
        result=self.run_case(facts=self.base())
        self.assertIn('severance_cap',result['missing_info']);self.assertIsNone(result['confirmation'])
        self.assertIsNone(next(r for r in result['calculations'] if r['claim_id']=='N')['amount'])
        self.assertEqual(next(r for r in result['calculations'] if r['claim_id']=='notice')['amount'],'9500.00')
    def test_distinct_compensation_notice_salary_and_exclusivity(self):
        # Arithmetic fixture is explicitly synthetic, never part of the manifest.
        original=self.registry.parameter
        def fixture(city,purpose,when):
            return {'id':'SYNTHETIC_TEST_CAP','value':'30000'} if purpose=='severance_cap' else original(city,purpose,when)
        with patch.object(self.registry,'parameter',side_effect=fixture):
            result=self.run_case(facts=self.base())
            amounts={r['claim_id']:r['amount'] for r in result['calculations']}
            self.assertEqual(amounts['N'],'24000.00');self.assertEqual(amounts['notice'],'9500.00')
            with self.assertRaises(CaseInputError): self.run_case(action='confirm',expected_case_version=1,selected_claims=['N','2N'])
            doc=self.run_case(action='confirm',expected_case_version=1,selected_claims=['N','notice'])['document']
            self.assertEqual([r['amount'] for r in doc['requests']],['24000.00','9500.00'])
    def test_article41_does_not_add_notice(self):
        facts=self.base();facts['termination_basis']='article_41'
        result=self.run_case(facts=facts);self.assertNotIn('notice',[c['id'] for c in result['claims']])
    def test_cross_city_checkbox_does_not_determine_a_compensation_parameter_city(self):
        original=self.registry.parameter;cap_calls=[]
        def fixture(city,purpose,when):
            if purpose=='severance_cap':
                cap_calls.append(city);return {'id':'SYNTHETIC_TEST_CAP_'+city,'value':'40000' if city=='深圳' else '30000'}
            return original(city,purpose,when)
        facts=self.base();facts.update(employer_city='深圳',cross_city_resolved=True,monthly_average='50000')
        with patch.object(self.registry,'parameter',side_effect=fixture): result=self.run_case(facts=facts)
        n=next(c for c in result['calculations'] if c['claim_id']=='N')
        self.assertIsNone(n['amount']);self.assertEqual(cap_calls,[])
        self.assertIsNone(n['parameter_regions']['severance_cap'])
        self.assertIn('cross_city_compensation_rule',result['missing_info'])
        self.assertIsNone(result['confirmation'])
        self.assertIn('contract-regulation-2008:a14',{s['id'] for s in result['sources']})
    def test_negation_does_not_establish_illegality_or_evidence(self):
        result=self.run_case(query='在广州不是违法辞退，没有补偿，没有考勤')
        self.assertEqual(result['facts']['termination_basis'],'unknown');self.assertEqual(result['facts']['evidence']['考勤'],'missing')
        self.assertTrue(all(c['status']=='needs_clarification' for c in result['claims']))
    def test_actual_cross_border_blocks_but_hk_identity_alone_does_not(self):
        result=self.run_case(query='我是香港人，在广州工作，单位是港资企业',facts={'employer_city':'广州','dispute_date':'2026-10-01','wages':[{'start':'2026-09-01','end':'2026-09-30','due':'8000','paid':'0'}]})
        self.assertEqual(result['status'],'awaiting_confirmation')
        changed=self.run_case(facts={'actual_cross_border_work':True})
        self.assertEqual(changed['status'],'review_blocked');self.assertIsNone(changed['calculations'][0]['amount'])
    def test_pre2008_requires_review_and_no_simplified_amount(self):
        facts=self.base();facts['start_date']='2007-01-01'
        result=self.run_case(facts=facts);self.assertTrue(any(i['code']=='pre2008' for i in result['review_issues']))
        self.assertIsNone(result['calculations'][0]['amount'])
    def test_cross_city_requires_clarification(self):
        facts=self.base();facts['employer_city']='深圳'
        result=self.run_case(facts=facts);self.assertIn('cross_city_resolved',result['missing_info'])
    def test_company_location_is_not_workplace_and_conflicting_places_require_clarification(self):
        from legal_ai_agent.casework.facts import extract
        self.assertNotIn('workplace',extract('公司在深圳'))
        self.assertEqual(extract('没有在深圳工作，在广州工作')['workplace'],'广州')
        result=self.run_case(query='我在广州工作，也在深圳工作，公司所在地广州')
        self.assertIsNone(result['facts']['workplace'])
        self.assertTrue(any(i['code']=='fact_conflict' for i in result['review_issues']))
    def test_retrieval_failure_keeps_partial_artifacts_and_prevents_document(self):
        with patch('legal_ai_agent.agents.qa_agent.QAAgent.retrieve_case_sources',side_effect=RuntimeError('offline retrieval failure')):
            result=self.run_case(facts=self.base())
        self.assertIsNone(result['confirmation']);self.assertIsNone(result['document']);self.assertTrue(result['failures'])
        self.assertTrue(result['calculations']);self.assertEqual(result['sources'],[])
    def test_model_structure_retry_is_once_and_timeout_is_reported(self):
        self.case.update(sources=[],claims=[])
        calls=[]
        def bad(prompt): calls.append(prompt);return 'invalid json'
        result=model_analysis(self.case,runner=bad)
        self.assertEqual(result['status'],'model_failed');self.assertEqual(len(calls),2)
        self.case['model_calls']=[]
        def timeout(prompt): raise TimeoutError('simulated timeout')
        result=model_analysis(self.case,runner=timeout)
        self.assertEqual(len(self.case['model_calls']),1);self.assertEqual(result['status'],'model_failed')
    def test_unknown_model_citation_is_rejected(self):
        result=model_analysis(self.case,runner=lambda p:'{"arguments":[{"claim_id":"arrears","supporting_evidence":[],"adverse_factors":[],"source_ids":["invented"],"questions":[]}]}')
        self.assertEqual(result['status'],'model_failed')
    def test_document_review_revision_is_bounded(self):
        facts={'workplace':'广州','employer_city':'广州','dispute_date':'2026-10-01','wages':[{'start':'2026-09-01','end':'2026-09-30','due':'8000','paid':'0'}]}
        workflow=CaseWorkflow(self.registry);workflow.run({'facts':facts},self.case)
        with patch.object(workflow.review,'review_document',return_value=[{'code':'test','severity':'critical','message':'still inconsistent'}]) as review:
            result=workflow.run({'action':'confirm','expected_case_version':1,'selected_claims':['arrears']},self.case)['structured']
            self.assertEqual(review.call_count,2);self.assertEqual(result['document']['revision_count'],1)
            self.assertEqual(result['status'],'document_blocked');self.assertNotIn('# 劳动人事争议仲裁申请书',workflow.payload(self.case)['answer'])
    def test_overlap_and_non_finite_money_are_rejected(self):
        for wages in [[{'start':'2026-09-01','end':'2026-09-20','due':'1','paid':'0'},{'start':'2026-09-20','end':'2026-09-30','due':'1','paid':'0'}],[{'start':'2026-09-01','end':'2026-09-30','due':'NaN','paid':'0'}]]:
            with self.assertRaises(ValueError):CaseFacts(wages=wages)
    def test_legacy_tool_and_document_cannot_bypass_case_confirmation(self):
        from legal_ai_agent.tools.labor_tools import calculate_severance_pay
        from legal_ai_agent.agents.doc_agent import DocAgent
        for kind in (None,'severance','notice','notice_pay'):
            result=calculate_severance_pay.invoke({'context':{'calc_type':kind,'salary':8000,'years':3,'reason':'违法辞退'}})
            self.assertIn('案件协同',result);self.assertNotIn('48000',result)
        self.assertIn('确认',DocAgent().run('直接写申请书'))
    def test_model_roles_handoff_and_failed_document_plan_blocks_delivery(self):
        import json
        calls=[]
        laws=['contract-law-2012:a30','labor-law-2018:a50','arbitration-law-2008:a6']
        def runner(prompt):
            if '的Review角色' in prompt: calls.append('Review');return '{"issues":[]}'
            if '的Doc角色' in prompt:
                calls.append('Doc');return json.dumps({'requests':[{'claim_id':'arrears','amount':'7000.10','source_ids':laws}],'evidence_names':[]})
            calls.append('Judge');return json.dumps({'arguments':[{'claim_id':'arrears','supporting_evidence':[],'adverse_factors':['工资材料待补'],'source_ids':laws,'questions':[]}]})
        workflow=CaseWorkflow(self.registry,model_runner=runner)
        facts={'workplace':'广州','employer_city':'广州','dispute_date':'2026-10-01','wages':[{'start':'2026-09-01','end':'2026-09-30','due':'8000.10','paid':'1000'}]}
        workflow.run({'facts':facts},self.case)
        result=workflow.run({'action':'confirm','expected_case_version':1,'selected_claims':['arrears']},self.case)['structured']
        self.assertEqual(result['status'],'draft_ready');self.assertEqual(calls,['Judge','Review','Judge','Review','Doc'])
        self.assertEqual([c['role'] for c in result['model_calls']],['Judge','Review','Doc'])
        with patch.object(workflow.doc,'draft_case',side_effect=ValueError('invalid confirmed amount')):
            failed=workflow.run({'action':'confirm','expected_case_version':1,'selected_claims':['arrears']},self.case)['structured']
        self.assertIsNone(failed['document']);self.assertTrue(failed['failures']);self.assertNotEqual(failed['status'],'draft_ready')
    def test_calendar_rounding_boundaries(self):
        self.assertEqual(str(service_units('2026-01-01','2026-06-29')),'0.5')
        self.assertEqual(str(service_units('2026-01-01','2026-06-30')),'1')
        self.assertEqual(str(service_units('2023-01-01','2025-12-31')),'3')

if __name__=='__main__':unittest.main()
