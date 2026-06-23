import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from legal_ai_agent.memory.memory_manager import ConversationStateStore


class MultiTurnWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = ConversationStateStore(Path(self.tmpdir.name) / "conversation_state.json")

        import legal_ai_agent.api.server as server

        self.server = server
        self.store_patch = patch.object(server, "conversation_store", self.store)
        self.store_patch.start()
        self.agent_patch = patch.object(server, "_run_agent", side_effect=self._fake_run_agent)
        self.mock_run_agent = self.agent_patch.start()

    def tearDown(self):
        self.agent_patch.stop()
        self.store_patch.stop()
        self.tmpdir.cleanup()

    def _fake_run_agent(self, route, query, session_id):
        return f"ROUTE={route}\nSESSION={session_id}\nQUERY={query}"

    def _chat(self, session_id, query, **extra):
        return self.server._build_chat_payload({"session_id": session_id, "query": query, **extra})

    def assert_clean_general_law_answer(self, payload):
        text = payload["answer"]
        self.assertNotIn("【前文案件状态】", text)
        self.assertNotIn("【上次赔偿计算】", text)
        self.assertNotIn("60000", text)
        self.assertNotIn("300000", text)
        self.assertNotIn("2N赔偿", text)
        self.assertNotIn("计算公式", text)
        timeline_text = str(payload["structured"].get("timeline", ""))
        self.assertNotIn("2N赔偿", timeline_text)
        self.assertNotIn("计算公式", timeline_text)

    def test_full_session_mixes_all_features_without_polluting_general_qa(self):
        session_id = "mixed-flow"

        calc = self._chat(session_id, "月薪10000，工作3年，被公司突然辞退且无补偿，能拿多少？")
        self.assertEqual(calc["route"], "qa")
        self.assertEqual(calc["structured"]["calculation"]["amount"], "60000")
        self.assertEqual(calc["structured"]["conversation"]["route_reason"], "explicit_calculation_intent")

        general_law = self._chat(session_id, "劳动法第68条是什么")
        self.assertEqual(general_law["route"], "qa")
        self.assertEqual(general_law["structured"]["conversation"]["route_reason"], "router:qa")
        self.assert_clean_general_law_answer(general_law)

        case_law = self._chat(session_id, "结合我上面的情况，劳动合同法第47条怎么适用？")
        self.assertEqual(case_law["route"], "qa")
        self.assertIn("【前文案件状态】", case_law["answer"])
        self.assertIn("60000", case_law["answer"])

        judge = self._chat(session_id, "那我这个案子下一步怎么办？")
        self.assertEqual(judge["route"], "judge")
        self.assertIn("【前文案件状态】", judge["answer"])
        self.assertIn("60000", judge["answer"])

        doc = self._chat(session_id, "用以上内容生成仲裁申请书", preferred_mode="judge")
        self.assertEqual(doc["route"], "doc")
        self.assertEqual(doc["structured"]["conversation"]["route_reason"], "explicit_doc_intent")
        self.assertIn("【前文案件状态】", doc["answer"])
        self.assertIn("60000", doc["answer"])

        risk = self._chat(session_id, "公司这样处理有什么法律风险？")
        self.assertEqual(risk["route"], "risk")
        self.assertIn("【前文案件状态】", risk["answer"])
        self.assertIn("60000", risk["answer"])

    def test_new_session_general_law_does_not_inherit_old_case(self):
        self._chat("old-session", "月薪5000，工作30年，被公司突然辞退且无补偿，能拿多少？")

        fresh = self._chat("fresh-session", "劳动合同法第47条是什么")

        self.assertEqual(fresh["route"], "qa")
        self.assertFalse(fresh["structured"]["conversation"]["is_continuation"])
        self.assert_clean_general_law_answer(fresh)

    def test_preferred_mode_and_force_mode_behaviour_in_mixed_session(self):
        preferred_calc = self._chat(
            "preference-flow",
            "公司违法解除，月工资8000，工作20年，赔偿多少？",
            preferred_mode="judge",
        )
        self.assertEqual(preferred_calc["route"], "qa")
        self.assertEqual(preferred_calc["structured"]["calculation"]["amount"], "320000")

        preferred_doc = self._chat(
            "preference-flow",
            "用以上内容生成仲裁文书",
            preferred_mode="judge",
        )
        self.assertEqual(preferred_doc["route"], "doc")
        self.assertIn("320000", preferred_doc["answer"])

        forced = self._chat(
            "preference-flow",
            "公司违法解除，月工资8000，工作20年，赔偿多少？",
            mode="judge",
            force_mode=True,
        )
        self.assertEqual(forced["route"], "judge")
        self.assertEqual(forced["structured"]["conversation"]["route_reason"], "force_mode:judge")
        self.assertIn("ROUTE=judge", forced["answer"])

    def test_missing_info_then_supplemental_numbers_calculates_from_session_state(self):
        missing = self._chat("supplement-flow", "我被辞退了，能拿多少？")
        self.assertEqual(missing["route"], "qa")
        self.assertEqual(missing["structured"]["calculation"]["status"], "missing_info")

        completed = self._chat("supplement-flow", "月薪8000，工作3年")
        self.assertEqual(completed["route"], "qa")
        self.assertEqual(completed["structured"]["calculation"]["amount"], "48000")
        self.assertTrue(completed["structured"]["conversation"]["used_previous_calculation"])


if __name__ == "__main__":
    unittest.main()
