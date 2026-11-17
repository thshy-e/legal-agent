"""Human-review results must remain attributable and distinct from automation."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.legal_review import COLUMNS, DIMENSIONS, export_bundle, summarize


class LegalReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dataset = self.root / 'tasks.json'
        self.dataset.write_text(json.dumps({'dataset_type': 'public_engineering_not_blind',
            'tasks': [{'id': 'T01', 'kind': 'case', 'group': 'termination',
                       'request': {'query': '请核对解除条件'}, 'expected': {'secret_label': 42}}]}), encoding='utf-8')
        self.report = self.root / 'report.json'
        self.report.write_text(json.dumps({'dataset_sha256': hashlib.sha256(self.dataset.read_bytes()).hexdigest(),
            'results': [{'id': 'T01', 'artifact': {'facts': {}, 'calculations': []}, 'passed': True}],
            'rows': [{'id': 'T01', 'variant': 'single_agent', 'status': 'not_run'}]}), encoding='utf-8')
        self.bundle = self.root / 'bundle'

    def tearDown(self):
        self.tmp.cleanup()

    def export(self, kind='engineering'):
        return export_bundle(self.dataset, self.report, self.bundle, kind)

    def ratings(self, **updates):
        path = self.bundle / 'ratings.csv'
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        rows[0].update(updates)
        with path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=COLUMNS)
            writer.writeheader(); writer.writerows(rows)
        return path

    def review(self, **updates):
        values = dict.fromkeys(DIMENSIONS, 'NA')
        values.update(review_status='reviewed', reviewer='SYNTHETIC TEST REVIEWER',
                      reviewer_role='internal_test', review_date='2026-01-01', facts='2', sources='1',
                      severe_errors='[]', explanation='Synthetic review for aggregation test only',
                      source_urls='["https://example.org/synthetic-source"]', final_legal_assessment='needs_revision')
        return self.ratings(**(values | updates))

    def test_pending_reviews_never_create_a_score_or_expert_claim(self):
        self.export()
        result = summarize(self.bundle, self.bundle / 'ratings.csv')
        self.assertEqual(result['variants']['rules_engineering']['pending'], 1)
        self.assertIsNone(result['variants']['rules_engineering']['dimension_point_ratio'])
        self.assertFalse(result['expert_reviewed']); self.assertFalse(result['blind_test'])
        self.assertNotIn('secret_label', (self.bundle / 'packet.json').read_text(encoding='utf-8'))

    def test_unrun_model_rows_are_not_gradeable_outputs(self):
        self.assertEqual(self.export('model')['exported'], 0)
        result = summarize(self.bundle, self.bundle / 'ratings.csv')
        self.assertEqual(result['variants'], {})
        self.assertEqual(result['unavailable_outputs'][0]['status'], 'not_run')

    def test_na_scores_and_severe_errors_are_counted_separately(self):
        self.export()
        result = summarize(self.bundle, self.review(severe_errors='["wrong_region"]'))
        stats = result['variants']['rules_engineering']
        self.assertEqual(stats['possible_points'], 4)
        self.assertEqual(stats['dimension_point_ratio'], .75)
        self.assertEqual(stats['severe_cases'], 1)
        self.assertEqual(stats['severe_errors']['wrong_region'], 1)
        self.assertFalse(result['reviewer_identity_verified'])

    def test_missing_metadata_invalid_scores_and_contradictory_verdict_fail(self):
        self.export()
        for update in ({'reviewer': ''}, {'facts': '3'}, {'source_urls': '[]'},
                       {'final_legal_assessment': 'acceptable', 'severe_errors': '["wrong_region"]'},
                       {'review_status': 'pending'}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                summarize(self.bundle, self.review(**update))

    def test_packet_tampering_and_omitted_ratings_are_rejected(self):
        self.export()
        path = self.bundle / 'packet.json'
        original = path.read_bytes()
        path.write_bytes(original + b' ')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            summarize(self.bundle, self.bundle / 'ratings.csv')
        path.write_bytes(original)
        (self.bundle / 'ratings.csv').write_text(','.join(COLUMNS) + '\n', encoding='utf-8-sig')
        with self.assertRaisesRegex(ValueError, 'Missing or duplicate'):
            summarize(self.bundle, self.bundle / 'ratings.csv')

    def test_changed_dataset_and_existing_exports_are_not_silently_accepted(self):
        self.export()
        with self.assertRaises(FileExistsError):
            self.export()
        self.dataset.write_bytes(self.dataset.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'Dataset differs'):
            export_bundle(self.dataset, self.report, self.root / 'other', 'engineering')


if __name__ == '__main__':
    unittest.main()
