"""Competition documents only: preserve originals, render separately; no application imports."""
from pathlib import Path
import sys, re, json, math, hashlib, csv, zipfile, copy, importlib.util
ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'output/contest-submission-qa'
sys.path.insert(0,str(QA/'pydeps'))
from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.section import WD_SECTION_START
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from lxml import etree

BASE=ROOT/'docs/project'; AS=BASE/'contest_submission_assets'; AS.mkdir(exist_ok=True)
REF=BASE/'劳法智枢大挑申报说明书第一版.docx'
APP=BASE/'劳法智枢大挑作品申报书.docx'
OUTAPP=BASE/'劳法智枢大挑作品申报书（B3及C完善版）.docx'
BLUE='#17324D'; TEAL='#087F8C'; GRAY='#647383'; PALE='#F1F6F8'
FONT='C:/Windows/Fonts/simsun.ttc'
spec=importlib.util.spec_from_file_location('old_report',ROOT/'scripts/generate_contest_report_v1.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
ORIGINALS={str(p.relative_to(ROOT)):sha(p) for p in [REF,APP,BASE/'劳法智枢技术架构与核心创新说明.docx']}

def drawtext(d,xy,s,size=32,color=BLUE):
    d.text(xy,s,font=ImageFont.truetype(FONT,size),fill=color)

def box(d,r,s,accent=False):
    d.rounded_rectangle(r,radius=12,fill='#EFF8F8' if accent else PALE,outline=TEAL if accent else BLUE,width=3)
    f=ImageFont.truetype(FONT,28); ls=s.split('\n');x0,y0,x1,y1=r
    for j,line in enumerate(ls):
        w=d.textlength(line,font=f);assert w<x1-x0-20,(s,w)
        d.text(((x0+x1-w)/2,(y0+y1)/2-len(ls)*20+j*40),line,font=f,fill=BLUE)

def arrow(d,a,b):
    d.line([a,b],fill=GRAY,width=3);ang=math.atan2(b[1]-a[1],b[0]-a[0])
    d.polygon([b]+[(b[0]-13*math.cos(ang+t),b[1]-13*math.sin(ang+t)) for t in [-.5,.5]],fill=GRAY)

def diagrams():
    im=Image.new('RGB',(1600,1070),'white');d=ImageDraw.Draw(im)
    box(d,(270,20,1330,125),'浏览器工作台：自然咨询 · 案件核对 · 来源阅读 · 草稿',True)
    arrow(d,(800,125),(800,165))
    box(d,(270,165,1330,255),'FastAPI：会话隔离 · 版本校验 · 真实SSE事件')
    arrow(d,(480,255),(280,310));arrow(d,(1000,255),(1065,310))
    box(d,(30,310,530,415),'自然咨询\n最近对话 · 相关来源 · 只读解释')
    box(d,(610,310,1550,415),'LangGraph案件编排\n按条件推进 · 有界修订 · 等待用户确认',True)
    roles=[('接待','事实与缺口'),('检索','适用法源'),('Judge分析','请求与条件'),('计算工具','算式与金额'),('Review审查','问题与核对'),('Doc文书','当前确认稿')]
    for i,(role,task) in enumerate(roles):
        x=35+i*261;box(d,(x,485,x+225,595),role+'\n'+task,i in [3,4])
        if i<5:arrow(d,(x+225,540),(x+261,540))
    arrow(d,(1080,415),(1080,460));d.line([(145,460),(1450,460)],fill=GRAY,width=3)
    d.line([(145,460),(145,485)],fill=GRAY,width=3)
    drawtext(d,(530,625),'所有角色读取共享状态，按职责交接产物',30)
    box(d,(210,685,1390,800),'共享案件状态：事实 · 来源 · 请求 · 工具结果 · 审查 · 确认 · 版本',True)
    for x in [145,406,667,928,1189,1450]:
        d.line([(x,595),(x,665)],fill='#AAB9C2',width=2)
    d.line([(145,665),(1450,665)],fill='#AAB9C2',width=2);arrow(d,(800,665),(800,685))
    for r,s in [((40,885,510,1025),'版本清单与知识索引\n全国基础 · 广东 · 广深'),((565,885,1035,1025),'规则工具与JSON持久化\n金额十进制 · 下游失效'),((1090,885,1560,1025),'模型服务\n受限结构化分析与起草')]:box(d,r,s)
    for x in [280,800,1320]:arrow(d,(x,800),(x,885))
    im.save(AS/'fig1_architecture.png')
    im=Image.new('RGB',(1600,850),'white');d=ImageDraw.Draw(im)
    box(d,(300,20,1300,120),'共享案件状态：版本v · 事实 · 法源 · 请求 · 计算 · 草稿',True)
    nodes=[((40,210,460,345),'保存事实或依赖变更\n案件版本递增'),((590,210,1010,345),'重新检索、分析、计算\n审查并检查关键缺口'),((1140,210,1560,345),'等待用户核对\n当前事实、请求、金额'),((1140,590,1560,725),'确认绑定当前版本\n过期返回409并同步'),((590,590,1010,725),'形成当前草稿\n引用同一工具金额'),((40,590,460,725),'再次修改\n旧金额、确认、草稿失效')]
    for i,(r,s) in enumerate(nodes):box(d,r,s,i in [2,3])
    for a,b in [((460,277),(590,277)),((1010,277),(1140,277)),((1350,345),(1350,590)),((1140,657),(1010,657)),((590,657),(460,657)),((250,590),(250,345))]:arrow(d,a,b)
    arrow(d,(800,120),(800,210))
    drawtext(d,(525,420),'条件未齐：补充信息后重新核对',30)
    drawtext(d,(535,470),'确认与草稿始终关联同一案件版本',30)
    drawtext(d,(40,790),'编辑未保存时先暂停旧稿使用；明确保存后更新后端状态。',28,GRAY)
    im.save(AS/'fig2_versioning.png')

def screenshot(name):return Image.open(ROOT/'output/playwright'/('frontend-v18-'+name+'-desktop.png')).convert('RGB')
def pastefit(canvas,img,rect):
    x0,y0,x1,y1=rect;ratio=min((x1-x0)/img.width,(y1-y0)/img.height)
    img=img.resize((round(img.width*ratio),round(img.height*ratio)),Image.Resampling.LANCZOS)
    canvas.paste(img,(x0+(x1-x0-img.width)//2,y0+(y1-y0-img.height)//2))
def screenshots():
    # Crops retain original pixels/content; annotations are outside screenshot areas.
    im=Image.new('RGB',(1600,1040),'white');d=ImageDraw.Draw(im)
    drawtext(d,(30,20),'（a）自然咨询入口',34);drawtext(d,(870,20),'（b）本轮法源原文与版本',34)
    pastefit(im,screenshot('home').crop((445,160,1265,790)),(20,100,835,970))
    pastefit(im,screenshot('source').crop((940,195,1418,855)),(865,100,1580,970))
    im.save(AS/'fig3_consult_sources.png')
    im=Image.new('RGB',(1500,1390),'white');d=ImageDraw.Draw(im)
    drawtext(d,(25,15),'（a）三步核对：当前步骤与明确保存',34)
    guide=screenshot('guide')
    # Show navigation and save action, separated by white space, no invented field data.
    pastefit(im,guide.crop((940,533,1418,640)),(70,80,1430,385))
    pastefit(im,guide.crop((940,914,1418,998)),(70,395,1430,635))
    drawtext(d,(25,675),'（b）确认后的草稿：主体占位与请求金额',34)
    pastefit(im,screenshot('draft').crop((945,305,1405,600)),(260,735,1240,1365))
    im.save(AS/'fig4_guide_draft.png')
    im=Image.new('RGB',(1500,1130),'white');d=ImageDraw.Draw(im)
    for i,(name,title) in enumerate([('draft','（a）修订前：8000.10 - 1000.00 = 7000.10元'),('revised','（b）重新确认后：9000.10 - 1000.00 = 8000.10元')]):
        top=i*565;drawtext(d,(25,top+15),title,34)
        ss=screenshot(name)
        pastefit(im,ss.crop((965,497,1385,594)),(90,top+80,1410,top+355))
        pastefit(im,ss.crop((965,799,1280,883)),(230,top+360,1270,top+550))
    im.save(AS/'fig5_revision_screens.png')

def charts():
    raw=ROOT/'docs/evaluation/casework_v2/model_ablation.json'
    data=json.loads(raw.read_text(encoding='utf-8'))
    variants=['single_agent','collaboration_no_review','collaboration_review']
    labels=['单Agent','协同无审查','协同有审查'];colors=[BLUE,TEAL,GRAY]; summary=[];lat=[]
    for var,label in zip(variants,labels):
        rows=[r for r in data['rows'] if r['variant']==var];tr=[t for r in rows for t in r['trace'] if t['status']=='completed']
        assert len(rows)==60 and len(tr) in [60,120,180],(var,len(rows),len(tr))
        times=sorted(float(t['seconds']) for t in tr)
        tokens=sum(t['usage']['total_tokens'] for t in tr)
        flags=sum(bool(r['automatic_errors']) for r in rows)
        summary.append(dict(variant=var,label=label,outputs=len(rows),automatic_flags=flags,calls=len(tr),total_tokens=tokens,median_seconds=(times[(len(times)-1)//2]+times[len(times)//2])/2,max_seconds=max(times)))
        lat.extend(dict(variant=var,call_index=i+1,seconds=t) for i,t in enumerate(times))
    assert [s['automatic_flags'] for s in summary]==[15,2,8]
    assert [s['total_tokens'] for s in summary]==[791864,1588002,2402071]
    (AS/'experiment_aggregates.json').write_text(json.dumps({'source':'docs/evaluation/casework_v2/model_ablation.json','source_sha256':sha(raw),'statistic':'successful role calls; ECDF uses each observed seconds value','groups':summary},ensure_ascii=False,indent=2),encoding='utf-8')
    for name,rows in [('experiment_summary.csv',summary),('latency_seconds.csv',lat)]:
        with (AS/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    plt.rcParams.update({'font.family':'SimSun','font.size':11,'text.color':BLUE,'axes.labelcolor':BLUE,'xtick.color':BLUE,'ytick.color':BLUE,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':GRAY,'axes.axisbelow':True,'svg.fonttype':'none','axes.unicode_minus':False})
    fig,axs=plt.subplots(1,2,figsize=(10.5,4.6),layout='constrained')
    for ax,vals,title,lab in [(axs[0],[s['automatic_flags'] for s in summary],'（a）自动标记产物','份（每组60份产物）'),(axs[1],[s['total_tokens']/1e6 for s in summary],'（b）已报告token','百万token')]:
        ax.bar(labels,vals,color=colors,width=.58);ax.set_title(title,fontweight='normal',pad=18);ax.set_ylabel(lab);ax.set_ylim(0,max(vals)*1.28);ax.grid(axis='y',color='#E0E7EB')
        for i,v in enumerate(vals):ax.text(i,v+max(vals)*.035,str(int(v)) if ax is axs[0] else f'{v:.3f}',ha='center')
    for ext in ['png','svg']:fig.savefig(AS/f'fig6_experiment.{ext}',dpi=300,facecolor='white')
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(10.5,4.6),layout='constrained')
    for s,col in zip(summary,colors):
        ts=[x['seconds'] for x in lat if x['variant']==s['variant']];n=len(ts)
        ax.step([0]+ts,[0]+[(i+1)/n for i in range(n)],where='post',color=col,lw=2,label=f"{s['label']}（n={n}）")
    ax.set(xlabel='单次角色调用耗时 / 秒',ylabel='累计完成比例',xlim=(0,20),ylim=(0,1.03));ax.grid(color='#E0E7EB');ax.legend(loc='lower right',frameon=False)
    for ext in ['png','svg']:fig.savefig(AS/f'fig7_latency_ecdf.{ext}',dpi=300,facecolor='white')
    plt.close(fig)
    return summary

def runstyle(r,size=12,bold=False,east='宋体'):
    r.font.name='Times New Roman';r.font.size=Pt(size);r.bold=bold;r.font.color.rgb=RGBColor(0,0,0)
    r._r.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),east)

def inline(p,text,size=None):
    # Use explicit hyperlinks for bibliography. Preserve unlinked prose literally.
    for part in re.split(r'(https?://[^\s]+)',text):
        if part.startswith(('https://','http://')):
            tail=''
            while part.endswith(('.', '。', '；')):tail=part[-1]+tail;part=part[:-1]
            h=OxmlElement('w:hyperlink');h.set(qn('r:id'),p.part.relate_to(part,RT.HYPERLINK,is_external=True))
            r=OxmlElement('w:r');pr=OxmlElement('w:rPr');font=OxmlElement('w:rFonts');font.set(qn('w:ascii'),'Times New Roman');pr.append(font)
            c=OxmlElement('w:color');c.set(qn('w:val'),'17324D');pr.append(c)
            fs=OxmlElement('w:sz');fs.set(qn('w:val'),str(int((size or 10.5)*2)));pr.append(fs);r.append(pr)
            t=OxmlElement('w:t');t.text=part;r.append(t);h.append(r);p._p.append(h)
            if tail:p.add_run(tail)
        else:
            r=p.add_run(part)
            if size:runstyle(r,size)

def setup_doc():
    doc=Document(REF);body=doc._element.body
    secpr=copy.deepcopy(doc.sections[0]._sectPr)
    for child in list(body):body.remove(child)
    for e in list(secpr):
        if e.tag in [qn('w:headerReference'),qn('w:footerReference'),qn('w:pgNumType')]:secpr.remove(e)
    body.append(secpr)
    for s in ['Normal','Body Text','Caption','Header','Footer']:
        old.stylefont(doc.styles[s],12 if s in ['Normal','Body Text'] else (10.5 if s=='Caption' else 9))
    norm=doc.styles['Normal'].paragraph_format;norm.first_line_indent=Pt(24);norm.line_spacing=1.5;norm.space_after=Pt(0);norm.keep_with_next=False
    old.stylefont(doc.styles['Title'],22,'黑体')
    for n in [1,2]:
        old.stylefont(doc.styles[f'Heading {n}'],14 if n==1 else 12,'黑体' if n==1 else '宋体',n==2)
        pf=doc.styles[f'Heading {n}'].paragraph_format;pf.first_line_indent=Pt(0);pf.space_before=Pt(16 if n==1 else 10);pf.space_after=Pt(6);pf.keep_with_next=True;pf.page_break_before=False
    doc.styles['Caption'].paragraph_format.first_line_indent=Pt(0)
    for name in ['TOC 1','TOC 2']:
        if name not in doc.styles:doc.styles.add_style(name,1)
        old.stylefont(doc.styles[name],12)
        pf=doc.styles[name].paragraph_format;pf.line_spacing=1.05;pf.space_after=Pt(4);pf.left_indent=Pt(20 if name=='TOC 2' else 0);pf.first_line_indent=Pt(0)
    for e in list(doc.styles.element.iter(qn('w:pBdr'))):e.getparent().remove(e)
    return doc

def section(doc,kind,title):
    s=doc.add_section(WD_SECTION_START.NEW_PAGE)
    s.header.is_linked_to_previous=False;s.footer.is_linked_to_previous=False
    # python-docx property spelling is linked_to_previous for both headers and footers.
    s.header.is_linked_to_previous=False;s.footer.is_linked_to_previous=False
    for e in list(s._sectPr):
        if e.tag==qn('w:pgNumType'):s._sectPr.remove(e)
    num=OxmlElement('w:pgNumType');num.set(qn('w:start'),'1');num.set(qn('w:fmt'),'upperRoman' if kind=='front' else 'decimal');s._sectPr.append(num)
    hp=s.header.paragraphs[0];hp.text=title;hp.alignment=WD_ALIGN_PARAGRAPH.CENTER;hp.paragraph_format.first_line_indent=Pt(0)
    fp=s.footer.paragraphs[0];fp.alignment=WD_ALIGN_PARAGRAPH.CENTER;fp.paragraph_format.first_line_indent=Pt(0)
    f=OxmlElement('w:fldSimple');f.set(qn('w:instr'),'PAGE');fp._p.append(f)

def table(doc,rows,index):
    n=len(rows[0]);weights={1:[.13,.19,.20,.23,.25],2:[.20,.38,.42],3:[.24,.25,.51],4:[.18,.105,.18,.14,.20,.195]}[index]
    assert len(weights)==n
    # Normalize intentionally generous final column for project-specific mechanisms.
    weights=[w/sum(weights) for w in weights]
    t=doc.add_table(rows=0,cols=n);t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
    for col,w in zip(t.columns,weights):col.width=Cm(16*w)
    for ri,row in enumerate(rows):
        cells=t.add_row().cells;pr=t.rows[-1]._tr.get_or_add_trPr();pr.append(OxmlElement('w:cantSplit'))
        if ri==0:pr.append(OxmlElement('w:tblHeader'))
        for ci,(c,txt) in enumerate(zip(cells,row)):
            c.width=Cm(16*weights[ci]);c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tc=c._tc.get_or_add_tcPr();mar=OxmlElement('w:tcMar')
            for side,v in [('top',90),('bottom',90),('left',85),('right',85)]:
                x=OxmlElement('w:'+side);x.set(qn('w:w'),str(v));x.set(qn('w:type'),'dxa');mar.append(x)
            tc.append(mar);b=OxmlElement('w:tcBorders')
            for side in ['top','left','bottom','right']:
                x=OxmlElement('w:'+side);x.set(qn('w:val'),'single');x.set(qn('w:sz'),'4');x.set(qn('w:color'),'D9D9D9');b.append(x)
            tc.append(b);sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'E8EFF4' if ri==0 else ('F3F8F8' if (index==1 and ci==n-1) else ('F7F9FB' if ri%2==0 else 'FFFFFF')));tc.append(sh)
            p=c.paragraphs[0];p.paragraph_format.first_line_indent=Pt(0);p.paragraph_format.line_spacing=1.15;p.paragraph_format.space_after=Pt(0)
            p.paragraph_format.keep_with_next=ri==0
            p.alignment=WD_ALIGN_PARAGRAPH.CENTER if (ri==0 or index==4 or ci==0) else WD_ALIGN_PARAGRAPH.LEFT
            runstyle(p.add_run(txt),10.5,ri==0 or (index==1 and ci==n-1))
    return t

def build_md(src,main):
    doc=setup_doc();lines=src.read_text(encoding='utf-8').splitlines();i=0;cover=True;body=False;refs=False;tables=0
    title='劳法智枢研究与开发报告' if main else '劳法智枢软件运行操作与测试说明'
    while i<len(lines):
        line=lines[i].strip();i+=1
        if not line:continue
        if line.startswith('# '):
            p=doc.add_paragraph(line[2:],style='Title');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.first_line_indent=Pt(0);p.paragraph_format.space_before=Pt(90)
        elif line=='## 摘要':
            section(doc,'front',title);cover=False
            p=doc.add_paragraph('摘　要');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.first_line_indent=Pt(0);runstyle(p.runs[0],14,True)
        elif line=='## 目录':
            doc.add_page_break();p=doc.add_paragraph('目　录');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.first_line_indent=Pt(0);runstyle(p.runs[0],14,True)
        elif line=='<!-- WORD_TOC -->':
            p=doc.add_paragraph();p.paragraph_format.first_line_indent=Pt(0)
            f=OxmlElement('w:fldSimple');f.set(qn('w:instr'),'TOC \\o "1-2" \\h \\z \\u');p._p.append(f)
        elif line.startswith('## '):
            h=line[3:]
            if not body:section(doc,'body',title);body=True;cover=False
            elif h=='参考文献':doc.add_page_break()
            doc.add_paragraph(h,style='Heading 1');refs=h=='参考文献'
        elif line.startswith('### '):doc.add_paragraph(line[4:],style='Heading 2')
        elif line.startswith('$$'):old.equation(doc,line.strip('$'))
        elif re.match(r'^表\d+ ',line):
            p=doc.add_paragraph(line,style='Caption');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.keep_with_next=True
        elif line.startswith('|'):
            rows=[];i-=1
            while i<len(lines) and lines[i].strip().startswith('|'):
                row=[x.strip() for x in lines[i].strip().strip('|').split('|')];i+=1
                if not all(re.fullmatch(':?-+:?',x) for x in row):rows.append(row)
            tables+=1;table(doc,rows,tables)
        elif line.startswith('!['):
            m=re.fullmatch(r'!\[([^]]+)\]\(([^)]+)\)',line)
            p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.first_line_indent=Pt(0);p.paragraph_format.keep_with_next=True;p.paragraph_format.space_before=Pt(7)
            p.add_run().add_picture(str(BASE/m[2]),width=Cm(16))
            p=doc.add_paragraph(m[1],style='Caption');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.keep_with_next=False;p.paragraph_format.space_after=Pt(4)
        elif line.startswith('```'):
            if doc.paragraphs:doc.paragraphs[-1].paragraph_format.keep_with_next=True
            code_paragraphs=[]
            while i<len(lines) and not lines[i].strip().startswith('```'):
                p=doc.add_paragraph();p.paragraph_format.first_line_indent=Pt(0);p.paragraph_format.left_indent=Pt(12);p.paragraph_format.line_spacing=1.1;p.paragraph_format.space_after=Pt(3)
                p.paragraph_format.keep_together=True
                r=p.add_run(lines[i]);runstyle(r,10.5,east='宋体');r.font.name='Consolas';code_paragraphs.append(p);i+=1
            for p in code_paragraphs[:-1]:p.paragraph_format.keep_with_next=True
            i+=1
        else:
            p=doc.add_paragraph()
            if cover:
                p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.first_line_indent=Pt(0);p.paragraph_format.space_before=Pt(24)
                inline(p,line,12)
            elif line.startswith('资料来源：'):
                p.paragraph_format.first_line_indent=Pt(0);p.paragraph_format.line_spacing=1.05;p.paragraph_format.space_after=Pt(8);inline(p,line,9.5)
            elif refs:
                p.paragraph_format.first_line_indent=Pt(0);p.paragraph_format.line_spacing=1.15;p.paragraph_format.space_after=Pt(7);inline(p,line,10.5)
            else:inline(p,line)
    doc.core_properties.title=title;doc.core_properties.author='劳法智枢项目组';doc.core_properties.subject='2026年11月参赛书面材料'
    dest=src.with_suffix('.docx');doc.save(dest)
    stats=dict(path=str(dest.relative_to(ROOT)),tables=len(doc.tables),figures=len(doc.inline_shapes),equations=len(doc._element.xpath('.//m:oMath')))
    if main:assert (stats['tables'],stats['figures'],stats['equations'])==(4,7,3)
    return dest,stats

def fill_application():
    assert sha(APP)=='5b2194c87e03d208ce6d4ea1e6ea3e7179a383f7689434f5b47329932a82ff8e','Application source changed; re-audit latest user document'
    # Generate just the cell paragraphs, then transplant them without reserializing other ZIP parts.
    tmp=Document();src=(BASE/'申报书C栏国内外研究水平概述.md').read_text(encoding='utf-8')
    for line in src.splitlines():
        line=line.strip()
        if not line or line.startswith('# '):continue
        p=tmp.add_paragraph();pf=p.paragraph_format;pf.first_line_indent=Pt(24);pf.line_spacing=Pt(21);pf.space_before=Pt(0);pf.space_after=Pt(0);pf.widow_control=False;pf.keep_together=False;pf.keep_with_next=False
        ref=line.startswith('[') or line.startswith('资料核验')
        heading=bool(re.match(r'^（[1-4]）',line)) or line=='参考文献'
        if heading:pf.first_line_indent=Pt(0);pf.space_before=Pt(6)
        if ref:pf.first_line_indent=Pt(0);pf.line_spacing=Pt(16);pf.space_after=Pt(3)
        runstyle(p.add_run(line),10.5 if ref else 12,heading)
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    with zipfile.ZipFile(APP) as z:
        original=z.read('word/document.xml');root=etree.fromstring(original);tables=root.findall('w:body/w:tbl',ns);assert len(tables)==6
        cell=tables[-1].find('w:tr/w:tc',ns);assert not ''.join(cell.itertext()).strip(), 'C cell is no longer blank'
        for child in list(cell):
            if child.tag!=qn('w:tcPr'):cell.remove(child)
        for p in tmp.paragraphs:cell.append(copy.deepcopy(p._p))
        changed=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
        with zipfile.ZipFile(OUTAPP,'w',zipfile.ZIP_DEFLATED) as out:
            for info in z.infolist():out.writestr(info,changed if info.filename=='word/document.xml' else z.read(info.filename))
    with zipfile.ZipFile(APP) as a,zipfile.ZipFile(OUTAPP) as b:
        assert a.namelist()==b.namelist()
        for name in a.namelist():
            if name!='word/document.xml':assert a.read(name)==b.read(name),name
        ar=etree.fromstring(a.read('word/document.xml'));br=etree.fromstring(b.read('word/document.xml'))
        for rt in [ar,br]:
            c=rt.findall('w:body/w:tbl',ns)[-1].find('w:tr/w:tc',ns)
            for x in list(c):
                if x.tag!=qn('w:tcPr'):c.remove(x)
        assert etree.tostring(ar,method='c14n')==etree.tostring(br,method='c14n')
    return {'path':str(OUTAPP.relative_to(ROOT)),'only_C_cell_changed':True,'all_other_zip_parts_byte_identical':True,'main_prose_characters':len(src.split('参考文献')[0].split('\n',2)[2].replace('\n',''))}

if __name__=='__main__':
    QA.mkdir(exist_ok=True,parents=True);diagrams();screenshots();summary=charts()
    reports=[build_md(BASE/'劳法智枢研究与开发报告（参赛版）.md',True),build_md(BASE/'劳法智枢软件运行操作与测试说明.md',False)]
    app=fill_application()
    for rel,h in ORIGINALS.items():assert sha(ROOT/rel)==h,rel
    result={'date':'2026-11-02','original_sha256':ORIGINALS,'originals_unchanged':True,'reports':[s for _,s in reports],'application':app,'experiment_groups':summary,'model_calls_this_task':0,'application_tests_rerun':False}
    (QA/'build_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    for i,(p,_) in enumerate(reports,1):(QA/f'report{i}-path.txt').write_text(str(p),encoding='utf-8')
    (QA/'application-path.txt').write_text(str(OUTAPP),encoding='utf-8');(QA/'original-application-path.txt').write_text(str(APP),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
