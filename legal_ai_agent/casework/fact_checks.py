"""Statement extraction and calendar ordering, without legal determinations."""
import re
from datetime import date


def employment_statement(text):
    active = r'(?:我|本人)?(?:(?:目前|现在|当前|现)(?:仍|还)?(?:在职|在(?:该|本)?(?:单位|公司)(?:工作|上班))|仍(?:在职|在(?:该|本)?(?:单位|公司)(?:工作|上班)))'
    terminated = r'(?:我|本人)(?:目前|现在|当前|现)?(?:已经|已)(?:离职|与(?:该|本)?(?:单位|公司)终止劳动关系)'
    found = []
    for match in re.finditer(r'([^，。；;！？!?\n]+)([，。；;！？!?\n]|$)', str(text or '')):
        clause, delimiter = match.groups()
        if delimiter in ('?', '？'): continue
        clause = re.sub(r'^\s*更正[^：:]*[：:]\s*', '', clause).strip()
        if re.search(r'是否|吗|么|还是|不准确|不属实|不是事实|并非事实', clause):
            continue
        for status, pattern in (('active', active), ('terminated', terminated)):
            if re.match(pattern, clause): found.append((status, clause))
    statuses = {status for status, _ in found}
    return (next(iter(statuses)) if len(statuses) == 1 else ('unknown' if statuses else None),
            '；'.join(clause for _, clause in found), len(statuses) > 1)


def date_checks(facts):
    checks = []
    def compare(left_field, left, right_field, right, label):
        if not left or not right: return
        a, b = date.fromisoformat(left), date.fromisoformat(right)
        checks.append({'left_field': left_field, 'left': left, 'operator': '<=',
                       'right_field': right_field, 'right': right,
                       'passed': a <= b, 'label': label,
                       'scope': '仅比较输入日期，不判断时效、到期日或请求是否成立'})
    compare('start_date', facts.get('start_date'), 'dispute_date', facts.get('dispute_date'), '入职日期不晚于争议日期')
    for index, period in enumerate(facts.get('wages', [])):
        compare('start_date', facts.get('start_date'), f'wages.{index}.start', period['start'], '入职日期不晚于所填工资期间起日')
        compare(f'wages.{index}.start', period['start'], f'wages.{index}.end', period['end'], '工资期间起日不晚于止日')
        compare(f'wages.{index}.end', period['end'], 'dispute_date', facts.get('dispute_date'), '工资期间止日不晚于争议日期')
    return checks


def consistency_issues(facts):
    issues = []
    stated, _, conflict = employment_statement(facts.get('wage_statement'))
    status = facts.get('employment_status', 'unknown')
    if conflict or (stated in ('active', 'terminated') and status in ('active', 'terminated') and stated != status):
        issues.append({'code': 'employment_statement_conflict', 'severity': 'critical',
                       'message': '在职状态与工资陈述不一致，请同时核对状态和原始陈述；不据此认定劳动关系。'})
    if status == 'active' and facts.get('end_date') and facts.get('dispute_date') and facts['end_date'] <= facts['dispute_date']:
        issues.append({'code': 'employment_end_conflict', 'severity': 'critical',
                       'message': '陈述仍在职，但所填离职日期不晚于争议日期；请澄清是否涉及不同用工期间。'})
    if facts.get('start_date') and facts.get('dispute_date') and facts['start_date'] > facts['dispute_date']:
        issues.append({'code': 'dispute_before_employment', 'severity': 'critical',
                       'message': '所填争议日期早于入职日期，请澄清本轮欠薪或解除对应的劳动期间。'})
    return issues
