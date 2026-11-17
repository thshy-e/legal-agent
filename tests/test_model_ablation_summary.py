from copy import deepcopy
import unittest
from scripts.summarize_model_ablation import summarize,VARIANTS


class ModelSummaryTest(unittest.TestCase):
    def report(self):
        rows=[]
        for variant in VARIANTS:
            rows.append({'id':'a','variant':variant,'status':'completed','automatic_errors':[],'trace':[{'status':'completed','actual_model':'qwen-plus','usage':{'input_tokens':10,'output_tokens':2,'total_tokens':12},'seconds':1.0}]})
            rows.append({'id':'b','variant':variant,'status':'failed','trace':[{'status':'failed','actual_model':'unknown','usage':None,'seconds':2.0}]})
        return {'status':'completed_with_results_requiring_human_review','rows':rows,'dataset_sha256':'dataset','knowledge_digest':'knowledge','protocol_sha256':'protocol','model_config':{}}

    def test_failure_and_unknown_usage_cannot_be_reported_as_pass_or_free_calls(self):
        result=summarize(self.report())
        for group in result['groups'].values():
            self.assertEqual(group['tasks'],2);self.assertEqual(group['outputs_without_automatic_flags'],1)
            self.assertEqual(group['call_attempts'],2);self.assertEqual(group['calls_without_reported_usage'],1)
            self.assertEqual(group['reported_tokens']['total_tokens'],12)
            self.assertEqual(group['human_legal_reviews'],0)

    def test_partial_duplicate_and_unbalanced_reports_are_rejected(self):
        report=self.report();partial=deepcopy(report);partial['status']='running'
        duplicate=deepcopy(report);duplicate['rows'].append(duplicate['rows'][0])
        unbalanced=deepcopy(report);unbalanced['rows'].pop()
        for candidate in (partial,duplicate,unbalanced):
            with self.assertRaises(ValueError):summarize(candidate)


if __name__=='__main__':unittest.main()
