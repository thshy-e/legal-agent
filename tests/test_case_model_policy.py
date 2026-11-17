import os
import unittest
from unittest.mock import patch

from legal_ai_agent.casework.models import empty_case
from legal_ai_agent.casework.model_policy import profile_digest, role_profile
from legal_ai_agent.casework.roles import _structured_model_runner
from legal_ai_agent.casework.workflow import CaseWorkflow, CaseConflict


class CaseModelPolicyTest(unittest.TestCase):
    def test_review_profile_is_independent_and_provider_receives_bounded_options(self):
        with patch.dict(os.environ, {'CASE_REVIEW_MODEL': 'qwen3.8-max'}), \
             patch('legal_ai_agent.llm.qwen_llm.get_llm') as factory:
            _structured_model_runner('Review')
            self.assertEqual(role_profile('Judge')['requested_model'], 'qwen-plus')
            self.assertEqual(role_profile('Doc')['requested_model'], 'qwen-plus')
            self.assertEqual(factory.call_args.kwargs['model_name'], 'qwen3.8-max')
            self.assertEqual(factory.call_args.kwargs['timeout'], 90)
            self.assertEqual(factory.call_args.kwargs['max_retries'], 0)
            bind = factory.return_value.bind.call_args.kwargs
            self.assertEqual(bind['reasoning_effort'], 'low')
            self.assertTrue(bind['extra_body']['enable_thinking'])

    def test_profile_and_mode_changes_invalidate_old_confirmation(self):
        with patch.dict(os.environ, {'CASE_MODEL_ENABLED': '0', 'CASE_REVIEW_MODEL': 'qwen-plus'}):
            case = empty_case(); workflow = CaseWorkflow()
            workflow.run({'facts': {'workplace': '广州', 'employer_city': '广州',
                                   'dispute_date': '2026-10-01', 'wages': [
                                       {'start': '2026-09-01', 'end': '2026-09-30', 'due': '100', 'paid': '0'}]}}, case)
            workflow.run({'action': 'confirm', 'expected_case_version': 1, 'selected_claims': ['arrears']}, case)
            before = profile_digest()
            with patch.dict(os.environ, {'CASE_REVIEW_MODEL': 'qwen3.8-max'}):
                self.assertNotEqual(before, profile_digest())
                with self.assertRaises(CaseConflict):
                    workflow.run({'action': 'confirm', 'expected_case_version': 1, 'selected_claims': ['arrears']}, case)
            self.assertIsNone(case['document']); self.assertIsNone(case['confirmation'])
            self.assertEqual(case['case_version'], 2)
            with patch.dict(os.environ, {'CASE_MODEL_ENABLED': '1'}):
                self.assertNotEqual(before, profile_digest())

    def test_unknown_review_model_does_not_silently_fallback(self):
        with patch.dict(os.environ, {'CASE_REVIEW_MODEL': 'unknown-model'}):
            with self.assertRaisesRegex(ValueError, 'Unsupported CASE_REVIEW_MODEL'):
                role_profile('Review')


if __name__ == '__main__': unittest.main()
