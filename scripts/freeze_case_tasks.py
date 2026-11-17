"""Freeze the public 60-task engineering set; not a blind legal benchmark."""
from pathlib import Path
import hashlib
import json

DEST=Path(__file__).resolve().parents[1]/'data/evaluation/case_tasks_v1.json'
def main():
    tasks=[]
    base={'workplace':'广州','employer_city':'广州','dispute_date':'2026-10-01'}
    termination={**base,'start_date':'2023-01-01','end_date':'2025-12-31','monthly_average':'8000','previous_month_wage':'9500','initiator':'employer','termination_reason':'用人单位提出解除，理由须核验','termination_basis':'unknown'}
    variants=[('突然辞退',{},'termination_basis'),('称违法解除',{'termination_basis':'illegal_claim'},'severance_cap'),('单位协商',{'termination_basis':'employer_agreement'},'severance_cap'),('第40条无通知',{'termination_basis':'article_40','article40_conditions':True,'written_notice_30':False,'protected_status':False},'severance_cap'),('第40条已通知',{'termination_basis':'article_40','article40_conditions':True,'written_notice_30':True,'protected_status':False},'severance_cap'),('第40条条件缺失',{'termination_basis':'article_40'},'article40_conditions'),('第41条裁员',{'termination_basis':'article_41','written_notice_30':False},'severance_cap'),('第39条',{'termination_basis':'article_39'},None),('个人辞职',{'termination_basis':'voluntary','initiator':'worker'},None),('第38条欠薪解除',{'termination_basis':'worker_38','initiator':'worker'},'severance_cap'),('未满半年',{'start_date':'2025-09-01'},'termination_basis'),('恰好半年',{'start_date':'2025-07-01'},'termination_basis'),('跨2008年',{'start_date':'2007-01-01'},'severance_cap'),('派遣',{'employment_type':'dispatch'},'termination_basis'),('高工资',{'monthly_average':'80000'},'severance_cap'),('补偿与通知工资不同',{'termination_basis':'article_40','article40_conditions':True,'written_notice_30':False,'protected_status':False,'previous_month_wage':'12345.67'},'severance_cap'),('保护期',{'termination_basis':'article_40','article40_conditions':True,'protected_status':True},'protected_status'),('无提出方',{'initiator':'unknown'},'initiator'),('无理由',{'termination_reason':None},'termination_reason'),('无平均工资',{'monthly_average':None},'monthly_average')]
    for i,(name,patch,missing) in enumerate(variants,1):
        expected={'missing_contains':[missing]} if missing else {'no_conditional_claims':True}
        if i in (7,): expected['no_claims']=['notice']
        if i in (13,14):expected['review_codes']=['pre2008' if i==13 else 'special_employment']
        tasks.append({'id':f'T{i:02}','group':'termination','name':name,'kind':'workflow','request':{'facts':{**termination,**patch}},'expected':expected})
    wages_cases=[('全欠',[('8000','0')],'8000.00'),('部分支付',[('8000','3000')],'5000.00'),('小数',[('8000.10','0.03')],'8000.07'),('分期',[('8000','500'),('9000','1000')],'15500.00'),('足额支付',[('8000','8000')],'0.00'),('超付不负数',[('100','150')],'0.00'),('零应付',[('0','0')],'0.00'),('三期',[('1.01','0'),('2.02','1'),('3.03','0')],'5.06'),('百万元内精度',[('123456.78','456.79')],'122999.99'),('跨期欠薪',[('7000','0'),('7000','7000')],'7000.00')]
    for i,(name,rows,total) in enumerate(wages_cases,1):
        wages=[{'start':f'2026-{m+6:02}-01','end':f'2026-{m+6:02}-28','due':due,'paid':paid} for m,(due,paid) in enumerate(rows)]
        tasks.append({'id':f'W{i:02}','group':'arrears','name':name,'kind':'workflow','request':{'facts':{**base,'wages':wages}},'expected':{'amounts':{'arrears':total},'status':'awaiting_confirmation'}})
    geo=[('深圳旧版','深圳市员工工资支付条例第22条','深圳','2025-12-04','sz-wage-2022'),('深圳新版','深圳市员工工资支付条例第22条','深圳','2025-12-05','sz-wage-2025'),('广州不混深圳','深圳市员工工资支付条例第22条','广州','2026-10-01',None),('劳动法47','劳动法第47条','广州','2026-10-01','labor-law-2018'),('合同法47','劳动合同法第47条','深圳','2026-10-01','contract-law-2012'),('广东旧版','广东省劳动人事争议处理办法第74条','东莞','2025-01-08','gd-disputes-2017'),('广东新版','广东省劳动人事争议处理办法第74条','东莞','2025-01-09','gd-disputes-2025'),('港澳隔离广东','广东省工资支付条例第13条','香港','2026-10-01',None),('未知城市不定深圳','深圳市员工工资支付条例第13条',None,'2026-10-01',None),('解释二生效前','最高人民法院关于审理劳动争议案件适用法律问题的解释（二）第6条','广州','2025-08-31',None)]
    for i,(name,query,city,when,source) in enumerate(geo,1):tasks.append({'id':f'G{i:02}','group':'region_version','name':name,'kind':'retrieval','query':query,'city':city,'date':when,'expected_source':source})
    for i in range(1,11):
        first={**base,'wages':[{'start':'2026-09-01','end':'2026-09-30','due':'8000','paid':'0'}]}
        changes=({'wages':[{'start':'2026-09-01','end':'2026-09-30','due':str(8000+i*100),'paid':'0'}]} if i<=5 else {'dispute_date':f'2026-10-{i+1:02}'} if i<=8 else {'workplace':'深圳','employer_city':'深圳'})
        tasks.append({'id':f'M{i:02}','group':'multiturn','name':'确认后修订'+str(i),'kind':'multiturn','initial':first,'changes':changes,'expected_version':2})
    neg=[('没有补偿','termination_basis','unknown'),('突然辞退','termination_basis','unknown'),('不是违法辞退','termination_basis','unknown'),('没有考勤','evidence.考勤','missing'),('有考勤','evidence.考勤','claimed_present'),('没有劳动合同','evidence.劳动合同','missing'),('没有工资流水','evidence.工资流水','missing'),('有工资流水','evidence.工资流水','claimed_present'),('我是香港人，在广州工作，港资企业','actual_cross_border_work',None),('实际在香港工作','actual_cross_border_work',True)]
    for i,(query,field,value) in enumerate(neg,1): tasks.append({'id':f'N{i:02}','group':'negation_missing','name':query,'kind':'extraction','query':query,'expected_field':field,'expected_value':value})
    assert len(tasks)==60
    payload={'version':'case-tasks-v1','dataset_type':'public_engineering_not_blind','created_on':'2026-10-25','expert_reviewed':False,'tasks':tasks}
    encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2).encode()
    if DEST.exists() and DEST.read_bytes()!=encoded:raise ValueError('v1 already frozen; use a new version')
    DEST.parent.mkdir(parents=True,exist_ok=True);DEST.write_bytes(encoded)
    DEST.with_suffix('.sha256').write_text(hashlib.sha256(encoded).hexdigest()+'\n',encoding='ascii')
    print('Frozen',len(tasks),'tasks;',hashlib.sha256(encoded).hexdigest())
if __name__=='__main__':main()
