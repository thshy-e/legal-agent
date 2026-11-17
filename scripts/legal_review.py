"""Export traceable legal review sheets and validate independent human ratings.

No automatic legal grades, expert endorsements or blind-test claims are created.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date
import hashlib
import json
from pathlib import Path

DIMENSIONS = ('facts', 'region_time', 'claim_conditions', 'claim_relations',
              'evidence', 'calculation', 'sources', 'confirmation_document')
SEVERE_CODES = {'fabricated_source', 'wrong_region', 'obsolete_rule',
                'unconditional_compensation', 'fabricated_parameter_or_evidence',
                'stale_confirmation', 'document_amount_mismatch'}
VARIANTS = {'single_agent', 'collaboration_no_review', 'collaboration_review'}
COLUMNS = ('review_id', 'task_id', 'variant', 'review_status', 'reviewer',
           'reviewer_role', 'review_date', *DIMENSIONS, 'severe_errors',
           'explanation', 'source_urls', 'final_legal_assessment')
ROOT = Path(__file__).resolve().parents[1]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def export_bundle(dataset_path, report_path, output, kind):
    dataset_raw = Path(dataset_path).read_bytes()
    report_raw = Path(report_path).read_bytes()
    dataset, report = json.loads(dataset_raw), json.loads(report_raw)
    if report.get('dataset_sha256') != digest(dataset_raw):
        raise ValueError('Dataset differs from the evaluated dataset')
    tasks = {task['id']: task for task in dataset['tasks']}
    if len(tasks) != len(dataset['tasks']):
        raise ValueError('Duplicate dataset task id')
    items, skipped, seen = [], [], set()
    rows = report['results'] if kind == 'engineering' else report['rows']
    for row in rows:
        task_id = row['id']
        variant = 'rules_engineering' if kind == 'engineering' else row['variant']
        if task_id not in tasks or (kind == 'model' and variant not in VARIANTS):
            raise ValueError('Unknown task or variant')
        identity = (task_id, variant)
        if identity in seen:
            raise ValueError('Duplicate evaluated task and variant')
        seen.add(identity)
        if kind == 'model' and row.get('status') != 'completed':
            skipped.append({'task_id': task_id, 'variant': variant,
                            'status': row.get('status', 'unknown'), 'error': row.get('error')})
            continue
        task = tasks[task_id]
        # Scoring expectations are withheld from the reviewer packet.
        user_input = {key: value for key, value in task.items()
                      if not key.startswith('expected') and key not in ('name', 'group')}
        answer_key = 'artifact' if kind == 'engineering' else 'answer'
        if not isinstance(row.get(answer_key), dict):
            raise ValueError('A completed evaluation must contain its actual output')
        items.append({'review_id': digest((task_id + ':' + variant).encode())[:16],
                      'task_id': task_id, 'variant': variant, 'group': task['group'],
                      'user_input': user_input, 'actual_output': row[answer_key]})
    packet = {'schema_version': 1, 'kind': kind, 'dataset_sha256': digest(dataset_raw),
              'report_sha256': digest(report_raw), 'knowledge_digest': report.get('knowledge_digest'),
              'protocol_sha256': report.get('protocol_sha256'),
              'dataset_type': dataset.get('dataset_type', 'unspecified'),
              'blind_test': False, 'expert_reviewed': False, 'items': items, 'skipped': skipped}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    packet_raw = (json.dumps(packet, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    (output / 'packet.json').write_bytes(packet_raw)
    (output / 'packet.sha256').write_text(digest(packet_raw) + '\n', encoding='ascii')
    with (output / 'ratings.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        for item in items:
            writer.writerow({key: item[key] for key in ('review_id', 'task_id', 'variant')} |
                            {'review_status': 'pending'})
    return {'exported': len(items), 'skipped': len(skipped), 'packet_sha256': digest(packet_raw)}


def parse_list(value, field):
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(field + ' must be a JSON list') from exc
    if not isinstance(parsed, list) or not all(isinstance(v, str) and v.strip() for v in parsed):
        raise ValueError(field + ' must be a list of nonempty strings')
    if len(set(parsed)) != len(parsed):
        raise ValueError(field + ' contains duplicates')
    return parsed


def summarize(bundle, ratings_path):
    bundle = Path(bundle)
    raw = (bundle / 'packet.json').read_bytes()
    if digest(raw) != (bundle / 'packet.sha256').read_text(encoding='ascii').strip():
        raise ValueError('Review packet hash mismatch')
    packet = json.loads(raw)
    items = {item['review_id']: item for item in packet['items']}
    if len(items) != len(packet['items']):
        raise ValueError('Duplicate review packet id')
    ratings_raw = Path(ratings_path).read_bytes()
    with Path(ratings_path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(COLUMNS):
            raise ValueError('Unexpected review sheet columns')
        ratings = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in ratings):
        raise ValueError('Malformed review CSV row')
    if len(ratings) != len(items) or len({r['review_id'] for r in ratings}) != len(ratings):
        raise ValueError('Missing or duplicate review rows')
    variants = defaultdict(lambda: {'available_outputs': 0, 'reviewed': 0, 'pending': 0,
                                   'points': 0, 'possible_points': 0, 'severe_cases': 0,
                                   'severe_errors': Counter(), 'assessments': Counter()})
    reviewed = []
    for row in ratings:
        item = items.get(row['review_id'])
        if not item or any(row[k] != item[k] for k in ('task_id', 'variant')):
            raise ValueError('Review row identity mismatch')
        stats = variants[row['variant']]
        stats['available_outputs'] += 1
        if row['review_status'] == 'pending':
            if any(row[k].strip() for k in (*DIMENSIONS, 'severe_errors', 'final_legal_assessment')):
                raise ValueError('Pending review cannot contain grades')
            stats['pending'] += 1
            continue
        if row['review_status'] != 'reviewed':
            raise ValueError('review_status must be pending or reviewed')
        for key in ('reviewer', 'reviewer_role', 'review_date', 'explanation'):
            if not row[key].strip():
                raise ValueError('Missing review metadata: ' + key)
        checked_on = date.fromisoformat(row['review_date'])
        if checked_on > date.today():
            raise ValueError('Review date is in the future')
        scores = {key: row[key] for key in DIMENSIONS}
        if any(value not in ('0', '1', '2', 'NA') for value in scores.values()):
            raise ValueError('Dimension scores must be 0, 1, 2 or NA')
        numeric = [int(v) for v in scores.values() if v != 'NA']
        if not numeric:
            raise ValueError('At least one dimension must be applicable')
        severe = parse_list(row['severe_errors'], 'severe_errors')
        if not set(severe) <= SEVERE_CODES:
            raise ValueError('Unknown severe error category')
        urls = parse_list(row['source_urls'], 'source_urls')
        if not urls or any(not url.startswith(('https://', 'http://')) for url in urls):
            raise ValueError('Review must cite supporting HTTP(S) sources')
        assessment = row['final_legal_assessment']
        if assessment not in ('acceptable', 'needs_revision', 'insufficient_information'):
            raise ValueError('Unknown final legal assessment')
        if assessment == 'acceptable' and (severe or any(v == '0' for v in scores.values())):
            raise ValueError('An acceptable assessment conflicts with recorded errors')
        stats['reviewed'] += 1
        stats['points'] += sum(numeric)
        stats['possible_points'] += 2 * len(numeric)
        stats['severe_cases'] += bool(severe)
        stats['severe_errors'].update(severe)
        stats['assessments'].update([assessment])
        reviewed.append(dict(row, dimension_scores=scores))
    for stats in variants.values():
        stats['dimension_point_ratio'] = (stats['points'] / stats['possible_points']
                                          if stats['possible_points'] else None)
    return {'packet_sha256': digest(raw), 'ratings_sha256': digest(ratings_raw),
            'dataset_sha256': packet['dataset_sha256'], 'report_sha256': packet['report_sha256'],
            'kind': packet['kind'], 'blind_test': False, 'expert_reviewed': False,
            'reviewer_identity_verified': False, 'variants': dict(variants), 'reviews': reviewed,
            'unavailable_outputs': packet['skipped'],
            'limitations': ['Dimension points are human ratings, not a legal accuracy estimate.',
                            'Reviewer identities and qualifications require independent verification.',
                            'Public engineering inputs are not an independent blind test.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('export')
    export.add_argument('--dataset', type=Path, default=ROOT / 'data/evaluation/case_tasks_v2.json')
    export.add_argument('--report', type=Path, required=True)
    export.add_argument('--kind', choices=('engineering', 'model'), required=True)
    export.add_argument('--output', type=Path, required=True)
    summary = sub.add_parser('summarize')
    summary.add_argument('--bundle', type=Path, required=True)
    summary.add_argument('--ratings', type=Path, required=True)
    summary.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'export':
        print(json.dumps(export_bundle(args.dataset, args.report, args.output, args.kind)))
    else:
        result = summarize(args.bundle, args.ratings)
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'reviewed': len(result['reviews']), 'expert_reviewed': False}))


if __name__ == '__main__':
    main()
