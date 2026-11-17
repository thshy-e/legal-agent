"""Conversation intent and context policy. This module never mutates a case."""
import re

VERSION = 'conversation-20261026-v16'


def smalltalk(query):
    text = re.sub(r'[\s，。！？!?,~～]+', '', query)
    if re.fullmatch(r'(你好|您好|嗨|哈喽|在吗|你好呀)', text):
        return '你好，我在。你想了解哪方面的劳动法律问题？也可以直接说说遇到的情况。'
    if re.fullmatch(r'(谢谢|谢谢你|多谢|好的|好|明白了|知道了|收到|辛苦了|谢谢啦)', text):
        return '不客气，有不清楚的地方可以接着问。'
    if re.fullmatch(r'(我)?(有点|很|好|还是|非常)?(担心|害怕|焦虑|紧张)(怎么办|啊|了)?', text):
        return '遇到这种事有些担心很正常。我们可以一步一步梳理，不用一下把所有材料准备齐。你现在最担心哪一点？'
    return None


def is_followup(query):
    return bool(re.search(r'^(那|那么|但是|可是|所以|为什么|为何|怎么办|该怎么办|接下来|还有|如果是|公司说|单位说)|这一条|这条|这个规定|这是什么意思|上面|刚才|前面|第[一二三四五六七八九十\d]+[点项种]|再解释|展开说|通俗|举个例子', query))


def case_reference(query):
    return bool(re.search(r'我的(情况|案|工资|材料|请求)|我这个|本案|当前案件|结合我|按我|为什么.*(材料|流水|考勤|通知|合同)|为何.*(材料|流水)|这个(金额|请求|材料|案子)', query))


def wants_case(req, prior):
    query = str(req.get('query', '')).strip()
    if req.get('action') in ('confirm', 'generate_document', 'analyze') or 'facts' in req:
        return True
    if smalltalk(query):
        return False
    # Conceptual/hypothetical questions never become operations merely because
    # their nouns mention wages, compensation or a document.
    conceptual = bool(re.search(r'是什么|什么意思|是什么意思|怎么理解|区别|计算方法|计算公式|一般.*怎么算|为什么|为何|假设|举例|如果|第.+条|需要.*吗|要.*吗', query))
    action = bool(re.search(r'(帮我|给我|替我|请).{0,12}(写|起草|生成|准备).{0,10}(申请书|仲裁材料|文书)|^(写|生成|起草).{0,8}(申请书|仲裁申请书)|(?:分析|整理|核对|评估).{0,6}(我的案件|我的案子|我的情况)|(?:按|结合).{0,8}(我的情况|我的案子|我).{0,8}(算|分析|计算)|(?:帮我|给我)(?:算|计算)|重新算|重算|再算|能拿多少|赔我多少|赔偿多少|补偿多少|赔偿金.{0,5}(多少|计算)', query))
    if action and not conceptual:
        return True
    if prior and not conceptual and wage_revision(query,prior):
        return True
    if prior and not conceptual and not re.search(r'[？?]|吗|呢|是否|怎么|如何|规定', query):
        from legal_ai_agent.casework.facts import extract
        patch = extract(query)
        if patch:
            return True  # Fact-only answers to the current intake, checked by workflow.
    return req.get('workflow') == 'case' and (not query or not conceptual)


def context_for(query, history, case):
    followup = is_followup(query)
    # A standalone question must not inherit an unrelated salary or legal label.
    history = history if followup else []
    relevant = [t for t in history if t.get('route') != 'case']
    implicit_case = bool(history and history[-1].get('route') == 'case' and followup and re.search(r'为什么|第二|这|上面|刚才',query))
    if case and (case_reference(query) or implicit_case):
        relevant = history
    previous = next((t for t in reversed(relevant) if t.get('metadata', {}).get('retrieval_query')), None)
    topic = previous['metadata']['retrieval_query'] if previous else (relevant[-1]['query'] if relevant else '')
    lookup = (topic[:1500] + '\n追问：' + query) if followup and topic else query
    # Explanations can read a case snapshot, never write it or invoke confirmation.
    read_case = case if case and (case_reference(query) or implicit_case) else None
    ambiguous = followup and not relevant and read_case is None and bool(re.fullmatch(r'(那|那么)?(为什么|怎么办|该怎么办|第二点什么意思|这一条是什么意思|这个规定呢|这是什么意思)[？?。]*', query))
    return relevant, lookup, read_case, ambiguous


