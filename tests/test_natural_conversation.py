"""Conversation behavior is independent of the frozen case benchmark."""
import copy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from legal_ai_agent.agents.qa_agent import QAAgent
from legal_ai_agent.memory.memory_manager import ConversationStateStore
from tests.test_conversation_state import WAGES


class NaturalConversationTest(unittest.TestCase):
    def setUp(self):
        import legal_ai_agent.api.server as server
        self.server = server
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ConversationStateStore(Path(self.tmp.name)/'state.json')
        self.agent = QAAgent()
        self.llm = Mock()
        self.agent.balanced_llm = self.llm
        self.patches = [patch.object(server,'conversation_store',self.store),
                        patch.object(server,'qa',self.agent),patch.dict(os.environ,{'CASE_MODEL_ENABLED':'0'})]
        for p in self.patches: p.start()
        self.client = TestClient(server.app)

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()

    def chat(self, query, sid='natural', **extra):
        return self.server._build_chat_payload({'query':query,'session_id':sid,**extra})

    def grounded(self, messages):
        packet = json.loads(messages[-1].content.split('本轮可信检索与只读工具数据：')[1])
        source = packet['sources'][0]['id']
        return SimpleNamespace(content=json.dumps({'answer':'可以继续结合这条规定理解。['+source+']','source_ids':[source]},ensure_ascii=False),response_metadata={})

    def test_smalltalk_never_retrieves_or_calls_model(self):
        with patch('legal_ai_agent.casework.knowledge.KnowledgeRegistry',side_effect=AssertionError('must not retrieve')):
            for query in ('你好','谢谢','我有点担心'):
                result = self.chat(query)
                self.assertEqual(result['structured']['presentation']['kind'],'conversation')
                self.assertEqual(result['structured']['sources'],[])
                self.assertNotIn('metrics',result['structured'])
        self.llm.invoke.assert_not_called()

    def test_concepts_do_not_start_cases_even_in_legacy_case_workspace(self):
        self.llm.invoke.side_effect = self.grounded
        for query in ('N+1是什么意思？','赔偿金的计算公式是什么？','仲裁申请书是什么？','一般欠薪怎么算？'):
            result = self.chat(query,workflow='case')
            self.assertEqual(result['structured']['presentation']['kind'],'conversation',query)
        self.assertNotIn('case',self.store.get('natural'))

    def test_explicit_personal_operation_starts_case_and_preserves_confirmation_gate(self):
        for sid,query in (('a','按我的情况算一下'),('b','请分析我的案件'),('c','请帮我生成仲裁申请书')):
            result = self.chat(query,sid=sid)
            self.assertEqual(result['structured']['presentation']['kind'],'case')
            self.assertIsNone(result['structured']['confirmation'])
            self.assertIsNone(result['structured']['document'])

    def test_probation_followups_receive_actual_preceding_dialogue(self):
        self.llm.invoke.side_effect = self.grounded
        questions = ['试用期也要签劳动合同吗？','公司说转正才签呢？','为什么？','该怎么办？']
        for query in questions:
            result = self.chat(query)
            self.assertEqual(result['structured']['status'],'completed')
        last = self.llm.invoke.call_args.args[0]
        self.assertEqual([m.content for m in last if m.type=='human'][:-1],questions[:-1])
        self.assertEqual(len([m for m in last if m.type=='ai']),3)
        turns = self.store.get('natural')['turns']
        self.assertEqual(turns[0]['answer'],turns[1]['answer'])
        self.assertEqual(turns[-1]['query'],'该怎么办？')
        self.assertNotIn('case',self.store.get('natural'))

    def test_exact_lookup_is_recorded_and_followup_retains_article_identity(self):
        first = self.chat('劳动法第47条是什么')
        self.llm.invoke.side_effect = self.grounded
        second = self.chat('这一条是什么意思？')
        self.assertIn('工资分配',first['answer'])
        self.assertTrue(second['structured']['conversation']['is_continuation'])
        packet = self.llm.invoke.call_args.args[0][-1].content
        self.assertIn('labor-law-2018:a47',packet)
        self.assertNotIn('contract-law-2012:a47',packet)

    def test_second_point_uses_full_answer_not_240_character_preview(self):
        answer = '1. '+('完整背景。'*100)+'\n2. 保存工资流水。'
        self.store.record_turn('natural',query='需要哪些材料？',route='qa',answer_preview=answer[:240],answer=answer,
                               metadata={'retrieval_query':'劳动争议证据'})
        self.llm.invoke.side_effect = self.grounded
        self.chat('第二点什么意思？')
        messages = self.llm.invoke.call_args.args[0]
        self.assertEqual(messages[2].content,answer)

    def test_numbered_followup_is_bound_to_the_actual_second_passage(self):
        from legal_ai_agent.conversation import referenced_passage
        text = '第一，保存劳动合同。第二，保存催款消息。根据举证规则，单位须提供其掌握的证据。'
        self.store.record_turn('natural',query='分两点说',route='qa',answer_preview='',answer=text,
                               metadata={'retrieval_query':'欠薪材料'})
        self.assertTrue(referenced_passage('第二点什么意思',self.store.recent_dialogue('natural')).startswith('第二，保存催款消息'))
        self.llm.invoke.side_effect = self.grounded
        self.chat('第二点什么意思？')
        packet = json.loads(self.llm.invoke.call_args.args[0][-1].content.split('本轮可信检索与只读工具数据：')[1])
        self.assertTrue(packet['referenced_passage'].startswith('第二，保存催款消息'))
        result = self.chat('第三点什么意思？')
        self.assertEqual(result['structured']['status'],'clarification')

    def test_missing_antecedent_clarifies_without_model(self):
        result = self.chat('这一条是什么意思？')
        self.assertEqual(result['structured']['status'],'clarification')
        self.assertIn('哪条',result['answer'])
        self.llm.invoke.assert_not_called()

    def test_case_explanation_and_ambiguous_wage_revision_are_read_only(self):
        self.chat('',workflow='case',facts=WAGES)
        self.chat('',workflow='case',action='confirm',expected_case_version=1,selected_claims=['arrears'])
        before = copy.deepcopy(self.store.get('natural')['case'])
        self.llm.invoke.side_effect = self.grounded
        result = self.chat('为什么需要工资流水？',workflow='case')
        self.assertTrue(result['structured']['conversation']['read_case'])
        self.assertEqual(result['structured']['presentation']['kind'],'conversation')
        self.assertEqual(self.store.get('natural')['case'],before)
        result = self.chat('工资改成9000元，重新算')
        self.assertEqual(result['structured']['status'],'clarification')
        self.assertEqual(self.store.get('natural')['case'],before)

    def test_general_new_topic_does_not_receive_case_or_old_salary(self):
        self.chat('',workflow='case',facts=WAGES)
        self.store.record_turn('natural',query='我的工资是76543元',route='qa',answer_preview='',answer='旧案内容')
        self.llm.invoke.side_effect = self.grounded
        result = self.chat('试用期最长多久？')
        self.assertFalse(result['structured']['conversation']['read_case'])
        messages = '\n'.join(m.content for m in self.llm.invoke.call_args.args[0][1:])
        self.assertNotIn('76543',messages)
        self.assertNotIn('8000.10',messages)
        self.assertNotIn('旧案内容',messages)

    def test_precise_text_revision_invalidates_old_amount_and_document(self):
        self.chat('',workflow='case',facts=WAGES)
        self.chat('',workflow='case',action='confirm',expected_case_version=1,selected_claims=['arrears'])
        result = self.chat('2026年9月应付工资改为9000.10元，重新算')['structured']
        self.assertEqual(result['presentation']['kind'],'case')
        self.assertEqual(result['case_version'],2)
        self.assertEqual(result['calculations'][0]['amount'],'8000.10')
        self.assertIsNone(result['document'])
        self.assertIsNone(result['confirmation'])
        self.assertEqual(result['fact_sources']['wages']['source'],'user_text_extraction')

    def test_multiple_wage_periods_require_clarification_and_hypotheticals_do_not_mutate(self):
        facts = copy.deepcopy(WAGES)
        facts['wages'].append({'start':'2026-08-01','end':'2026-08-31','due':'3000','paid':'0'})
        self.chat('',workflow='case',facts=facts)
        before = copy.deepcopy(self.store.get('natural')['case'])
        self.assertEqual(self.chat('应付工资改为9000元，重新算')['structured']['status'],'clarification')
        self.assertEqual(self.store.get('natural')['case'],before)
        self.llm.invoke.side_effect = self.grounded
        self.chat('如果应付工资改为9000元会怎么样？')
        self.assertEqual(self.store.get('natural')['case'],before)

    def test_json_reload_and_new_session_isolation(self):
        self.chat('劳动合同法第47条是什么')
        reloaded = ConversationStateStore(self.store.path)
        self.llm.invoke.side_effect = self.grounded
        with patch.object(self.server,'conversation_store',reloaded):
            self.assertTrue(self.chat('这一条是什么意思？')['structured']['conversation']['is_continuation'])
            self.assertEqual(self.chat('这一条是什么意思？',sid='another')['structured']['status'],'clarification')

    def test_stateless_request_does_not_create_shared_default_session(self):
        self.server._build_chat_payload({'query':'你好'})
        self.assertFalse(self.store.path.exists())

    def test_history_is_bounded_and_legacy_summary_labelled(self):
        for i in range(9):
            self.store.record_turn('natural',query=str(i),route='qa',answer_preview='旧摘要')
        history = self.store.recent_dialogue('natural')
        self.assertEqual(len(history),6)
        self.assertTrue(all(t['legacy_summary'] for t in history))
        self.store.record_turn('natural',query='long',route='qa',answer_preview='',answer='x'*14000)
        history = self.store.recent_dialogue('natural')
        self.assertLessEqual(sum(len(t['query'])+len(t['answer']) for t in history),12000)
        self.assertTrue(history[-1]['truncated'])

    def test_model_timeout_no_retry_and_case_unchanged(self):
        self.chat('',workflow='case',facts=WAGES)
        before = copy.deepcopy(self.store.get('natural')['case'])
        self.llm.invoke.side_effect = TimeoutError('offline timeout')
        result = self.chat('为什么需要工资流水？')
        self.assertEqual(result['structured']['status'],'model_failed')
        self.assertEqual(self.llm.invoke.call_count,1)
        self.assertEqual(self.store.get('natural')['case'],before)

    def test_retrieval_failure_has_no_empty_report_or_model_call(self):
        with patch('legal_ai_agent.casework.knowledge.KnowledgeRegistry',side_effect=RuntimeError('offline')):
            result = self.chat('试用期多久？')
        self.assertEqual(result['structured']['status'],'retrieval_failed')
        self.assertNotIn('metrics',result['structured'])
        self.llm.invoke.assert_not_called()

    def test_invented_source_is_rejected_with_only_one_correction(self):
        self.llm.invoke.return_value = SimpleNamespace(content=json.dumps({'answer':'可以。[fake:a999]','source_ids':['fake:a999']}),response_metadata={})
        result = self.chat('试用期多久？')
        self.assertEqual(result['structured']['status'],'invalid_output')
        self.assertEqual(result['structured']['sources'],[])
        self.assertEqual(self.llm.invoke.call_count,2)
        self.assertNotIn('fake',result['answer'])

    def test_unsupported_limitation_or_article_is_not_delivered(self):
        self.llm.invoke.return_value = SimpleNamespace(content=json.dumps({
            'answer':'时效一般从离职后一年起算。[contract-law-2012:a82]',
            'source_ids':['contract-law-2012:a82']}),response_metadata={})
        result = self.chat('试用期签合同问题')
        self.assertEqual(result['structured']['status'],'invalid_output')
        self.assertNotIn('离职后一年',result['answer'])

    def test_colloquial_this_article_is_not_mistaken_for_article_one(self):
        from legal_ai_agent.casework.knowledge import KnowledgeRegistry
        records = [KnowledgeRegistry().by_id('labor-law-2018:a47',None,'2026-10-26')]
        answer = self.agent._validate(json.dumps({'answer':'这一条讲的是工资分配自主权。','source_ids':['labor-law-2018:a47']}),records)
        self.assertIn('这一条',answer.answer)
        with self.assertRaises(ValueError):
            self.agent._validate(json.dumps({'answer':'须适用第48、49、50条。','source_ids':['labor-law-2018:a47']}),records)

    def test_sse_starts_lightweight_then_returns_presentation(self):
        response = self.client.post('/api/chat/stream',json={'session_id':'stream','query':'你好'})
        self.assertEqual(response.status_code,200)
        events = [line[7:] for line in response.text.splitlines() if line.startswith('event: ')]
        self.assertEqual(events[0],'thinking')
        self.assertNotIn('task_started',events)
        self.assertIn('"kind": "conversation"',response.text)
        self.assertEqual(events[-1],'done')


if __name__ == '__main__': unittest.main()
