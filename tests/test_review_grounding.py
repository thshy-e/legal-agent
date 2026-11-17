"""Review must show its references; matching text does not prove legal merit."""
from copy import deepcopy
import json
import unittest

from legal_ai_agent.casework.models import empty_case
from legal_ai_agent.casework.roles import ReviewOutput, structured_role
from legal_ai_agent.casework.review_grounding import validate_review_grounding


class ReviewGroundingTest(unittest.TestCase):
    def setUp(self):
        self.data = {'facts': {'wage_statement': '工资尚未支付，仍在职。',
                               'end_date': None, 'wages': [{'due': '120.00', 'paid': '0'}]},
                     'sources': [{'id': 'synthetic-law',
                                  'original_text': '本测试条款仅用于校验文本引用，不是法律依据。'}]}
        self.finding = {'code': 'synthetic', 'severity': 'critical', 'category': 'legal_condition',
                        'message': 'Synthetic grounding test, not a legal opinion.',
                        'source_ids': ['synthetic-law'], 'fact_fields': ['wage_statement'],
                        'law_excerpts': [{'source_id': 'synthetic-law',
                                          'quote': '本测试条款仅用于校验文本引用，不是法律依据。'}],
                        'fact_excerpts': [{'field': 'wage_statement', 'quote': '工资尚未支付'}]}

    def validate(self, finding):
        parsed = ReviewOutput.model_validate({'issues': [finding]})
        validate_review_grounding(parsed, self.data)
        return parsed

    def test_real_excerpts_remain_critical_without_claiming_semantic_correctness(self):
        parsed = self.validate(self.finding)
        self.assertEqual(parsed.issues[0].severity, 'critical')

    def test_fabricated_law_text_and_reference_outside_role_input_are_rejected(self):
        for change in ('fabricated', 'outside_context', 'blank'):
            with self.subTest(change=change):
                finding = deepcopy(self.finding)
                if change == 'fabricated':
                    finding['law_excerpts'][0]['quote'] = '工资必须在次月七日以前支付，否则不能整理草稿。'
                elif change == 'blank':
                    finding['law_excerpts'][0]['quote'] = ' ' * 12
                else:
                    finding['source_ids'] = ['outside-law']
                with self.assertRaises(ValueError): self.validate(finding)

    def test_populated_and_unknown_fields_cannot_be_claimed_missing(self):
        for field in ('wage_statement', 'wages.0.due', 'unknown_field'):
            finding = deepcopy(self.finding)
            finding.update(fact_fields=[field], fact_excerpts=[], missing_fact_fields=[field])
            with self.subTest(field=field), self.assertRaises(ValueError): self.validate(finding)
        finding.update(fact_fields=['end_date'], missing_fact_fields=['end_date'])
        self.validate(finding)

    def test_fabricated_fact_and_duplicate_conflict_anchors_are_rejected(self):
        finding = deepcopy(self.finding)
        finding['fact_excerpts'][0]['quote'] = '已离职'
        with self.assertRaises(ValueError): self.validate(finding)
        finding = deepcopy(self.finding)
        finding['category'] = 'fact_conflict'
        finding['fact_excerpts'] *= 2
        with self.assertRaises(ValueError): self.validate(finding)

    def test_invalid_critical_is_retried_once_then_blocks_not_downgraded(self):
        case = empty_case()
        case['sources'] = self.data['sources']
        finding = deepcopy(self.finding)
        finding['law_excerpts'][0]['quote'] = '这是不存在于本轮法源的错误法律命题。'
        result = structured_role(case, 'Review', ReviewOutput, self.data, '',
                                 lambda prompt: json.dumps({'issues': [finding]}, ensure_ascii=False))
        self.assertTrue(result['failed'])
        self.assertEqual(len(case['model_calls']), 2)
        self.assertTrue(all(c['status'] == 'failed' for c in case['model_calls']))
        self.assertEqual(case['failures'][0]['stage'], 'Review')

    def test_anchor_fields_are_derived_and_actual_tool_values_can_be_referenced(self):
        self.data['calculations'] = [{'amount': '120.00'}]
        finding = deepcopy(self.finding)
        finding.update(category='calculation', fact_fields=[],
                       fact_excerpts=[{'field': 'calculations.0.amount', 'quote': '120.00'}])
        parsed = self.validate(finding)
        self.assertEqual(parsed.issues[0].fact_fields, ['calculations.0.amount'])
        finding['fact_excerpts'][0]['quote'] = '999.00'
        with self.assertRaises(ValueError): self.validate(finding)

    def test_all_eight_missing_subject_fields_fit_without_accepting_populated_fields(self):
        names = ['applicant', 'applicant_id', 'applicant_address', 'applicant_phone',
                 'employer_name', 'employer_address', 'employer_representative', 'employer_phone']
        self.data['facts'].update({name: None for name in names})
        finding = {'code': 'subject', 'severity': 'warning', 'category': 'subject_placeholder',
                   'message': 'Subject information needs completion.', 'source_ids': [],
                   'missing_fact_fields': names}
        parsed = self.validate(finding)
        self.assertEqual(parsed.issues[0].fact_fields, names)
        self.data['facts']['employer_phone'] = 'synthetic-contact'
        with self.assertRaisesRegex(ValueError, '不能把已填写'):
            self.validate(finding)

    def test_dictionary_rephrasing_is_rejected_but_literal_leaf_is_accepted(self):
        self.data['facts']['evidence'] = {'考勤': 'missing'}
        finding = {'code': 'evidence', 'severity': 'warning', 'category': 'evidence_gap',
                   'message': 'Attendance materials missing.', 'source_ids': [],
                   'fact_excerpts': [{'field': 'evidence', 'quote': '考勤: missing'}]}
        with self.assertRaisesRegex(ValueError, '事实或工具片段'):
            self.validate(finding)
        finding['fact_excerpts'] = [{'field': 'evidence.考勤', 'quote': 'missing'}]
        self.validate(finding)


if __name__ == '__main__':
    unittest.main()
