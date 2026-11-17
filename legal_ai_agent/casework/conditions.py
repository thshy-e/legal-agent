"""Explicit legal-condition checklist; a selected label is never a finding.

Answers are user statements for conditional analysis, not authenticated evidence.
"""

from .facts import LABELS


def termination_checklist(facts):
    basis=facts.get('termination_basis','unknown')
    required=[];issues=[]
    if basis=='employer_agreement':
        required=['agreement_reached']
    elif basis=='worker_38':
        required=['worker38_ground','worker38_conditions','worker38_notice_delivered']
        if facts.get('worker38_ground')=='other':
            issues.append(dict(code='worker38_special_ground',severity='critical',message='所填第三十八条事由未纳入首期规则，需专业复核；紧急解除等情形不能统一套用送达条件。'))
    elif basis=='article_40':
        required=['article40_category','article40_conditions','protected_status','written_notice_30']
    elif basis=='article_41':
        required=['layoff_conditions','layoff_procedure','protected_status']
    elif basis=='illegal_claim':
        required=['continued_performance']
        if facts.get('continued_performance')=='requested':
            issues.append(dict(code='remedy_conflict',severity='critical',message='已选择请求继续履行，应依第四十八条核对救济路径，不能同时按赔偿金请求确认；继续履行确已不能时另行澄清。'))
    missing=[];checklist=[]
    for key in required:
        value=facts.get(key)
        if key=='protected_status': satisfied=value is False
        elif key in ('worker38_ground','article40_category'): satisfied=value not in (None,'unknown','other')
        elif key=='continued_performance': satisfied=value in ('not_requested','impossible')
        elif key=='written_notice_30': satisfied=value is not None
        else: satisfied=value is True
        if not satisfied: missing.append(key)
        checklist.append(dict(field=key,label=LABELS[key],value=value,status='user_stated' if satisfied else 'needs_clarification',evidence_verified=False))
    return checklist,missing,issues
