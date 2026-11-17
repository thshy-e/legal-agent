"""Select a bounded citation correction; never clear factual/legal blockers."""
from copy import deepcopy
import hashlib
import json


PROTECTED_FIELDS = ('facts', 'fact_sources', 'fact_conflicts', 'case_version', 'claims',
                    'calculations', 'missing_info', 'sources', 'dependencies',
                    'knowledge_digest', 'confirmation', 'document', 'document_status')


def citation_feedback(case, issues):
    if case.get('analysis_repair', {}).get('attempts') or case.get('missing_info') or case.get('failures'):
        return []
    if case.get('analysis', {}).get('status') != 'model_augmented':
        return []
    if any(i['severity'] == 'critical' for i in case.get('review_issues', [])):
        return []
    critical = [i for i in issues if i['severity'] == 'critical']
    model_issues = (case.get('model_review') or {}).get('issues', [])
    cited = {key for a in case['analysis'].get('arguments', []) for key in a['source_ids']}
    if not critical or any(i.get('category') != 'citation' or i not in model_issues
                           or not cited.intersection(i.get('source_ids', [])) for i in critical):
        return []
    return deepcopy(critical)


def facts_digest(case):
    return hashlib.sha256(json.dumps(case['facts'], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def guard_snapshot(case):
    return {key: deepcopy(case[key]) for key in PROTECTED_FIELDS if key in case}


def restore_if_mutated(case, before):
    changed = [key for key in PROTECTED_FIELDS if (key in case) != (key in before)
               or (key in before and case[key] != before[key])]
    for key in changed:
        if key in before: case[key] = deepcopy(before[key])
        else: case.pop(key, None)
    return changed
