"""Possession, negation and conflicts must agree across consultation and cases."""
import os
import unittest
from unittest.mock import patch
from legal_ai_agent.casework.facts import extract
from legal_ai_agent.casework.models import empty_case
from legal_ai_agent.casework.workflow import CaseWorkflow
from legal_ai_agent.tools.legal_reasoning import build_case_analysis,_detect_case_types


class EvidenceConsistencyTest(unittest.TestCase):
    def test_mention_is_not_possession_and_absence_is_preserved(self):
        self.assertNotIn('evidence',extract('考勤可以证明加班吗'))
        analysis=build_case_analysis('公司辞退了我，没有考勤，没有工资流水')
        self.assertIn('用户称持有（真实性未核验）：暂无明确持有陈述',analysis)
        self.assertIn('用户称缺失：工资流水、考勤记录',analysis)
        self.assertIn('解除争议',_detect_case_types('不是违法辞退，需说明理由'))
        self.assertNotIn('违法辞退',_detect_case_types('被辞退'))
        self.assertNotIn('加班费',_detect_case_types('没有考勤'))
    def test_conflicting_and_double_negation_statements_require_clarification(self):
        for query in ('有考勤，没有考勤','不是没有考勤','没有考勤，有考勤'):
            facts,conflicts=extract(query,with_conflicts=True)
            self.assertEqual(facts['evidence']['考勤'],'unknown')
            self.assertEqual(conflicts[0]['field'],'evidence.考勤')
        self.assertEqual(extract('有辞退通知')['evidence']['解除通知'],'claimed_present')
    def test_questions_hypotheticals_and_employer_possession_are_not_user_possession(self):
        for query in ('是否有考勤可以证明加班','有考勤吗？','如果有考勤就好了','建议提供了考勤','公司有考勤','单位有工资流水','有没有考勤'):
            self.assertNotIn('evidence',extract(query),query)
        self.assertEqual(extract('公司有考勤，我有工资流水')['evidence'],{'工资流水':'claimed_present'})
    @patch.dict(os.environ,{'CASE_MODEL_ENABLED':'0'})
    def test_text_evidence_survives_other_structured_evidence_and_conflicts_persist(self):
        case=empty_case();workflow=CaseWorkflow()
        facts={'workplace':'广州','employer_city':'广州','dispute_date':'2026-10-01','wages':[{'start':'2026-09-01','end':'2026-09-30','due':'100','paid':'0'}],'evidence':{'工资流水':'claimed_present'}}
        result=workflow.run({'query':'有考勤，没有考勤，没有劳动合同','facts':facts},case)['structured']
        self.assertEqual(result['facts']['evidence']['劳动合同'],'missing')
        self.assertEqual(result['fact_sources']['evidence.工资流水']['source'],'user_structured')
        self.assertEqual(result['fact_sources']['evidence.劳动合同']['source'],'user_text_extraction')
        self.assertFalse(result['confirmation_required'])
        retried=workflow.run({'query':'请继续分析'},case)['structured']
        self.assertTrue(any(i['code']=='fact_conflict' for i in retried['review_issues']))
        resolved=workflow.run({'facts':{'evidence':{'考勤':'missing'}}},case)['structured']
        self.assertEqual(resolved['fact_conflicts'],[]);self.assertTrue(resolved['confirmation_required'])
        self.assertEqual(resolved['case_version'],2)
    @patch.dict(os.environ,{'CASE_MODEL_ENABLED':'0'})
    def test_location_conflict_survives_retry_until_specific_correction(self):
        case=empty_case();workflow=CaseWorkflow()
        workflow.run({'query':'在广州工作，也在深圳工作','facts':{'employer_city':'广州','dispute_date':'2026-10-01'}},case)
        result=workflow.run({'query':'继续'},case)['structured']
        self.assertTrue(result['fact_conflicts'])
        result=workflow.run({'facts':{'workplace':'广州'}},case)['structured']
        self.assertFalse(result['fact_conflicts'])

if __name__=='__main__':unittest.main()
