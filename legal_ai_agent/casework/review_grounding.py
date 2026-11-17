"""Validate review references, without claiming to validate legal reasoning."""
import json


def compact(value):
    return ''.join(value.split())


def fact_value(facts, field):
    """Resolve only existing fact paths; never evaluate a model expression."""
    parts = field.removeprefix('facts.').split('.')
    current = facts
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise ValueError('未知事实字段：' + field)
    return current


def referenced_value(data, field):
    if field.split('.', 1)[0] in ('calculations', 'claims', 'date_checks'):
        return fact_value(data, field)
    return fact_value(data.get('facts', {}), field)


def validate_review_grounding(parsed, data):
    sources = {source['id']: source for source in data.get('sources', [])}
    facts = data.get('facts', {})
    for finding in parsed.issues:
        invalid = set(finding.source_ids) - sources.keys()
        if invalid:
            raise ValueError('source_ids只允许本轮法源编号；事实路径写fact_fields。无效值：' + json.dumps(sorted(invalid), ensure_ascii=False))
        # Dependencies are derived from anchors, not entered twice by the model.
        finding.fact_fields = list(dict.fromkeys(finding.fact_fields +
            [excerpt.field for excerpt in finding.fact_excerpts] + finding.missing_fact_fields))
        for field in finding.fact_fields:
            referenced_value(data, field)
        for excerpt in finding.law_excerpts:
            if excerpt.source_id not in finding.source_ids:
                raise ValueError('法条片段的source_id必须同时列入source_ids')
            original = sources[excerpt.source_id].get('original_text', '')
            if len(compact(excerpt.quote)) < 12 or compact(excerpt.quote) not in compact(original):
                raise ValueError('法条片段不在本轮原文中：' + excerpt.source_id)
        for excerpt in finding.fact_excerpts:
            value = referenced_value(data, excerpt.field)
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            if not compact(excerpt.quote) or compact(excerpt.quote) not in compact(text):
                raise ValueError('事实或工具片段不匹配本轮原值：' + excerpt.field)
        for field in finding.missing_fact_fields:
            if fact_value(facts, field) not in (None, '', [], {}, 'unknown'):
                raise ValueError('不能把已填写的事实列为缺失：' + field)
        if finding.severity != 'critical' or finding.category in ('evidence_gap', 'subject_placeholder'):
            continue
        if not finding.fact_excerpts and not finding.missing_fact_fields:
            raise ValueError('关键问题须有原始事实片段或确实未填写的missing_fact_fields')
        if finding.category in ('legal_condition', 'citation', 'claim_relation') and not finding.law_excerpts:
            raise ValueError('关键法律问题须提供本轮法条原文片段law_excerpts，不能依据记忆补法')
        if finding.category == 'fact_conflict' and len({(e.field, compact(e.quote)) for e in finding.fact_excerpts}) < 2:
            raise ValueError('事实冲突须指出至少两个不同的原始陈述片段')
