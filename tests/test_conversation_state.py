import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from legal_ai_agent.memory.memory_manager import ConversationStateStore

WAGES={'workplace':'广州','employer_city':'广州','dispute_date':'2026-10-01',
       'wages':[{'start':'2026-09-01','end':'2026-09-30','due':'8000.10','paid':'1000'}]}

class ConversationStateFlowTest(unittest.TestCase):
    def setUp(self):
        import legal_ai_agent.api.server as server
        self.server=server;self.tmp=tempfile.TemporaryDirectory();self.store=ConversationStateStore(Path(self.tmp.name)/'sessions.json')
        self.patch=patch.object(server,'conversation_store',self.store);self.patch.start()
        self.env=patch.dict(os.environ,{'CASE_MODEL_ENABLED':'0'});self.env.start()
        self.client=TestClient(server.app)
    def tearDown(self): self.env.stop();self.patch.stop();self.tmp.cleanup()
    def chat(self,sid='case',**kwargs):return self.server._build_chat_payload({'workflow':'case','session_id':sid,**kwargs})
    def test_confirm_then_document_uses_decimal_artifact(self):
        first=self.chat(facts=WAGES)['structured']
        self.assertIsNone(first['document']);self.assertTrue(first['confirmation_required'])
        result=self.chat(action='confirm',expected_case_version=1,selected_claims=['arrears'])['structured']
        self.assertEqual(result['status'],'draft_ready');self.assertEqual(result['document']['requests'][0]['amount'],'7000.10')
        self.assertIn('7000.10 元',result['document']['markdown']);self.assertIn('【待补充】',result['document']['markdown'])
        self.assertFalse(result['confirmation']['evidence_verified'])
    def test_revision_invalidates_document_confirmation_and_old_amount(self):
        self.chat(facts=WAGES);self.chat(action='confirm',expected_case_version=1,selected_claims=['arrears'])
        changed=self.chat(facts={'wages':[{'start':'2026-09-01','end':'2026-09-30','due':'9000','paid':'1000'}]})['structured']
        self.assertEqual(changed['case_version'],2);self.assertIsNone(changed['document']);self.assertIsNone(changed['confirmation'])
        self.assertEqual(changed['calculations'][0]['amount'],'8000.00');self.assertTrue(changed['confirmation_required'])
    def test_stale_confirmation_returns_http409_on_both_endpoints(self):
        self.chat(facts=WAGES);self.chat(facts={'dispute_date':'2026-10-02'})
        for endpoint in ('/api/chat','/api/chat/stream'):
            response=self.client.post(endpoint,json={'workflow':'case','session_id':'case','action':'confirm','expected_case_version':1,'selected_claims':['arrears']})
            self.assertEqual(response.status_code,409)
    def test_store_reloads_case_and_new_session_is_isolated(self):
        self.chat(facts=WAGES)
        reloaded=ConversationStateStore(self.store.path)
        self.assertEqual(reloaded.get('case')['case']['case_version'],1)
        self.assertNotIn('case',reloaded.get('new'))
        fresh=self.chat('new')['structured'];self.assertEqual(fresh['facts']['wages'],[])
    def test_evidence_conflict_survives_json_reload_and_blocks_confirmation(self):
        first=self.chat(query='有考勤，没有考勤',facts=WAGES)['structured']
        self.assertTrue(first['fact_conflicts'])
        reloaded=ConversationStateStore(self.store.path)
        with patch.object(self.server,'conversation_store',reloaded):
            blocked=self.chat(action='confirm',expected_case_version=1,selected_claims=['arrears'])['structured']
            self.assertEqual(blocked['status'],'review_blocked')
            self.assertIsNone(blocked['document']);self.assertIsNone(blocked['confirmation'])
            self.assertTrue(any(i['code']=='fact_conflict' for i in blocked['review_issues']))
            resolved=self.chat(facts={'evidence':{'考勤':'missing'}})['structured']
            self.assertEqual(resolved['case_version'],2);self.assertFalse(resolved['fact_conflicts'])
            ready=self.chat(action='confirm',expected_case_version=2,selected_claims=['arrears'])['structured']
            self.assertEqual(ready['status'],'draft_ready')
            self.assertNotIn('考勤',ready['document']['evidence'])
    def test_legacy_inferred_labels_are_unverified_history(self):
        self.store.record_turn('legacy',query='old',route='qa',answer_preview='',facts={'termination_reason':'非法辞退','salary':8000})
        result=self.chat('legacy')['structured']
        self.assertEqual(result['historical_information']['status'],'unverified_legacy')
        self.assertEqual(result['facts']['termination_basis'],'unknown');self.assertIsNone(result['facts']['monthly_average'])
    def test_general_law_qa_is_not_contaminated_by_case(self):
        self.chat(facts=WAGES)
        result=self.server._build_chat_payload({'session_id':'case','query':'劳动法第47条是什么'})
        self.assertEqual(result['route'],'qa');self.assertIn('工资分配',result['answer']);self.assertNotIn('7000.10',result['answer'])
    def test_force_single_module_cannot_bypass_confirmation(self):
        result=self.server._build_chat_payload({'session_id':'forced','query':'突然辞退没有补偿，月薪8000工作3年，能拿多少','mode':'judge','force_mode':True})
        self.assertEqual(result['route'],'case');self.assertIsNone(result['structured']['document'])
        self.assertTrue(all(r['amount'] is None for r in result['structured']['calculations']))
    def test_invalid_fact_patch_is422_and_does_not_change_version(self):
        self.chat(facts=WAGES)
        response=self.client.post('/api/chat',json={'workflow':'case','session_id':'case','facts':{'wages':[{'start':'2026-09-30','end':'2026-09-01','due':'8000','paid':'0'}]}})
        self.assertEqual(response.status_code,422);self.assertEqual(self.store.get('case')['case']['case_version'],1)
    def test_corrupt_state_is_preserved_and_reported_on_both_endpoints(self):
        self.store.path.write_text('{broken',encoding='utf-8')
        for endpoint in ('/api/chat','/api/chat/stream'):
            response=self.client.post(endpoint,json={'workflow':'case','session_id':'case'})
            self.assertEqual(response.status_code,503)
            self.assertIn('原文件已保留',response.json()['detail'])
        self.assertEqual(self.store.path.read_text(encoding='utf-8'),'{broken')
    def test_knowledge_change_invalidates_before_confirmation_and_persists_version(self):
        self.chat(facts=WAGES)
        from legal_ai_agent.casework.workflow import CaseConflict
        with self.store.case_transaction('case') as case:
            case['knowledge_digest']='obsolete-digest'
        with self.assertRaises(CaseConflict): self.chat(action='confirm',expected_case_version=1,selected_claims=['arrears'])
        changed=self.store.get('case')['case']
        self.assertEqual(changed['case_version'],2)
        self.assertIsNone(changed['confirmation']);self.assertIsNone(changed['document'])

if __name__=='__main__':unittest.main()
