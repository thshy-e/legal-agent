"""Create a reviewed catalog from official snapshots; inspect diffs before activation."""
from pathlib import Path
import hashlib
import json
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.collect_official_sources import SOURCES, OUT

URLS = dict(SOURCES)
URLS.update({'gd-disputes-2017':'https://www.sz.gov.cn/cn/xxgk/zfxxgj/zcfg/content/post_8967143.html',
             'gd-disputes-2025':'https://hrss.zs.gov.cn/zcy/zczn/bmcs/content/post_2521162.html',
             'sz-guide':'https://www.szgm.gov.cn/szgm/132104/132207/ldzc/content/post_9123962.html',
             'minimum-2025':'https://www.szlh.gov.cn/zmhd/wdzsk/content/post_12082310.html'})
CONFIG = [
 ('labor-law-2018','中华人民共和国劳动法','全国人民代表大会常务委员会','全国','2018-12-29',None,107),
 ('contract-law-2012','中华人民共和国劳动合同法','全国人民代表大会常务委员会','全国','2013-07-01',None,98),
 ('contract-regulation-2008','中华人民共和国劳动合同法实施条例','国务院','全国','2008-09-18',None,38),
 ('arbitration-law-2008','中华人民共和国劳动争议调解仲裁法','全国人民代表大会常务委员会','全国','2008-05-01',None,54),
 ('spc-labor-I-2021','最高人民法院关于审理劳动争议案件适用法律问题的解释（一）','最高人民法院','全国','2021-01-01',None,54),
 ('spc-labor-II-2025','最高人民法院关于审理劳动争议案件适用法律问题的解释（二）','最高人民法院','全国','2025-09-01',None,21),
 ('wage-interim-1995','工资支付暂行规定','劳动部','全国','1995-01-01',None,20),
 ('gd-wage-2016','广东省工资支付条例','广东省人民代表大会常务委员会','广东','2016-09-29',None,64),
 ('gd-disputes-2017','广东省劳动人事争议处理办法','广东省人民政府','广东','2017-05-01','2025-01-09',75),
 ('gd-disputes-2025','广东省劳动人事争议处理办法','广东省人民政府','广东','2025-01-09',None,74),
 ('sz-wage-2022','深圳市员工工资支付条例','深圳市人民代表大会常务委员会','深圳','2022-08-04','2025-12-05',62),
 ('sz-wage-2025','深圳市员工工资支付条例','深圳市人民代表大会常务委员会','深圳','2025-12-05',None,60),
]

