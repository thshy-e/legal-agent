"""Manifest-only, date/jurisdiction filtered legal retrieval and atomic builds."""
from __future__ import annotations
from datetime import date
from pathlib import Path
from collections import Counter
import hashlib
import json
import math
import os
import re
import shutil
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / 'data' / 'legal_sources'
INDEX_DIR = ROOT / 'db' / 'legal_indexes'
CITIES = ('广州', '深圳', '珠海', '佛山', '惠州', '东莞', '中山', '江门', '肇庆')

def cn_number(value: str) -> int:
    if value.isdigit(): return int(value)
    digits = dict(zip('零一二三四五六七八九', range(10)))
    total = current = 0
    for ch in value:
        if ch in digits: current = digits[ch]
        elif ch in '十百千': total += (current or 1) * {'十':10,'百':100,'千':1000}[ch]; current = 0
    return total + current

def tokens(text):
    text = re.sub(r'\s+', '', text.lower())
    return re.findall(r'[a-z0-9]+', text) + [text[i:i+2] for i in range(len(text)-1)]

def applicable(record, city, on_date):
    areas = record['jurisdictions']
    if '全国' not in areas and not ('广东' in areas and city in CITIES) and city not in areas: return False
    if not on_date: return '全国' in areas and record.get('effective_to') is None
    return record['effective_from'] <= on_date and (not record.get('effective_to') or on_date < record['effective_to'])

def validate_manifest(manifest):
    errors = []; seen = set()
    required = ('id','title','issuer','url','jurisdictions','version','effective_from','verified_on','snapshot')
    for source in manifest['sources']:
        if source.get('id') in seen: errors.append('duplicate source: ' + source['id'])
        seen.add(source.get('id'))
        for key in required:
            if not source.get(key): errors.append(f"{source.get('id')}: missing {key}")
        path = SOURCE_DIR / source['snapshot']
        if not path.is_file(): errors.append(f"missing snapshot: {path.name}"); continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != source.get('sha256'): errors.append(f"hash mismatch: {path.name}")
        if source.get('kind') == 'law':
            articles = extract_articles(source, path.read_text(encoding='utf-8'))
            count=len({a['article'] for a in articles})
            if count != source.get('expected_articles'): errors.append(f"article count: {source['id']} {count} != {source.get('expected_articles')}")
    for record in manifest.get('cases',[]):
        key=record.get('id')
        if key in seen: errors.append('duplicate case: '+key)
        seen.add(key)
        for field in required+('original_text','key_facts','holding','limits','review_status'):
            if not record.get(field): errors.append(f'{key}: missing {field}')
        path=SOURCE_DIR/record.get('snapshot','__missing__')
        if not path.is_file(): errors.append(f'{key}: missing case snapshot');continue
        if hashlib.sha256(path.read_bytes()).hexdigest()!=record.get('sha256'): errors.append(f'{key}: case hash mismatch')
        if record.get('original_text','') not in path.read_text(encoding='utf-8'): errors.append(f'{key}: original text not found in snapshot')
        if record.get('normative_role')!='illustration_only': errors.append(f'{key}: case is not marked as reference only')
    for p in manifest.get('parameters', []):
        if p['purpose'] == 'severance_cap' and p.get('status') == 'verified' and not p.get('statistical_basis'):
            errors.append('cap lacks statistical basis: ' + p['id'])
    if errors: raise ValueError('; '.join(errors))

def extract_articles(source, text):
    # Snapshot has navigation or amendment decisions; start at the full law body.
    start = text.find(source.get('body_start', '第一条'))
    if start < 0: return []
    text = text[start:]
    matches = list(re.finditer(r'(?:^|\n)\s*第([零一二三四五六七八九十百千\d]+)条', text))
    result = []
    for i, match in enumerate(matches):
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        original = text[match.start():end].strip()
        if i == len(matches)-1 and source.get('body_end'): original = original.split(source['body_end'])[0].strip()
        number = cn_number(match.group(1))
        record={**source, 'id': f"{source['id']}:a{number}", 'source_id':source['id'],
                'article':number, 'original_text': original, 'summary':'', 'kind':'law'}
        partial=next((p for p in source.get('partial_repeals',[]) if p['article']==number),None)
        if partial:
            historical={**record,'id':record['id']+'@historical','effective_to':partial['effective_from']}
            result.append(historical)
            boundary=original.find(partial['surviving_text_start'])
            if boundary < 0: raise ValueError('partial repeal boundary not found: '+record['id'])
            record.update(effective_from=partial['effective_from'],original_text=original[boundary:],paragraph=2,
                          summary='第一款自'+partial['effective_from']+'废止，仅检索未废止的第二款；依据'+partial['authority'],version=source['version']+'-partial-repeal-20250901')
        result.append(record)
    return result

