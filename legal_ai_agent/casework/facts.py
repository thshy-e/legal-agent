"""Conservative deterministic extraction. Legal allegations remain allegations."""
import re
from .knowledge import CITIES
from .evidence import evidence_statements
from .fact_checks import employment_statement

LABELS = {'workplace':'劳动合同履行地','employer_city':'用人单位所在地','dispute_date':'争议发生日期',
          'applicant':'申请人姓名','applicant_id':'申请人身份证号','applicant_address':'申请人地址','applicant_phone':'申请人电话','employer_name':'单位名称','employer_address':'单位地址','employer_representative':'法定代表人或负责人',
          'termination_basis或wages':'具体解除情形或逐期欠薪信息','severance_cap':'对应城市及年度的经济补偿封顶工资参数','minimum_monthly_wage':'对应城市和日期的最低工资参数','cross_city_resolved':'跨市履行与用人单位所在地的适用关系',
          'start_date':'入职日期','end_date':'解除或离职日期','monthly_average':'解除前12个月应得月平均工资',
          'previous_month_wage':'解除前一个月工资','termination_basis':'解除情形','termination_reason':'解除具体理由',
          'initiator':'解除提出方','written_notice_30':'是否提前30日书面通知','article40_conditions':'第四十条实体条件是否具备',
          'protected_status':'是否处于第四十二条保护情形','wages':'逐期应付实付工资','employment_type':'用工类型'}
LABELS.update(article40_category='第四十条具体类别（医疗期满、不能胜任或客观情况重大变化）',agreement_reached='双方是否已就单位提出的解除达成一致',worker38_ground='第三十八条解除的具体事由',worker38_conditions='第三十八条所主张事由的具体事实条件',worker38_notice_delivered='第三十八条解除理由是否已向单位送达',layoff_conditions='第四十一条裁员的规模及法定事由',layoff_procedure='第四十一条说明、听取意见及报告等程序',continued_performance='是否请求继续履行劳动合同或确已不能继续履行')

LABELS['wage_statement']='工资约定、当期工作及在职情况陈述（待举证）'
LABELS['cross_city_compensation_rule']='跨市补偿封顶参数适用关系及相关约定（待专业核验）'
LABELS['employment_status']='当前在职状态（用户陈述，待举证）'


def extract(query, with_conflicts=False):
    patch={}; conflicts=[]; text=str(query or '')
    status,_,conflict=employment_statement(text)
    if status is not None:patch['employment_status']=status
    if conflict:conflicts.append({'field':'employment_status','message':'在职和已离职陈述冲突，请明确本轮所涉劳动期间。'})
    cities='|'.join(CITIES+('香港','澳门'))
    for field,pattern in [('workplace',r'(?:(?:履行地|工作地)(?:是|为|：|:)?\s*|在(?=(?:'+cities+r')(?:市)?(?:工作|上班|履行)))('+cities+r')(?:市)?'),
                          ('employer_city',r'(?:单位所在地|公司所在地|公司在|单位在)(?:是|为|：|:)?\s*('+'|'.join(CITIES+('香港','澳门'))+r')(?:市)?')]:
        matches=[m for m in re.finditer(pattern,text) if not re.search(r'(?:没有|不是|并非|不|没)$',text[max(0,m.start()-3):m.start()])]
        values={m.group(1) for m in matches}
        if len(values)==1: patch[field]=values.pop()
        elif len(values)>1:
            patch[field]=None;conflicts.append({'field':field,'message':LABELS[field]+'存在多个不同陈述，请明确实际地点及是否跨市履行。'})
    dt=r'(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?'
    for field,word in [('start_date','入职'),('end_date','离职|解除日期'),('dispute_date','争议日期')]:
        m=re.search(r'(?:'+word+r')(?:日期)?[为是：:\s]*'+dt,text)
        if m: patch[field]=f'{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}'
    for field,pattern in [('monthly_average',r'(?:12个月平均工资|十二个月平均工资|补偿工资基数|月平均工资)[为是：:\s]*(\d+(?:\.\d{1,2})?)'),
                          ('previous_month_wage',r'(?:上月工资|前一个月工资|代通知金工资)[为是：:\s]*(\d+(?:\.\d{1,2})?)')]:
        m=re.search(pattern,text)
        if m: patch[field]=m[1]
    evidence,evidence_conflicts=evidence_statements(text)
    conflicts+=evidence_conflicts
    if evidence: patch['evidence']=evidence
    if re.search(r'不是违法(?:辞退|解除)|不属于违法(?:辞退|解除)',text):
        patch['termination_basis']='unknown'; patch['termination_reason']='用户否认违法解除，请说明实际解除理由'
    elif '违法解除' in text or '违法辞退' in text:
        patch['termination_reason']='用户主张违法解除（未经认定）';patch['termination_basis']='unknown'
    elif any(w in text for w in ('突然辞退','没有补偿','无补偿','被辞退')):
        patch['termination_reason']='用户陈述被辞退或未获补偿，解除合法性待核验'
    # Citizenship/investor identity is deliberately not an applicable-law switch.
    if re.search(r'(?:实际|长期)?在(?:香港|澳门)(?:工作|履行)|跨境工作',text): patch['actual_cross_border_work']=True
    return (patch,conflicts) if with_conflicts else patch