def ambiguous_wage_revision(query, case):
    if not case:
        return False
    if re.search(r'工资.{0,8}(改成|改为|更正为|实际是)',query) and not re.search(r'应付|实付|12个月|十二个月|平均|补偿工资基数|上月|前一个月|代通知金',query):
        return True
    return bool(re.search(r'(应付|实付)(?:工资)?.{0,5}(改成|改为|更正为|实际是|是|为)\s*\d',query)
                and not wage_revision(query,case))


def wage_revision(query, case):
    """Only update a uniquely identified existing wage period, never infer it."""
    from copy import deepcopy
    if re.search(r'假设|如果|不是|并非|没有|不改|未改|怎么|为何|为什么|[？?]',query):
        return None
    matches = list(re.finditer(r'(应付|实付)(?:工资)?\s*(?:改成|改为|更正为|实际是|是|为|：|:)\s*(\d+(?:\.\d{1,2})?)(?![\d.])',query))
    if not matches:
        return None
    wages = deepcopy(case.get('facts',{}).get('wages') or [])
    periods = re.findall(r'(20\d{2})[年/-](\d{1,2})(?:月|(?=-|$))',query)
    choices = list(range(len(wages)))
    if periods:
        months = {f'{int(y):04d}-{int(m):02d}' for y,m in periods}
        choices = [i for i,w in enumerate(wages) if w['start'][:7] in months and w['end'][:7] in months]
    if len(choices) != 1:
        return None
    row = wages[choices[0]]
    for name in ('应付','实付'):
        values = {m[2] for m in matches if m[1] == name}
        if len(values) > 1:
            return None
        if values:
            row['due' if name == '应付' else 'paid'] = values.pop()
    return wages


def consultation_sources(registry, query, city, on_date):
    """Anchor core topics in the existing, date-filtered registry, not new law."""
    if re.search(r'第\s*[\d零一二三四五六七八九十百千]+\s*条',query):
        return registry.search(query,city,on_date,k=4)
    ids = []
    if re.search(r'N\s*[+＋]\s*1|代通知金',query,re.I):
        ids = ['contract-law-2012:a40','contract-law-2012:a46','contract-law-2012:a47']
    elif re.search(r'证据|材料|工资流水|考勤|第[一二\d]+点',query):
        ids = ['arbitration-law-2008:a6','contract-law-2012:a30']
        if city in ('广州','深圳'):
            ids.append('gz-guide' if city == '广州' else 'sz-guide')
    elif re.search(r'签.{0,5}合同|签劳动合同|转正.{0,4}签|试用期',query):
        ids = ['contract-law-2012:a10','contract-law-2012:a19','contract-law-2012:a82']
        if '工资' in query: ids.append('contract-law-2012:a20')
    elif re.search(r'欠薪|拖欠工资|工资支付',query):
        ids = ['contract-law-2012:a30','labor-law-2018:a50','arbitration-law-2008:a6']
    records = [d for key in ids if (d := registry.by_id(key,city,on_date))]
    return records or registry.search(query,city,on_date,k=4)


def referenced_passage(query, history):
    match = re.search(r'第([一二三四五六七八九十\d]+)[点项种]',query)
    if not match:
        return None
    from legal_ai_agent.casework.knowledge import cn_number
    requested = cn_number(match[1])
    for turn in reversed(history):
        text = turn['answer']
        markers = list(re.finditer(r'(?:^|\n)\s*(\d+)[.、）)]\s*|第([一二三四五六七八九十]+)[，、：:]',text))
        if not markers:
            continue
        for i, marker in enumerate(markers):
            if cn_number(marker[1] or marker[2]) == requested:
                end = markers[i+1].start() if i+1 < len(markers) else len(text)
                passage = text[marker.start():end].strip()
                return re.split(r'根据|这些材料|上述材料|另外，|此外，',passage,maxsplit=1)[0].strip()
        return ''
    return ''
