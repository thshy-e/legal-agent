import json
import os
import unittest
from unittest.mock import patch

from legal_ai_agent.casework.fact_checks import employment_statement, date_checks
from legal_ai_agent.casework.models import empty_case
from legal_ai_agent.casework.workflow import CaseWorkflow, CaseConflict
from legal_ai_agent.casework.roles import review_context


@patch.dict(os.environ, {'CASE_MODEL_ENABLED': '0'})
class FactChecksTest(unittest.TestCase):
    def request(self):
        return {'facts': {'workplace': '广州', 'employer_city': '广州',
                          'start_date': '2026-01-01', 'dispute_date': '2026-10-01',
                          'wage_statement': '我目前仍在该单位工作，9月正常工作，工资约定100元。',
                          'wages': [{'start': '2026-09-01', 'end': '2026-09-30', 'due': '100', 'paid': '0'}]}}

    def test_assertive_status_has_literal_provenance_not_evidence_verification(self):
        case = empty_case(); workflow = CaseWorkflow()
        workflow.run(self.request(), case)
        self.assertEqual(case['facts']['employment_status'], 'active')
        self.assertEqual(case['fact_sources']['employment_status']['input_field'], 'wage_statement')
        self.assertIn('仍在该单位工作', case['fact_sources']['employment_status']['statement'])
        self.assertFalse(case['fact_sources']['employment_status']['evidence_verified'])
        context = review_context(case)
        self.assertEqual(context['facts']['employment_status'], 'active')
        self.assertTrue(all(check['passed'] for check in context['date_checks']))

    def test_questions_hypotheticals_negations_and_historical_status_are_not_assertions(self):
        for text in ('如果我仍在职', '我仍在职？', '我仍在职吗', '目前仍在该单位工作？',
                     '我不是仍在职', '我曾经仍在职', '我不是没有离职', '公司说我已离职',
                     '我仍在职的说法不准确', '我仍在职还是已离职'):
            with self.subTest(text=text): self.assertIsNone(employment_statement(text)[0])
        self.assertEqual(employment_statement('我已离职')[0], 'terminated')

    def test_contradictory_status_blocks_and_survives_reload_until_correction(self):
        request = self.request(); request['facts']['employment_status'] = 'terminated'
        case = empty_case(); workflow = CaseWorkflow(); workflow.run(request, case)
        self.assertEqual(case['status'], 'review_blocked')
        self.assertTrue(any(i['code'] == 'employment_statement_conflict' for i in case['review_issues']))
        case = json.loads(json.dumps(case)); workflow.run({'query': '继续'}, case)
        self.assertEqual(case['status'], 'review_blocked')
        workflow.run({'facts': {'wage_statement': '我已离职，9月正常工作，尚欠100元。'}}, case)
        self.assertEqual(case['status'], 'awaiting_confirmation')

    def test_amended_status_invalidates_document_and_unasserted_replacement_clears_derived_value(self):
        case = empty_case(); workflow = CaseWorkflow(); workflow.run(self.request(), case)
        workflow.run({'action': 'confirm', 'expected_case_version': 1, 'selected_claims': ['arrears']}, case)
        self.assertIn('在职状态（申请人陈述，待举证）：仍在职', case['document']['markdown'])
        workflow.run({'facts': {'wage_statement': '仅核对9月工资，在职状态尚不确定。'}}, case)
        self.assertEqual(case['facts']['employment_status'], 'unknown')
        self.assertIsNone(case['document']); self.assertIsNone(case['confirmation'])
        with self.assertRaises(CaseConflict):
            workflow.run({'action': 'confirm', 'expected_case_version': 1, 'selected_claims': ['arrears']}, case)

    def test_calendar_ordering_distinguishes_october_from_january_without_a_limitations_verdict(self):
        facts = self.request()['facts']; checks = date_checks(facts)
        check = next(c for c in checks if c['left_field'] == 'start_date' and c['right_field'] == 'dispute_date')
        self.assertTrue(check['passed']); self.assertIn('不判断时效', check['scope'])
        facts['dispute_date'] = '2025-12-31'; self.assertFalse(date_checks(facts)[0]['passed'])
        case = empty_case(); CaseWorkflow().run({'facts': facts}, case)
        self.assertEqual(case['status'], 'review_blocked')
        self.assertTrue(any(i['code'] == 'dispute_before_employment' for i in case['review_issues']))

    def test_active_status_and_past_end_date_require_clarifying_employment_period(self):
        request = self.request(); request['facts']['end_date'] = '2026-09-30'
        case = empty_case(); CaseWorkflow().run(request, case)
        self.assertTrue(any(i['code'] == 'employment_end_conflict' for i in case['review_issues']))
        self.assertFalse(case['status'] == 'draft_ready')


if __name__ == '__main__': unittest.main()
