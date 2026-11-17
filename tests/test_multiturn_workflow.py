import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from legal_ai_agent.memory.memory_manager import ConversationStateStore
from tests.test_conversation_state import WAGES

class MultiTurnWorkflowTest(unittest.TestCase):
    def setUp(self):
        import legal_ai_agent.api.server as server
        self.server=server;self.tmp=tempfile.TemporaryDirectory();self.store=ConversationStateStore(Path(self.tmp.name)/'sessions.json')
        self.patch=patch.object(server,'conversation_store',self.store);self.patch.start();self.env=patch.dict(os.environ,{'CASE_MODEL_ENABLED':'0'});self.env.start()
    def tearDown(self): self.env.stop();self.patch.stop();self.tmp.cleanup()
    def test_real_sse_node_order_and_confirmation_gate(self):
        client=TestClient(self.server.app)
        response=client.post('/api/chat/stream',json={'workflow':'case','session_id':'events','facts':WAGES})
        self.assertEqual(response.status_code,200)
        events=[line[7:] for line in response.text.splitlines() if line.startswith('event: ')]
        self.assertEqual(events[:2],['task_started','task_completed'])
        self.assertIn('confirmation_required',events);self.assertEqual(events[-1],'done')
        self.assertNotIn('"task": "document"',response.text)
    def test_supplemental_information_is_shared_and_negations_are_preserved(self):
        first=self.server._build_chat_payload({'workflow':'case','session_id':'supplement','query':'在广州被突然辞退，没有考勤，没有补偿'})['structured']
        self.assertEqual(first['facts']['evidence']['考勤'],'missing');self.assertEqual(first['facts']['termination_basis'],'unknown')
        self.assertIsNone(first['facts']['workplace'])  # Meeting/dismissal location is not necessarily workplace.
        second=self.server._build_chat_payload({'workflow':'case','session_id':'supplement','facts':{'workplace':'广州','employer_city':'广州','dispute_date':'2026-10-01'}})['structured']
        self.assertEqual(second['facts']['workplace'],'广州');self.assertEqual(second['case_version'],2)
        self.assertEqual(second['facts']['evidence']['考勤'],'missing')
    def test_old_document_mode_requires_new_confirmation(self):
        result=self.server._build_chat_payload({'session_id':'doc','query':'帮我写劳动仲裁申请书','preferred_mode':'doc'})
        self.assertEqual(result['route'],'case');self.assertIsNone(result['structured']['confirmation']);self.assertIsNone(result['structured']['document'])
    def test_no_key_required_for_non_monetary_general_qa_lookup(self):
        result=self.server._build_chat_payload({'session_id':'general','query':'劳动合同法第47条是什么'})
        self.assertIn('经济补偿',result['answer']);self.assertNotIn('工资分配',result['answer'])
    def test_ordinary_exact_city_statute_lookup_honors_explicit_date(self):
        old=self.server._build_chat_payload({'session_id':'general','query':'2025-12-04深圳市员工工资支付条例第22条是什么'})
        new=self.server._build_chat_payload({'session_id':'general','query':'2025-12-05深圳市员工工资支付条例第22条是什么'})
        self.assertIn('sz-wage-2022',old['answer']);self.assertIn('sz-wage-2025',new['answer'])

if __name__=='__main__':unittest.main()
