"""Only live requests enter model analysis; excluded choices remain visible."""
import json
import os
import unittest
from unittest.mock import patch

from legal_ai_agent.casework.models import empty_case
from legal_ai_agent.casework.roles import model_analysis, analysis_context
from legal_ai_agent.casework.workflow import CaseWorkflow, CaseInputError


def payload(prompt):
    return json.JSONDecoder().raw_decode(prompt.split('\nDATA=', 1)[1])[0]


def arguments(ids):
    return json.dumps({'arguments': [{'claim_id': ident, 'supporting_evidence': [],
                       'adverse_factors': [], 'source_ids': [], 'questions': []} for ident in ids]})


class ClaimRoleScopeTest(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'CASE_MODEL_ENABLED': '0'})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def facts(self, basis='article_41'):
        return {'workplace': '广州', 'employer_city': '广州', 'dispute_date': '2026-10-15',
                'start_date': '2020-01-01', 'end_date': '2026-09-30', 'employment_status': 'terminated',
                'initiator': 'employer', 'termination_basis': basis, 'termination_reason': '用户陈述的解除理由，待核验',
                'monthly_average': '8000', 'previous_month_wage': '9500', 'written_notice_30': False,
                'layoff_conditions': True, 'layoff_procedure': True, 'protected_status': False,
                'article40_conditions': True, 'article40_category': 'incompetence'}

    def test_excluded_alternative_is_visible_but_not_a_required_model_argument(self):
        prompts = []
        def runner(prompt):
            if '的Review角色' in prompt: return '{"issues":[]}'
            prompts.append(prompt)
            return arguments(payload(prompt)['required_claim_ids'])
        case = empty_case()
        CaseWorkflow(model_runner=runner).run({'facts': self.facts()}, case)
        self.assertEqual([a['claim_id'] for a in case['analysis']['arguments']], ['N'])
        self.assertEqual(next(c['status'] for c in case['claims'] if c['id'] == '2N'), 'not_selected')
        self.assertEqual(payload(prompts[0])['required_claim_ids'], ['N'])
        self.assertEqual(payload(prompts[0])['excluded_claims'][0]['id'], '2N')
        self.assertIn('severance_cap', case['missing_info'])
        self.assertIsNone(case['confirmation'])

    def test_omitted_active_request_is_corrected_once_with_specific_missing_id(self):
        case = empty_case(); CaseWorkflow().run({'facts': self.facts('article_40')}, case)
        prompts = []
        def runner(prompt):
            prompts.append(prompt)
            return arguments(['N'] if len(prompts) == 1 else ['N', 'notice'])
        result = model_analysis(case, runner)
        self.assertEqual(result['status'], 'model_augmented')
        self.assertEqual(len(prompts), 2)
        self.assertIn('缺少=["notice"]', prompts[1])
        self.assertEqual(analysis_context(case)['required_claim_ids'], ['N', 'notice'])

    def test_inventing_an_excluded_request_still_fails_after_one_correction(self):
        case = empty_case(); CaseWorkflow().run({'facts': self.facts()}, case)
        result = model_analysis(case, lambda prompt: arguments(['N', '2N']))
        self.assertEqual(result['status'], 'model_failed')
        self.assertEqual(len(case['model_calls']), 2)

    def test_zero_balance_skips_models_and_cannot_generate_a_zero_request(self):
        case = empty_case()
        def forbidden(prompt): raise AssertionError('No request remains for model analysis')
        workflow = CaseWorkflow(model_runner=forbidden)
        workflow.run({'facts': {'workplace': '深圳', 'employer_city': '深圳', 'dispute_date': '2026-10-15',
                               'wages': [{'start': '2026-09-01', 'end': '2026-09-30', 'due': '100', 'paid': '100'}]}}, case)
        self.assertEqual(case['status'], 'no_supported_claim')
        self.assertEqual(case['analysis']['status'], 'not_applicable')
        self.assertEqual(case['model_calls'], [])
        self.assertEqual(case['failures'], [])
        with self.assertRaises(CaseInputError):
            workflow.run({'action': 'confirm', 'expected_case_version': 1, 'selected_claims': ['arrears']}, case)
        self.assertIsNone(case['document'])

    def test_no_active_request_does_not_hide_existing_critical_rules(self):
        case = empty_case()
        CaseWorkflow(model_runner=lambda prompt: self.fail('Model should be skipped')).run(
            {'facts': {'workplace': '广州', 'employer_city': '广州', 'dispute_date': '2026-10-15',
                       'actual_cross_border_work': True,
                       'wages': [{'start': '2026-09-01', 'end': '2026-09-30', 'due': '100', 'paid': '100'}]}}, case)
        self.assertEqual(case['status'], 'review_blocked')
        self.assertTrue(any(i['code'] == 'cross_border' and i['severity'] == 'critical' for i in case['review_issues']))
        self.assertIsNone(case['document'])


if __name__ == '__main__': unittest.main()