def main():
    sources = []
    for key,title,issuer,area,start,end,count in CONFIG:
        path = OUT / 'snapshots' / (key+'.txt')
        sources.append(dict(id=key,title=title,issuer=issuer,jurisdictions=[area],effective_from=start,effective_to=end,
                            expected_articles=count,kind='law',version=key,verified_on='2026-10-25',verification='official_text_internal_check',
                            url=URLS[key],snapshot='snapshots/'+path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                            body_start='第一条',body_end={'contract-regulation-2008':'\n放弃','arbitration-law-2008':'\n劳动\n争议','spc-labor-I-2021':'\n【关闭】','spc-labor-II-2025':'\n相关链接','wage-interim-1995':'\n劳动部','gd-wage-2016':'\n相关附件','gd-disputes-2017':'\n分享到','gd-disputes-2025':'\n打印','sz-wage-2022':'\n发布','sz-wage-2025':'\n下载'}.get(key)))
        if key=='spc-labor-I-2021': sources[-1]['partial_repeals']=[{'article':32,'effective_from':'2025-09-01','surviving_text_start':'企业停薪留职人员','authority':'spc-labor-II-2025:a21'}]
    for key,title,area in [('gz-guide','广州市劳动人事争议仲裁办事指引','广州'),('sz-guide','劳动者申请劳动人事争议仲裁提交证据材料须知','深圳')]:
        path=OUT/'snapshots'/(key+'.txt')
        sources.append(dict(id=key,title=title,issuer=area+'人力资源和社会保障部门',jurisdictions=[area],effective_from='2021-09-01',effective_to=None,
                            kind='guide',version='snapshot-20261025',verified_on='2026-10-25',verification='historical_guide_recheck_before_filing',url=URLS[key],snapshot='snapshots/'+path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        sources[-1]['effective_from']='2023-03-13' if key=='gz-guide' else '2021-09-01'
    cases=[]
    gz=(OUT/'snapshots/gz-cases-2025.txt').read_text(encoding='utf-8')
    # Each case is extracted from its body, not the publication's table of contents.
    for i,title,outcome in [(1,'某信息公司集体劳动纠纷','mediation'),(4,'谭某与某食品公司劳动争议案','supported'),(5,'周某与某软件科技公司劳动争议案','rejected'),(6,'赵某与某投资公司、某实业公司劳动争议案','supported'),(7,'陈某与某网络科技公司劳动争议案','employer_evidence_insufficient'),(8,'李某与某加工厂劳动争议案','rejected')]:
        start=gz.rfind('\n'+title+'\n')+1
        next_title=re.search(r'\n[^\n]+(?:劳动争议案|纠纷案)\n——',gz[start+len(title):])
        end=start+len(title)+next_title.start() if next_title else gz.find('\n相关',start)
        if end < start: end=len(gz)
        original=gz[start:end].strip()
        facts=original.split('一、基本案情')[-1].split('二、')[0].strip()
        holding=original.split('二、')[-1].split('三、')[0].strip()
        cases.append(case('gz-2025-'+str(i),title,'广州',URLS['gz-cases-2025'],original,facts,holding,outcome,'court_typical_case' if i!=1 else 'mediation_typical_case'))
    aid=(OUT/'snapshots/gz-aid-case-2025.txt').read_text(encoding='utf-8')
    cases.append(case('gz-aid-2025-1','苏某自动淘汰解除法律援助案','广州',URLS['gz-aid-case-2025'],aid,'业绩未达标被自动淘汰，未先培训或调岗。','二审结合聊天记录认定宜视为用人单位提出并协商一致解除，支持工资、提成和经济补偿等；不是所有末位淘汰都直接判2N。','supported','legal_aid_report'))
    sz=(OUT/'snapshots/sz-wage-cases-2025.txt').read_text(encoding='utf-8')
    sections=list(re.finditer(r'\n案例([一二三四五])：([^\n]+)',sz))
    for i,m in enumerate(sections):
        end=sections[i+1].start() if i+1<len(sections) else sz.index('\n法律链接',m.start())
        original=sz[m.start():end].strip(); lines=original.splitlines()
        record=case('sz-wage-2025-'+str(i+1),m.group(2),'深圳',URLS['sz-wage-cases-2025'],original,lines[1],lines[-1],'criminal_conviction','administrative_criminal_typical_case')
        if i==1: record['limits'] += ' 官方报道中刑拘日期晚于判决日期，时间矛盾待核验，不作为日期事实依据。'
        cases.append(record)
    for profile in json.loads((OUT/'civil_case_profiles.json').read_text(encoding='utf-8')):
        key=profile['id'];path=OUT/'snapshots'/(key+'.txt');text=path.read_text(encoding='utf-8')
        issuer='深圳市南山区劳动人事争议仲裁委员会' if key=='sz-award-2024-6977' else '深圳市劳动人事争议仲裁委员会'
        start=text.find(issuer)
        if start<0: raise ValueError('award body missing: '+key)
        body=text[start:]
        # Cut site navigation without assuming the first social-share toolbar
        # precedes the body on every publishing site.
        body=body.split('\n分享到：')[0].split('\n相关附件')[0].split('\n扫一扫在手机打开当前页')[0].strip()
        if '裁决如下' not in body and '本委裁决如下' not in body: raise ValueError('award result missing: '+key)
        cases.append({**profile,'kind':'case','case_type':'official_arbitration_award','jurisdictions':['深圳'],
                      'issuer':issuer,'url':URLS[key],'version':'official-award-'+profile['published_on'],
                      'effective_from':profile['published_on'],'effective_to':None,'verified_on':'2026-10-25',
                      'snapshot':'snapshots/'+path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                      'original_text':body,'summary':profile['key_facts'],'normative_role':'illustration_only',
                      'review_status':'internal_check_not_expert_review',
                      'limits':profile['limits']+' 公开仲裁裁决仅作类案参考，不是普遍适用法源；后续诉讼、撤销及履行状态未独立核实。'})
    for record in cases:
        if record.get('snapshot'): continue
        key='gz-cases-2025' if record['id'].startswith('gz-2025') else ('gz-aid-case-2025' if record['id'].startswith('gz-aid') else 'sz-wage-cases-2025')
        path=OUT/'snapshots'/(key+'.txt')
        record.update(snapshot='snapshots/'+path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),normative_role='illustration_only')
    params=[]
    for city,old,new in [('广州','2500','2680'),('深圳','2520','2700')]:
        for start,end,value,key in [('2025-03-01','2026-09-01',old,'minimum-2025'),('2026-09-01',None,new,'gz-minimum-2026' if city=='广州' else 'sz-minimum-2026')]:
            params.append(dict(id=f'{city}-minimum-{start}',city=city,purpose='minimum_monthly_wage',value=value,unit='CNY/month',statistical_basis='全日制正常劳动月最低工资，不是经济补偿三倍封顶标准',effective_from=start,effective_to=end,url=URLS[key],verified_on='2026-10-25',status='verified'))
        params.append(dict(id=city+'-severance-cap-pending',city=city,purpose='severance_cap',value=None,statistical_basis='劳动合同法47条所指上年度职工月平均工资及适用口径待核验，禁止替代为社保缴费基数或最低工资',effective_from='2025-01-01',effective_to=None,url=None,verified_on='2026-10-25',status='pending'))
    manifest=dict(version='gba-2026-10-25-v1',sources=sources,cases=cases,parameters=params,applicability_rules=[
        {'id':'national-arbitration-limitation','issue':'劳动法82条与仲裁法27条时效','resolution':'现行劳动争议一般仲裁时效引用仲裁法27条，一年及其中断中止、在职欠薪例外；劳动法82条60日文字不作为现行时效结论。'},
        {'id':'wage-local-conflict','issue':'广东工资条例13条与深圳工资条例13条离职工资结清期限','resolution':'检索同时返回法源差异，禁止机械地方优先；具体适用需专业核验，不自动给出唯一期限。'},
        {'id':'notice-only-article40','issue':'代通知金条件','resolution':'限劳动合同法40条三类无过失解除且未提前30日书面通知；41条裁员不自动附加。'},
    ])
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('manifest:',len(sources),'sources;',len(cases),'cases;',len(params),'parameters')

def case(key,title,city,url,original,facts,holding,outcome,case_type):
    return dict(id=key,title=title,kind='case',case_type=case_type,jurisdictions=[city],issuer='广州市中级人民法院' if key.startswith('gz-2025') else ('广州市司法局' if key.startswith('gz-aid') else '深圳市人力资源和社会保障局'),url=url,version='official-2025',effective_from='2025-08-18' if city=='深圳' else ('2025-02-24' if key.startswith('gz-aid') else '2025-04-30'),effective_to=None,verified_on='2026-10-25',original_text=original,summary=facts, key_facts=facts,issues=title,holding=holding,outcome=outcome,limits='案例仅作类案参考；结果依赖个案证据，不能替代现行法条。刑事案例不证明普通欠薪必然构成犯罪或产生罚款给付。',review_status='internal_check_not_expert_review')

if __name__=='__main__': main()
