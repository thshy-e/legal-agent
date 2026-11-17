"""Refresh official source snapshots. No credentials or embedding service required.

Snapshots are inputs for review, never silently activated as a production index.
"""
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
import hashlib
import json
import re
import subprocess
import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'legal_sources'
SOURCES = [
    ('labor-law-2018', 'https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_d9aa750028b14b99a776cb93726a360d.html'),
    ('contract-law-2012', 'https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_0abfdd261c03417b949df19d869add8d.html'),
    ('contract-regulation-2008', 'https://www.beijing.gov.cn/zhengce/gwywj/201105/t20110506_780976.html'),
    ('arbitration-law-2008', 'https://chinajob.mohrss.gov.cn/h5/c/2022-07-15/356212.shtml'),
    ('spc-labor-I-2021', 'https://www.sdcourt.gov.cn/jnanzqfy/xfkd/xfkd84/6793708/index.html'),
    ('spc-labor-II-2025', 'https://www.court.gov.cn/zixun/xiangqing/472691.html'),
    ('wage-interim-1995', 'https://rsj.sh.gov.cn/trlzyhshbzbgz_17256/20200617/t0035_1388318.html'),
    ('gd-wage-2016', 'https://www.huadu.gov.cn/zwfw/jyly6/gzfl/content/mpost_10647240.html'),
    ('sz-wage-2025', 'https://www.sz.gov.cn/zfgb/2026/gb1402/content/post_12621646.html'),
    ('sz-wage-2022', 'https://www.szgm.gov.cn/gmrlzyj/gkmlpt/content/10/10397/mpost_10397380.html'),
    ('gz-guide', 'https://rsj.gz.gov.cn/ywzt/ldgx/ldrszyzc/zcgg/content/post_2407253.html'),
    ('sz-guide', 'https://www.szgm.gov.cn/szgm/132104/132207/ldzc/content/post_9123962.html'),
    ('gd-disputes-2017', 'https://www.sz.gov.cn/cn/xxgk/zfxxgj/zcfg/content/post_8967143.html'),
    ('gd-disputes-2025', 'https://hrss.zs.gov.cn/zcy/zczn/bmcs/content/post_2521162.html'),
    ('minimum-2025', 'https://www.szlh.gov.cn/zmhd/wdzsk/content/post_12082310.html'),
    ('gz-minimum-2026', 'https://rsj.gz.gov.cn/ywzt/ldgx/tzgg/content/post_10981828.html'),
    ('sz-minimum-2026', 'https://hrss.sz.gov.cn/xxgk/qtxx/tzgg/content/post_12954949.html'),
    ('gz-cases-2025', 'https://www.gzcourt.gov.cn/yqfkdt/ck597/2025/10/17181128593.html'),
    ('gz-aid-case-2025', 'https://sfj.gz.gov.cn/gzssfj/flfw/pf/yasf/content/mpost_10127065.html'),
    ('sz-wage-cases-2025', 'https://hrss.sz.gov.cn/gkmlpt/content/12/12334/post_12334314.html'),
    ('sz-award-2023-11980','https://hrss.sz.gov.cn/ztfw/cjjy/wsgk/content/post_11007184.html'),
    ('sz-award-2021-281','https://hrss.sz.gov.cn/ztfw/cjjy/wsgk/content/post_10528740.html'),
    ('sz-award-2023-14951','https://hrss.sz.gov.cn/ztfw/cjjy/wsgk/content/post_11219114.html'),
    ('sz-award-2022-8372','https://hrss.sz.gov.cn/ztfw/cjjy/wsgk/content/post_11219002.html'),
    ('sz-award-2017-8169','https://hrss.sz.gov.cn/ztfw/cjjy/wsgk/content/post_8146130.html'),
    ('sz-award-2024-6977','https://www.szns.gov.cn/xxgk/bmxxgk/qrzj/xxgk/qt/tzgg/zcwsgk/content/post_12574663.html'),
]

class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'): self.hidden += 1
        if tag in ('p', 'div', 'br', 'li', 'h1', 'h2', 'h3', 'tr'): self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script', 'style'): self.hidden = max(0, self.hidden - 1)
        if tag in ('p', 'div', 'li', 'tr'): self.parts.append('\n')
    def handle_data(self, data):
        if not self.hidden: self.parts.append(data)

def fetch(item):
    key, url = item
    try:
        # Windows curl uses the system TLS stack (several government sites reject
        # Python/OpenSSL's EC negotiation). No TLS verification is disabled.
        try:
            response = subprocess.run(['curl.exe', '-fLsS', '--max-time', '35', '-A', 'Mozilla/5.0', url], capture_output=True, check=True)
            content = response.stdout
        except subprocess.CalledProcessError:
            response = httpx.get(url, timeout=35, follow_redirects=True)
            response.raise_for_status()
            content = response.content
        charset = re.search(br'charset=["\s]*([\w-]+)', content[:10000], re.I)
        encoding = charset.group(1).decode() if charset else 'utf-8'
        parser = TextParser(); parser.feed(content.decode(encoding, errors='replace'))
        text = '\n'.join(line.strip() for line in ''.join(parser.parts).splitlines() if line.strip())
        if len(text) < 300: raise ValueError('source too short; possible anti-bot response')
        (OUT / 'snapshots' / (key + '.txt')).write_text(text, encoding='utf-8')
        return dict(id=key, url=url, sha256=hashlib.sha256(text.encode()).hexdigest(), characters=len(text), status='downloaded')
    except Exception as exc:
        existing=OUT / 'snapshots' / (key + '.txt')
        result=dict(id=key, url=url, status='failed', error=type(exc).__name__ + ': ' + str(exc)[:180])
        if existing.exists():
            result.update(status='retained_snapshot_refresh_failed',sha256=hashlib.sha256(existing.read_bytes()).hexdigest(),characters=len(existing.read_text(encoding='utf-8')))
        return result

def main():
    (OUT / 'snapshots').mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=6) as pool: results = list(pool.map(fetch, SOURCES))
    (OUT / 'collection_report.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    for result in results: print(result['id'], result['status'], result.get('characters', ''), result.get('error', ''))

if __name__ == '__main__': main()
