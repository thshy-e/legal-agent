import unittest


class SmokeTest(unittest.TestCase):
    def test_asgi_app_imports(self):
        from app import app

        self.assertEqual(app.version, "2.0.0")

    def test_router_defaults_to_qa(self):
        from legal_ai_agent.agents.router_agent import RouterAgent

        self.assertEqual(RouterAgent().route("试用期最长多久"), "qa")

    def test_calculation_fast_path(self):
        from legal_ai_agent.tools.calculator import calculate_from_query

        result = calculate_from_query("我月工资10000，工作3年，被违法辞退，赔偿金是多少？")
        self.assertIsNotNone(result)
        self.assertIn("案件协同", result)

    def test_sudden_dismissal_without_compensation_requires_conditions(self):
        from legal_ai_agent.tools.calculator import calculate_from_query

        result = calculate_from_query("月薪8000，工作3年，被公司突然辞退且无补偿，能拿多少？")
        self.assertIsNotNone(result)
        self.assertIn("不直接认定2N", result)
        self.assertNotIn("48000", result)
    def test_legacy_fact_calculation_does_not_promote_legal_labels(self):
        from legal_ai_agent.api.server import _calculation_context_from_facts
        from legal_ai_agent.tools.calculator import calculate_compensation
        context=_calculation_context_from_facts({'salary':8000,'years':3,'termination_reason':'非法辞退'},'重新算一下2N金额')
        self.assertTrue(context['conditional_only']);self.assertNotIn('48000',calculate_compensation(context))

    def test_mojibake_repair(self):
        from legal_ai_agent.api.server import _repair_mojibake

        broken = "试用期最长多久？".encode("utf-8").decode("cp1252")
        self.assertEqual(_repair_mojibake(broken), "试用期最长多久？")


if __name__ == "__main__":
    unittest.main()
