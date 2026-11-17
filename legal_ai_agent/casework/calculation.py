"""Decimal calculations with explicit eligibility and parameter dependencies."""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from .conditions import termination_checklist

RULE_VERSION='labor-scope-20261025-v3'
N_LAWS=['contract-law-2012:a46','contract-law-2012:a47','contract-regulation-2008:a27']
NOTICE_LAWS=['contract-law-2012:a40','contract-regulation-2008:a20']

def money(value): return str(Decimal(str(value)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))

def service_units(start, end):
    """Calendar anniversaries; end is the last day worked (inclusive service)."""
    start=date.fromisoformat(start); end=date.fromisoformat(end)+timedelta(days=1)
    years=end.year-start.year
    def anniversary(y,months=0):
        import calendar
        month=start.month+months; y+= (month-1)//12; month=(month-1)%12+1
        return date(y,month,min(start.day,calendar.monthrange(y,month)[1]))
    if anniversary(start.year+years)>end: years-=1
    if end==anniversary(start.year+years): remainder=Decimal('0')
    elif end>=anniversary(start.year+years,6): remainder=Decimal('1')
    else: remainder=Decimal('.5')
    return Decimal(years)+remainder

def calculate(f, registry, version):
    claims=[]; results=[]; missing=[]; issues=[]
    basis=f.get('termination_basis','unknown'); city=f.get('workplace'); when=f.get('end_date') or f.get('dispute_date')
    termination=bool(f.get('end_date') or f.get('termination_reason') or basis!='unknown')
    if termination:
        checklist,condition_missing,condition_issues=termination_checklist(f)
        missing+=condition_missing;issues+=condition_issues
        if not f.get('termination_reason'): missing.append('termination_reason')
        if f.get('initiator','unknown')=='unknown': missing.append('initiator')
        expected_initiators={'article_40':{'employer'},'article_41':{'employer'},'article_39':{'employer'},'illegal_claim':{'employer'},'worker_38':{'worker'},'voluntary':{'worker'},'employer_agreement':{'employer','mutual'}}
        if basis in expected_initiators and f.get('initiator') not in expected_initiators[basis] and f.get('initiator')!='unknown':
            issues.append(dict(code='initiator_conflict',severity='critical',message='解除提出方与所选解除情形矛盾，请修正事实。'))
        basis_laws={'employer_agreement':['contract-law-2012:a36'],'worker_38':['contract-law-2012:a38'],'article_40':['contract-law-2012:a40','contract-law-2012:a42'],'article_41':['contract-law-2012:a41','contract-law-2012:a42']}
        options= [('N','经济补偿',N_LAWS+basis_laws.get(basis,[]),'满足劳动合同法46条所列情形及47条标准'),
                  ('2N','违法解除赔偿金',N_LAWS+['contract-law-2012:a48','contract-law-2012:a87','contract-regulation-2008:a25'],'违法解除且不要求继续履行或已不能继续履行')]
        for code,title,laws,conditions in options:
            available=(code=='N' and basis in ('employer_agreement','worker_38','article_40','article_41')) or (code=='2N' and basis=='illegal_claim')
            excluded=basis in ('article_39','voluntary') or (code=='2N' and basis in ('article_40','article_41','worker_38','employer_agreement')) or (code=='N' and basis=='illegal_claim')
            claims.append(dict(id=code,title=title,status='conditional' if available and not condition_missing else ('not_selected' if excluded else 'needs_clarification'),conditions=conditions,condition_checklist=checklist,
                               laws=laws,alternative_group='termination',mutually_exclusive=['N','2N'],
                               favorable=['核对解除通知、工资记录及工作年限'],unfavorable=['解除理由、实体条件及程序可能存在争议；用户陈述不等于司法认定']))
        if basis=='unknown': missing.append('termination_basis')
        if basis=='article_40':
            if f.get('article40_conditions') is not True: missing.append('article40_conditions')
            if f.get('protected_status') is not False: missing.append('protected_status')
            if f.get('written_notice_30') is None: missing.append('written_notice_30')
            if f.get('written_notice_30') is False:
                claims.append(dict(id='notice',title='代通知金',status='conditional' if not condition_missing else 'needs_clarification',condition_checklist=checklist,conditions='劳动合同法40条实体条件具备且未提前30日书面通知；不是所有未通知解除都适用',laws=NOTICE_LAWS,alternative_group=None,mutually_exclusive=['2N']))
        elif basis=='article_41':
            issues.append(dict(code='article41_notice',severity='info',message='第四十一条裁员不直接套用第四十条代通知金。需另核验裁员实体和程序条件。'))
        if basis not in ('article_39','voluntary'):
            for key in ('start_date','end_date','monthly_average'):
                if not f.get(key): missing.append(key)
            blockers=[]; assumptions=['普通劳动关系，所填工资为应得工资，法律适用尚需核验。']
            if f.get('start_date') and f['start_date']<'2008-01-01': blockers.append('2008年前工龄须分段专业复核')
            if f.get('employment_type')!='ordinary': blockers.append('特殊用工须专业复核')
            # Article 47 cannot be applied in isolation from Regulation 14 and
            # any relevant agreement when the two cities differ. A user's
            # cross_city_resolved checkbox is not a verified legal mapping.
            cross_city=bool(city and f.get('employer_city') and city!=f['employer_city'])
            cap_city=None if cross_city else f.get('employer_city')
            if cross_city:
                blockers.append('跨市补偿参数适用需核验实施条例第14条及相关约定，不能仅凭澄清勾选确定城市')
                missing.append('cross_city_compensation_rule')
                issues.append(dict(code='cross_city_compensation',severity='critical',message=blockers[-1],source_ids=['contract-law-2012:a47','contract-regulation-2008:a14']))
            cap=registry.parameter(cap_city,'severance_cap',when) if when and cap_city else None
            floor=registry.parameter(city,'minimum_monthly_wage',when) if when and city else None
            if not cap: blockers.append('缺少适用城市及年度经济补偿封顶参数'); missing.append('severance_cap')
            if not floor: blockers.append('缺少适用日期最低工资参数'); missing.append('minimum_monthly_wage')
            for c in claims:
                if c['id'] not in ('N','2N'): continue
                result=dict(claim_id=c['id'],case_version=version,rule_version=RULE_VERSION,amount=None,status='pending',formula='补偿工资基数 × 折算工龄'+(' × 2' if c['id']=='2N' else ''),assumptions=assumptions,missing_parameters=blockers,laws=c['laws'],parameter_ids=[],parameter_regions={'severance_cap':cap_city,'minimum_monthly_wage':city})
                if c['status']=='not_selected': result.update(status='not_applicable',missing_parameters=[])
                if c['status']=='conditional' and not blockers and all(f.get(k) for k in ('start_date','end_date','monthly_average')):
                    wage=Decimal(f['monthly_average']); ceiling=Decimal(cap['value']); base=max(Decimal(floor['value']),min(wage,ceiling))
                    units=service_units(f['start_date'],f['end_date']); units=min(units,Decimal(12)) if wage>ceiling else units
                    result.update(amount=money(base*units*(2 if c['id']=='2N' else 1)),status='conditional',base=money(base),service_units=str(units),formula=f"{money(base)} × {units}"+(' × 2' if c['id']=='2N' else ''),parameter_ids=[cap['id'],floor['id']])
                results.append(result)
            if f.get('written_notice_30') is False and basis=='article_40':
                wage=f.get('previous_month_wage')
                if not wage: missing.append('previous_month_wage')
                results.append(dict(claim_id='notice',case_version=version,rule_version=RULE_VERSION,status='conditional' if wage else 'pending',amount=money(wage) if wage else None,formula='解除前一个月工资 × 1',assumptions=['仅第四十条条件成立且未提前30日书面通知时支持。'],laws=NOTICE_LAWS,parameter_ids=[],missing_parameters=[] if wage else ['previous_month_wage']))
    if f.get('wages'):
        periods=[]
        for w in f['wages']:
            unpaid=max(Decimal(w['due'])-Decimal(w['paid']),Decimal(0))
            periods.append(dict(**w,unpaid=money(unpaid)))
        total=sum((Decimal(p['unpaid']) for p in periods),Decimal(0))
        claims.append(dict(id='arrears',title='拖欠工资',status='conditional',conditions='劳动关系、工资约定、已履行劳动及支付情况须证据支持',laws=['contract-law-2012:a30','labor-law-2018:a50','arbitration-law-2008:a6'],alternative_group=None,mutually_exclusive=[]))
        if total==0:
            claims[-1].update(status='not_selected',conditions='所填期间未付工资余额为零；核对是否遗漏期间或应付项目，不生成追讨零元的请求。')
        results.append(dict(claim_id='arrears',case_version=version,rule_version=RULE_VERSION,status='conditional',amount=money(total),formula='Σ max(逐期应付工资－实付工资, 0)',periods=periods,assumptions=['仅核算所填期间本金，不自动附加处罚性金额。'],laws=['contract-law-2012:a30','labor-law-2018:a50'],parameter_ids=[],missing_parameters=[]))
        if total==0: results[-1]['status']='no_unpaid_balance'
    if not claims: missing.append('termination_basis或wages')
    return claims,results,list(dict.fromkeys(missing)),issues
