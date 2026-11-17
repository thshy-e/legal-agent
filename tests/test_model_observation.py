"""Regress real SDK rejection semantics and incomplete Review responses."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from openai import LengthFinishReasonError
from openai.types.chat import ChatCompletion
from legal_ai_agent.casework.models import empty_case
from legal_ai_agent.casework.model_observation import observe_exception
from legal_ai_agent.casework.roles import ReviewOutput, structured_role, model_analysis


def length_error():
    completion=ChatCompletion.model_validate({
        'id':'synthetic-length','created':0,'object':'chat.completion','model':'reported-model',
        'choices':[{'index':0,'finish_reason':'length','message':{'role':'assistant','content':'{"issues":['}}],
        'usage':{'prompt_tokens':100,'completion_tokens':40,'total_tokens':140,
                 'prompt_tokens_details':{'cached_tokens':32},'completion_tokens_details':{'reasoning_tokens':30}}})
    return LengthFinishReasonError(completion=completion)


def message(content,finish='stop'):
    return SimpleNamespace(content=content,response_metadata={'model_name':'reported-model','finish_reason':finish},
                           usage_metadata={'input_tokens':10,'output_tokens':5,'total_tokens':15})


class ModelObservationTest(unittest.TestCase):
    def test_sdk_rejection_retains_reported_metadata_and_does_not_become_a_success(self):
        case=empty_case();prompts=[]
        def runner(prompt):
            prompts.append(prompt)
            if len(prompts)==1:raise length_error()
            return message('{"issues":[]}')
        result=structured_role(case,'Review',ReviewOutput,{'facts':{},'sources':[]},'',runner)
        self.assertEqual(result,{'issues':[]});self.assertEqual(len(prompts),2)
        first=case['model_calls'][0]
        self.assertEqual(first['status'],'failed');self.assertEqual(first['actual_model'],'reported-model')
        self.assertEqual(first['metadata_source'],'sdk_exception_completion')
        self.assertEqual(first['finish_reason'],'length');self.assertEqual(first['usage']['total_tokens'],140)
        self.assertEqual(first['usage']['input_token_details']['cache_read'],32)
        self.assertEqual(first['usage']['output_token_details']['reasoning'],30)
        self.assertEqual(first['output'],'{"issues":[')
        self.assertIn('output_truncated',prompts[1])

    def test_repeated_sdk_length_rejection_stops_at_two_and_keeps_failure(self):
        case=empty_case()
        def runner(prompt):raise length_error()
        result=structured_role(case,'Review',ReviewOutput,{'facts':{},'sources':[]},'',runner)
        self.assertTrue(result['failed']);self.assertEqual(len(case['model_calls']),2)
        self.assertTrue(all(c['status']=='failed' and c['usage']['total_tokens']==140 for c in case['model_calls']))
        self.assertEqual(case['failures'][0]['stage'],'Review')

    def test_valid_json_with_length_finish_is_still_incomplete(self):
        case=empty_case();calls=[]
        def runner(prompt):
            calls.append(prompt)
            return message('{"issues":[]}', 'length' if len(calls)==1 else 'stop')
        structured_role(case,'Review',ReviewOutput,{'facts':{},'sources':[]},'',runner)
        self.assertEqual([c['status'] for c in case['model_calls']],['failed','ok'])
        self.assertEqual(case['model_calls'][0]['finish_reason'],'length')

    def test_missing_fields_receive_precise_feedback_and_critical_is_preserved_after_correction(self):
        case=empty_case();prompts=[]
        incomplete={'code':'test','severity':'critical','category':'fact_conflict','message':'PRIVATE_CASE_TEXT'}
        complete={**incomplete,'source_ids':[], 'fact_excerpts':[
            {'field':'start_date','quote':'2026-11-01'}, {'field':'wages.0.start','quote':'2026-09-01'}]}
        data={'facts':{'start_date':'2026-11-01','wages':[{'start':'2026-09-01'}]},'sources':[]}
        def runner(prompt):
            prompts.append(prompt)
            return message(json.dumps({'issues':[incomplete if len(prompts)==1 else complete]}))
        result=structured_role(case,'Review',ReviewOutput,data,'',runner)
        self.assertEqual(result['issues'][0]['severity'],'critical')
        self.assertIn('issues.0.source_ids',prompts[1]);self.assertIn('Field required',prompts[1])
        self.assertNotIn('PRIVATE_CASE_TEXT',prompts[1])
        self.assertEqual([c['status'] for c in case['model_calls']],['failed','ok'])

    def test_missing_fields_are_not_auto_filled_and_unknown_usage_is_not_zero(self):
        case=empty_case();incomplete={'issues':[{'code':'test','severity':'critical','message':'incomplete'}]}
        result=structured_role(case,'Review',ReviewOutput,{'facts':{},'sources':[]},'',lambda _:json.dumps(incomplete))
        self.assertTrue(result['failed']);self.assertEqual(len(case['model_calls']),2)
        record={};observe_exception(record,SimpleNamespace(completion={
            'model':None,'usage':{'completion_tokens':7},'choices':[{'finish_reason':'length'}]}))
        self.assertEqual(record['actual_model'],'unknown');self.assertIsNone(record['usage'])
        self.assertEqual(record['raw_usage'],{'completion_tokens':7})
        untouched={'actual_model':'unknown','usage':None}
        observe_exception(untouched,TimeoutError())
        self.assertEqual(untouched,{'actual_model':'unknown','usage':None})

    def test_judge_sdk_failure_uses_the_same_metadata_and_retry_bound(self):
        case=empty_case();case['claims']=[{'id':'arrears','status':'conditional','laws':['test-law']}]
        case['sources']=[{'id':'test-law','kind':'law'}];calls=[]
        answer={'arguments':[{'claim_id':'arrears','supporting_evidence':[],'adverse_factors':[],
                              'source_ids':['test-law'],'questions':[]}]}
        def runner(prompt):
            calls.append(prompt)
            if len(calls)==1:raise length_error()
            return message(json.dumps(answer))
        result=model_analysis(case,runner)
        self.assertEqual(result['status'],'model_augmented');self.assertEqual(len(calls),2)
        self.assertEqual(case['model_calls'][0]['status'],'failed')
        self.assertEqual(case['model_calls'][0]['actual_model'],'reported-model')
        self.assertEqual(case['model_calls'][0]['usage']['total_tokens'],140)


if __name__=='__main__':unittest.main()
