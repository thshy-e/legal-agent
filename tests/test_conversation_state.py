import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from legal_ai_agent.memory.memory_manager import ConversationStateStore


class ConversationStateFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = ConversationStateStore(Path(self.tmpdir.name) / "conversation_state.json")

        import legal_ai_agent.api.server as server

        self.server = server
        self.store_patch = patch.object(server, "conversation_store", self.store)
        self.store_patch.start()
        self.agent_patch = patch.object(server, "_run_agent", side_effect=self._fake_run_agent)
        self.agent_patch.start()

    def tearDown(self):
        self.agent_patch.stop()
        self.store_patch.stop()
        self.tmpdir.cleanup()

    def _fake_run_agent(self, route, query, session_id):
        if route == "judge":
            return f"【测试Judge】route={route}; session={session_id}; context={query}"
        if route == "doc":
            return f"【测试Doc】route={route}; session={session_id}; context={query}"
        return f"【测试Agent】route={route}; session={session_id}; context={query}"

    def test_calculation_then_judge_continues_same_session(self):
        first = self.server._build_chat_payload(
            {
                "session_id": "case-1",
                "query": "我月薪8000元，工作3年，被违法辞退，赔偿多少？",
            }
        )

        self.assertEqual(first["route"], "qa")
        self.assertEqual(first["structured"]["calculation"]["amount"], "48000")
        self.assertFalse(first["structured"]["conversation"]["is_continuation"])

        second = self.server._build_chat_payload(
            {
                "session_id": "case-1",
                "query": "那我仲裁胜诉率怎么样？",
            }
        )

        self.assertEqual(second["route"], "judge")
        self.assertTrue(second["structured"]["conversation"]["is_continuation"])
        self.assertTrue(second["structured"]["conversation"]["used_previous_calculation"])
        self.assertEqual(second["structured"]["conversation"]["known_facts"]["salary"], 8000)
        self.assertEqual(second["structured"]["conversation"]["known_facts"]["years"], 3)
        self.assertIn("48000", second["answer"])
        self.assertIn("非法辞退", second["answer"])

    def test_doc_generation_receives_previous_calculation_context(self):
        self.server._build_chat_payload(
            {
                "session_id": "case-doc",
                "query": "我月薪8000元，工作3年，被违法辞退，赔偿多少？",
            }
        )

        result = self.server._build_chat_payload(
            {
                "session_id": "case-doc",
                "query": "帮我写劳动仲裁申请书",
            }
        )

        self.assertEqual(result["route"], "doc")
        self.assertTrue(result["structured"]["conversation"]["used_previous_calculation"])
        self.assertIn("48000", result["answer"])
        self.assertIn("【前文案件状态】", result["answer"])

    def test_new_session_does_not_inherit_old_case(self):
        self.server._build_chat_payload(
            {
                "session_id": "old-case",
                "query": "我月薪8000元，工作3年，被违法辞退，赔偿多少？",
            }
        )

        result = self.server._build_chat_payload(
            {
                "session_id": "new-case",
                "query": "那我仲裁胜诉率怎么样？",
            }
        )

        self.assertEqual(result["route"], "judge")
        self.assertFalse(result["structured"]["conversation"]["is_continuation"])
        self.assertEqual(result["structured"]["conversation"]["known_facts"], {})
        self.assertNotIn("48000", result["answer"])

    def test_store_persists_to_json_and_reloads(self):
        self.store.record_turn(
            "persist-case",
            query="我月薪9000元，工作2年，被违法辞退，赔偿多少？",
            route="qa",
            answer_preview="preview",
            facts={"salary": 9000, "years": 2, "termination_reason": "非法辞退"},
            calculation={"show": True, "status": "complete", "amount": "36000"},
        )

        reloaded = ConversationStateStore(self.store.path)
        state = reloaded.get("persist-case")

        self.assertEqual(state["facts"]["salary"], 9000)
        self.assertEqual(state["facts"]["years"], 2)
        self.assertEqual(state["last_calculation"]["amount"], "36000")
        self.assertEqual(state["last_route"], "qa")

    def test_preferred_judge_does_not_block_explicit_calculation(self):
        result = self.server._build_chat_payload(
            {
                "session_id": "arbitration-calc",
                "preferred_mode": "judge",
                "query": "公司违法解除，月工资8000，工作20年，赔偿多少？",
            }
        )

        self.assertEqual(result["route"], "qa")
        self.assertEqual(result["structured"]["conversation"]["route_reason"], "explicit_calculation_intent")
        self.assertEqual(result["structured"]["calculation"]["amount"], "320000")
        self.assertNotIn("【测试Judge】", result["answer"])

    def test_preferred_judge_does_not_block_explicit_doc_generation(self):
        self.server._build_chat_payload(
            {
                "session_id": "arbitration-doc",
                "query": "我月薪8000元，工作3年，被违法辞退，赔偿多少？",
            }
        )

        result = self.server._build_chat_payload(
            {
                "session_id": "arbitration-doc",
                "preferred_mode": "judge",
                "query": "用以上我输入的内容给我生成仲裁文书",
            }
        )

        self.assertEqual(result["route"], "doc")
        self.assertEqual(result["structured"]["conversation"]["route_reason"], "explicit_doc_intent")
        self.assertIn("【测试Doc】", result["answer"])
        self.assertIn("48000", result["answer"])

    def test_preferred_judge_still_routes_judge_for_judge_intent(self):
        result = self.server._build_chat_payload(
            {
                "session_id": "arbitration-judge",
                "preferred_mode": "judge",
                "query": "胜诉概率多大？",
            }
        )

        self.assertEqual(result["route"], "judge")
        self.assertEqual(result["structured"]["conversation"]["route_reason"], "explicit_judge_intent")
        self.assertIn("【测试Judge】", result["answer"])

    def test_force_mode_keeps_strict_judge_route(self):
        result = self.server._build_chat_payload(
            {
                "session_id": "arbitration-force",
                "mode": "judge",
                "force_mode": True,
                "query": "公司违法解除，月工资8000，工作20年，赔偿多少？",
            }
        )

        self.assertEqual(result["route"], "judge")
        self.assertEqual(result["structured"]["conversation"]["route_reason"], "force_mode:judge")
        self.assertIn("【测试Judge】", result["answer"])


if __name__ == "__main__":
    unittest.main()