def build_index(activate=False, target=None):
    manifest = json.loads((SOURCE_DIR / 'manifest.json').read_text(encoding='utf-8'))
    validate_manifest(manifest)
    docs = []
    for source in manifest['sources']:
        text = (SOURCE_DIR / source['snapshot']).read_text(encoding='utf-8')
        docs.extend(extract_articles(source, text) if source['kind'] == 'law' else [{**source, 'original_text':text, 'summary':''}])
    docs.extend(manifest['cases'])
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    target = Path(target) if target else INDEX_DIR / (manifest['version'] + '-' + digest)
    target.mkdir(parents=True, exist_ok=True)
    payload = {'version':manifest['version'], 'digest':digest, 'documents':docs, 'parameters':manifest['parameters'], 'applicability_rules':manifest['applicability_rules']}
    candidate = target / 'index.json.tmp'
    candidate.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    check = json.loads(candidate.read_text(encoding='utf-8'))
    if len(check['documents']) != len(docs) or len({x['id'] for x in docs}) != len(docs): raise ValueError('index acceptance failed')
    os.replace(candidate, target / 'index.json')
    if activate:
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        pointer = INDEX_DIR / 'active.json'
        if pointer.exists(): shutil.copy2(pointer, INDEX_DIR / 'previous.json')
        tmp = INDEX_DIR / 'active.json.tmp'; tmp.write_text(json.dumps({'path':str(target.resolve()), 'digest':digest}), encoding='utf-8'); os.replace(tmp, pointer)
    return {'path':str(target), 'documents':len(docs), 'digest':digest, 'activated':activate}

