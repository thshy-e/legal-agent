"""Conservative possession statements shared by case and consultation paths."""
import re

EVIDENCE_ALIASES={
    '劳动合同':('劳动合同',),'工资流水':('工资流水',),'解除通知':('解除通知','辞退通知'),
    '考勤':('考勤记录','考勤'),'聊天记录':('聊天记录',),'规章制度':('规章制度',),'工资条':('工资条',),
}

def evidence_statements(text,aliases=None):
    statuses={};conflicts=[]
    def asserted(match):
        before=re.split(r'[，。；;！？!?\n]',text[:match.start()])[-1]
        after=re.split(r'[，。；;！？!?\n]',text[match.end():])[0]
        return not (re.search(r'(?:是否|有没有|如果|假如|假设|要是|需要|建议|准备|希望|想要|公司|单位)',before) or (before.endswith('有') and match.group().startswith('没有')) or re.search(r'(?:吗|么)\s*$',after))
    for name,terms in (aliases or EVIDENCE_ALIASES).items():
        target='(?:'+'|'.join(re.escape(term) for term in terms)+')'
        missing=[m for m in re.finditer(r'(?:没有|没|未持有|缺少|无)\s*(?:任何)?'+target,text) if asserted(m)]
        present=[m for m in re.finditer(r'(?:持有|提供了|保存了|有)\s*'+target,text) if asserted(m)]
        ambiguous=any(re.search(r'(?:不是|并非|不属于)\s*$',text[max(0,m.start()-6):m.start()]) for m in missing)
        positive=any(not re.search(r'(?:没|没有|未|不|无|不是)\s*$',text[max(0,m.start()-6):m.start()]) for m in present)
        if ambiguous or (missing and positive):
            statuses[name]='unknown'
            conflicts.append({'field':'evidence.'+name,'message':name+'的持有陈述有矛盾或多重否定，请明确当前是否持有；不据此认定材料真实性。'})
        elif missing:statuses[name]='missing'
        elif positive:statuses[name]='claimed_present'
    return statuses,conflicts
