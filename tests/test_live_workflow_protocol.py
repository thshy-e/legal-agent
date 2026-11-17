import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from legal_ai_agent.casework.models import empty_case
from legal_ai_agent.casework.roles import ReviewOutput, structured_role
from scripts import run_live_casework_smoke as smoke


class LiveWorkflowProtocolTest(unittest.TestCase):
    def test_frozen_input_tampering_is_rejected_before_model_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = Path(folder) / 'fixture.json'
            fixture.write_text('{"initial_amount":"100.00"}', encoding='utf-8')
            fixture.with_suffix('.sha256').write_text(
                hashlib.sha256(fixture.read_bytes()).hexdigest(), encoding='ascii')
            self.assertEqual(smoke.load_fixture(fixture)[0]['initial_amount'], '100.00')
            fixture.write_text('{"initial_amount":"999.00"}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                smoke.load_fixture(fixture)

    def test_existing_evidence_is_not_overwritten_or_sent_to_model(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'summary.json'
            output.write_text('original evidence', encoding='utf-8')
            with patch('sys.argv', ['smoke', '--output', str(output)]), \
                 patch.object(smoke, 'run_check') as call:
                with self.assertRaises(SystemExit) as stopped:
                    smoke.main()
            self.assertEqual(stopped.exception.code, 2)
            call.assert_not_called()
            self.assertEqual(output.read_text(encoding='utf-8'), 'original evidence')

    def test_review_fact_paths_are_corrected_once_and_attempt_hashes_match(self):
        case = empty_case()
        case['sources'] = [{'id': 'verified-law'}]
        prompts = []
        finding = {'code': 'needs-check', 'severity': 'warning',
                   'category': 'evidence_gap', 'message': '材料待核验',
                   'source_ids': ['facts.wages'], 'fact_fields': []}

        def runner(prompt):
            prompts.append(prompt)
            result = dict(finding)
            if len(prompts) == 2:
                result.update(source_ids=['verified-law'], fact_fields=['wages'])
            return json.dumps({'issues': [result]}, ensure_ascii=False)

        result = structured_role(case, 'Review', ReviewOutput,
                                 {'sources': case['sources'], 'facts': {'wages': []}}, '', runner)
        self.assertEqual(result['issues'][0]['fact_fields'], ['wages'])
        self.assertEqual([r['status'] for r in case['model_calls']], ['failed', 'ok'])
        self.assertIn('facts.wages', prompts[1])
        schema = json.loads(prompts[0].split('\nschema=', 1)[1].split('\nDATA=', 1)[0])
        allowed = schema['$defs']['ReviewFinding']['properties']['source_ids']['items']['enum']
        self.assertEqual(allowed, ['verified-law'])
        self.assertEqual(len(prompts), 2)
        for prompt, record in zip(prompts, case['model_calls']):
            self.assertEqual(record['context_sha256'], hashlib.sha256(prompt.encode()).hexdigest())
            self.assertEqual(record['input_characters'], len(prompt))
        self.assertNotEqual(case['model_calls'][0]['context_sha256'],
                            case['model_calls'][1]['context_sha256'])


if __name__ == '__main__':
    unittest.main()