class KnowledgeRegistry:
    def __init__(self, index_path=None):
        pointer = INDEX_DIR / 'active.json'
        if index_path is None and pointer.exists(): index_path = Path(json.loads(pointer.read_text(encoding='utf-8'))['path']) / 'index.json'
        if index_path is None:
            # Source manifest is authoritative even without a prebuilt local index.
            result = build_index(); index_path = Path(result['path']) / 'index.json'
        self.data = json.loads(Path(index_path).read_text(encoding='utf-8'))
        self.documents = self.data['documents']
        self.vector_path=Path(index_path).with_name('vectors.json')

    def search(self, query, city=None, on_date=None, kind='law', k=6):
        article = re.search(r'第\s*([\d零一二三四五六七八九十百千]+)\s*条', query)
        names = sorted({d['title'] for d in self.documents if d['kind']=='law'}, key=len, reverse=True)
        normalized=query.replace('(', '（').replace(')', '）')
        aliases={'劳动争议司法解释（一）':'最高人民法院关于审理劳动争议案件适用法律问题的解释（一）','劳动争议司法解释（二）':'最高人民法院关于审理劳动争议案件适用法律问题的解释（二）'}
        title = next((name for name in names if name in normalized or name.removeprefix('中华人民共和国') in normalized), None)
        if title is None: title=next((name for alias,name in aliases.items() if alias in normalized),None)
        exact = article and title
        candidates = [d for d in self.documents if d['kind']==kind and applicable(d,city,on_date)]
        if exact:
            return [d for d in candidates if d['title']==title and d.get('article')==cn_number(article.group(1))][:k]
        # Retain the original wording for exact lookup, but do not use the old
        # 60-day labour-law text as the current arbitration limitation rule.
        if not on_date or on_date>='2008-05-01': candidates=[d for d in candidates if d['id']!='labor-law-2018:a82']
        q = Counter(tokens(query)); n = len(candidates) or 1
        dfs = Counter(t for d in candidates for t in set(tokens(d.get('original_text','') + d['title'] + d.get('summary',''))))
        ranked = []
        for d in candidates:
            text = d.get('original_text','') + d['title'] + d.get('summary','')
            dt = Counter(tokens(text)); length = max(len(text),1)
            score = sum((1+math.log(n/(1+dfs[t])))*min(count,dt[t])*3/(1+length/500) for t,count in q.items() if dt[t])
            # Exact citation and BM25-like character n-grams share a filtered pool.
            # An optional embedding reranker may only rank these already eligible IDs.
            score += sum(3 for term in ('解除','补偿','工资','仲裁','证据') if term in query and term in text)
            if score > 0: ranked.append((score,d))
        ordered=[d for _,d in sorted(ranked,key=lambda row:row[0],reverse=True)]
        if os.getenv('LEGAL_VECTOR_SEARCH')=='1' and self.vector_path.exists():
            from legal_ai_agent.llm.qwen_llm import get_embedding
            vector_data=_read_index(str(self.vector_path),self.vector_path.stat().st_mtime_ns)
            if vector_data['digest']!=self.data['digest']: raise ValueError('vector version mismatch')
            qvector=get_embedding().embed_query(query)
            def cosine(d):
                v=vector_data['vectors'].get(d['id'],[])
                dot=sum(a*b for a,b in zip(v,qvector));norm=math.sqrt(sum(a*a for a in v)*sum(b*b for b in qvector))
                return dot/norm if norm else 0
            semantic=sorted(candidates,key=cosine,reverse=True)
            ranks={d['id']:1/(60+i) for i,d in enumerate(ordered)}
            for i,d in enumerate(semantic): ranks[d['id']]=ranks.get(d['id'],0)+1/(60+i)
            ordered=sorted(candidates,key=lambda d:ranks.get(d['id'],0),reverse=True)
        return ordered[:k]

    def by_id(self, source_id, city, on_date):
        return next((d for d in self.documents if d['id']==source_id and applicable(d,city,on_date)), None)

    def parameter(self, city, purpose, on_date):
        return next((p for p in self.data['parameters'] if p['city']==city and p['purpose']==purpose and p['effective_from']<=on_date and (not p.get('effective_to') or on_date<p['effective_to']) and p.get('status')=='verified'), None)

    def render(self, query, city=None, on_date=None, kind='law', k=4):
        records = self.search(query,city,on_date or date.today().isoformat(),kind,k)
        result='\n\n'.join(f"[{d['id']}] {d['title']} 第{d.get('article','—')}条\n{d.get('original_text','')}\n来源：{d['url']}\n版本：{d['version']}；核验：{d['verified_on']}" for d in records) or '未找到满足地域、日期和精确法名条号的资料；请补充或专业核验。'
        if any(d['id']=='labor-law-2018:a82' for d in records):
            current=self.by_id('arbitration-law-2008:a27',city,on_date or date.today().isoformat())
            if current: result+='\n适用说明：上述60日文字不作为现行时效结论，现行一般时效为一年并有中断、中止和在职欠薪例外。\n'+current['original_text']+'\n来源：'+current['url']
        return result

def coverage(city):
    if city in ('香港','澳门'): return {'city':city,'level':'out_of_scope','message':'港澳法律制度不纳入首期内地自动测算；需结合实际履行地专业判断。'}
    if city in ('广州','深圳'): return {'city':city,'level':'focused','message':'全国、广东及城市专项资料；经济补偿封顶口径仍需逐案核验。'}
    if city in CITIES: return {'city':city,'level':'province','message':'已覆盖全国及广东规则，城市专项资料待完善。'}
    return {'city':city,'level':'unknown','message':'请补充劳动合同履行地、单位所在地及争议日期；不确定城市专项结论。'}

@lru_cache(maxsize=8)
def _read_index(path,mtime):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def build_embeddings(index_path,embedding):
    payload=json.loads(Path(index_path).read_text(encoding='utf-8'));docs=payload['documents'];vectors={};dimension=None
    for offset in range(0,len(docs),20):
        batch=docs[offset:offset+20]
        values=embedding.embed_documents([d.get('original_text','')[:9000] for d in batch])
        if len(values)!=len(batch): raise ValueError('incomplete embedding response')
        for vector in values:
            if not vector or any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) for v in vector):
                raise ValueError('invalid embedding values')
            if dimension is None:dimension=len(vector)
            if len(vector)!=dimension:raise ValueError('inconsistent embedding dimension')
        vectors.update({d['id']:v for d,v in zip(batch,values)})
    if len(vectors)!=len(docs): raise ValueError('incomplete embedding response')
    target=Path(index_path).with_name('vectors.json');tmp=target.with_suffix('.tmp')
    tmp.write_text(json.dumps({'digest':payload['digest'],'dimension':dimension,'vectors':vectors}),encoding='utf-8');os.replace(tmp,target)
