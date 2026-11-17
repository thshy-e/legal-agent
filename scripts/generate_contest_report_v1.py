"""Create the contest report; document-only, no model calls or app changes."""
from pathlib import Path
import re, math, json, hashlib
from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.section import WD_SECTION_START
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'docs/project'
SRC=BASE/'劳法智枢大挑申报说明书第一版.md'
OUT=SRC.with_suffix('.docx')
ASSETS=BASE/'contest_v1_assets'
BLUE='#17324D'; TEAL='#087F8C'; GRAY='#647383'
FONT='C:/Windows/Fonts/simsun.ttc'

def figure(name,size,boxes,edges):
    im=Image.new('RGB',size,'white');d=ImageDraw.Draw(im)
    f=ImageFont.truetype(FONT,32)
    for a,b in edges:
        d.line([a,b],fill=GRAY,width=3)
        theta=math.atan2(b[1]-a[1],b[0]-a[0])
        d.polygon([b]+[(b[0]-14*math.cos(theta+x),b[1]-14*math.sin(theta+x)) for x in [-.5,.5]],fill=GRAY)
    for rect,txt,accent in boxes:
        d.rounded_rectangle(rect,radius=10,fill='#EFF8F8' if accent else '#F3F6FA',outline=TEAL if accent else BLUE,width=3)
        lines=txt.split('\n');x1,y1,x2,y2=rect
        for i,line in enumerate(lines):
            w=d.textlength(line,font=f)
            assert w<x2-x1-18,(name,line)
            d.text(((x1+x2-w)/2,(y1+y2)/2-len(lines)*21+i*43),line,font=f,fill=BLUE)
    im.save(ASSETS/name)

def figures():
    ASSETS.mkdir(parents=True,exist_ok=True)
    figure('business_flow.png',(1440,670),[
        ((35,35,405,150),'用户自然提问',False),
        ((535,35,905,150),'普通咨询\n解释与查看依据',False),
        ((1035,35,1405,150),'明确案件操作\n核对事实与材料',True),
        ((1035,270,1405,385),'适用检索与分析\n工具计算和审查',False),
        ((535,270,905,385),'关键缺失或阻断\n追问或专业复核',False),
        ((1035,505,1405,620),'条件齐备\n用户确认当前版本',True),
        ((535,505,905,620),'草稿与一致性检查\n通过后供复制',False),
    ],[((1220,150),(1220,270)),((1035,327),(905,327)),((1220,385),(1220,505)),((1035,562),(905,562))])
    # Consultation and case branches are alternatives, not a mandatory serial chain.
    im=Image.open(ASSETS/'business_flow.png');d=ImageDraw.Draw(im)
    d.line([(220,150),(220,205),(720,205),(720,150)],fill=GRAY,width=3)
    d.polygon([(720,150),(712,165),(728,165)],fill=GRAY)
    d.line([(220,150),(220,225),(1220,225),(1220,150)],fill=GRAY,width=3)
    d.polygon([(1220,150),(1212,165),(1228,165)],fill=GRAY)
    im.save(ASSETS/'business_flow.png')
    figure('architecture.png',(1440,800),[
        ((320,20,1120,125),'浏览器工作台\n自然聊天  案件核对  来源  草稿',True),
        ((320,185,1120,285),'FastAPI接口\n会话绑定  JSON与真实SSE事件',False),
        ((35,355,665,465),'自然咨询\n相关历史与只读解释',False),
        ((775,355,1405,465),'LangGraph案件流程\n角色契约  计算  审查  确认',True),
        ((35,565,455,705),'清单知识库\n地域  时间  参数',False),
        ((510,565,930,705),'共享状态与规则\n事实  金额  版本  JSON',True),
        ((985,565,1405,705),'外部模型服务\n受限解释与结构化输出',False),
    ],[((720,125),(720,185)),((500,285),(350,355)),((950,285),(1090,355)),((220,465),(220,565)),((500,465),(620,565)),((900,465),(820,565)),((1220,465),(1220,565))])
    figure('versioning.png',(1440,550),[
        ((35,30,455,160),'版本1\n本金7000.10元  草稿有效',False),
        ((510,30,930,160),'保存修改\n应付改为9000.10元',True),
        ((985,30,1405,160),'旧产物失效\n金额  确认  草稿',False),
        ((985,355,1405,485),'重新分析审查\n本金8000.10元',False),
        ((510,355,930,485),'用户重新确认\n绑定版本2',True),
        ((35,355,455,485),'版本2草稿\n引用当前金额',False),
    ],[((455,95),(510,95)),((930,95),(985,95)),((1195,160),(1195,355)),((985,420),(930,420)),((510,420),(455,420))])
    # Shared typography and palette for the measured chart.
    im=Image.new('RGB',(1440,650),'white');d=ImageDraw.Draw(im);f=ImageFont.truetype(FONT,32)
    labels=['单智能体','协同\n无审查','协同\n有审查']
    for panel,(title,values,limit) in enumerate([('自动标记产物数',[15,2,8],20),('成功模型调用数',[60,120,180],200)]):
        x0=100+panel*710;y0=520;w=560;h=380
        d.text((x0,30),title,font=f,fill=BLUE)
        for tick in range(5):
            value=limit*tick/4;y=y0-h*tick/4
            d.line([(x0,y),(x0+w,y)],fill='#DFE5EA',width=1)
            d.text((x0-62,y-18),str(int(value)),font=f,fill=GRAY)
        for i,(lab,val) in enumerate(zip(labels,values)):
            x=x0+30+i*180;top=y0-val/limit*h
            d.rectangle((x,top,x+105,y0),fill=TEAL)
            d.text((x+25,top-40),str(val),font=f,fill=BLUE)
            for j,line in enumerate(lab.split('\n')):
                d.text((x-17,y0+20+j*36),line,font=f,fill=BLUE)
    im.save(ASSETS/'experiment.png')

def stylefont(s,size,east='宋体',bold=False):
    s.font.name='Times New Roman';s.font.size=Pt(size);s.font.bold=bold;s.font.cs_bold=bold
    s.font.color.rgb=RGBColor(0,0,0)
    s.element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),east)

def mr(txt):
    r=OxmlElement('m:r');t=OxmlElement('m:t');t.text=txt;r.append(t);return r
def sub(base,idx):
    n=OxmlElement('m:sSub');e=OxmlElement('m:e');e.append(mr(base));s=OxmlElement('m:sub');s.append(mr(idx));n.extend([e,s]);return n
def equation(doc,tag):
    p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.first_line_indent=Pt(0)
    m=OxmlElement('m:oMath')
    if tag=='FILTER':
        nodes=[sub('D','适用'),mr(' = {d ∈ D | R(d, r) ∧ T(d, t) ∧ K(d, k)}     （1）')]
    elif tag=='ARREARS':
        n=OxmlElement('m:nary');pr=OxmlElement('m:naryPr');c=OxmlElement('m:chr');c.set(qn('m:val'),'∑');pr.append(c)
        lo=OxmlElement('m:sub');lo.append(mr('i = 1'));up=OxmlElement('m:sup');up.append(mr('m'))
        e=OxmlElement('m:e');e.extend([mr('max('),sub('d','i'),mr(' − '),sub('p','i'),mr(', 0)')]);n.extend([pr,lo,up,e])
        nodes=[mr('A = '),n,mr('     （2）')]
    elif tag=='GATE':nodes=[mr('C = ('),sub('v','请求'),mr(' = '),sub('v','当前'),mr(') ∧ ¬M ∧ ¬B ∧ S     （3）')]
    else:
        frac=OxmlElement('m:f');num=OxmlElement('m:num');num.append(sub('n','严重'));den=OxmlElement('m:den');den.append(sub('n','已评'));frac.extend([num,den]);nodes=[sub('E','严重'),mr(' = '),frac,mr(' × 100%     （4）')]
    m.extend(nodes);p._p.append(m)

def build():
    figures();doc=Document()
    for b in list(doc.styles.element.iter(qn('w:pBdr'))):b.getparent().remove(b)
    sec=doc.sections[0];sec.page_width=Cm(21);sec.page_height=Cm(29.7)
    sec.top_margin=sec.bottom_margin=Cm(2.5);sec.left_margin=Cm(2.8);sec.right_margin=Cm(2.2)
    sec.header_distance=sec.footer_distance=Cm(1.25)
    for s in ['Normal','Body Text','Caption','Header','Footer']:stylefont(doc.styles[s],12 if s in ['Normal','Body Text'] else (10.5 if s=='Caption' else 9))
    norm=doc.styles['Normal'].paragraph_format;norm.first_line_indent=Pt(24);norm.line_spacing=1.5;norm.space_after=Pt(0)
    stylefont(doc.styles['Title'],22,'黑体',False)
    stylefont(doc.styles['Heading 1'],14,'黑体',False)
    stylefont(doc.styles['Heading 2'],12,'宋体',True)
    for n in [1,2]:
        pf=doc.styles[f'Heading {n}'].paragraph_format;pf.first_line_indent=Pt(0);pf.space_before=Pt(18 if n==1 else 10);pf.space_after=Pt(6);pf.keep_with_next=True
    doc.styles['Caption'].paragraph_format.first_line_indent=Pt(0)
    doc.styles.add_style('Frontmatter',1)
    stylefont(doc.styles['Frontmatter'],14,'黑体')
    doc.styles['Frontmatter'].paragraph_format.first_line_indent=Pt(0)
    lines=SRC.read_text(encoding='utf-8').splitlines();i=0;cover=True;inrefs=False;eqcount=0
    toc_entries=[]
    while i<len(lines):
        line=lines[i].strip()
        if not line:i+=1;continue
        if line.startswith('# '):
            p=doc.add_paragraph(line[2:],style='Title');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.space_before=Pt(90);p.paragraph_format.first_line_indent=Pt(0)
        elif line=='## 摘要':
            sec=doc.add_section(WD_SECTION_START.NEW_PAGE);cover=False
            sec.footer.is_linked_to_previous=False
            pg=OxmlElement('w:pgNumType');pg.set(qn('w:start'),'1');pg.set(qn('w:fmt'),'upperRoman');sec._sectPr.append(pg)
            fp=sec.footer.paragraphs[0];fp.alignment=WD_ALIGN_PARAGRAPH.CENTER;fp.paragraph_format.first_line_indent=Pt(0)
            ff=OxmlElement('w:fldSimple');ff.set(qn('w:instr'),'PAGE');fp._p.append(ff)
            p=doc.add_paragraph('摘　要',style='Frontmatter');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.first_line_indent=Pt(0);p.runs[0].bold=True;p.runs[0].font.size=Pt(14)
        elif line=='## Abstract':
            doc.add_page_break();p=doc.add_paragraph('Abstract',style='Frontmatter');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.runs[0].bold=True
        elif line=='## 目录':
            doc.add_page_break();p=doc.add_paragraph('目　　录');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.first_line_indent=Pt(0);p.runs[0].font.size=Pt(16);p.runs[0].bold=True
        elif line=='<!-- WORD_TOC -->':
            p=doc.add_paragraph();p.paragraph_format.first_line_indent=Pt(0)
            f=OxmlElement('w:fldSimple');f.set(qn('w:instr'),'TOC \\o "1-2" \\h \\z \\u \\t "Frontmatter,1"');p._p.append(f)
        elif line.startswith('## '):
            title=line[3:]
            if title.startswith('1 '):
                sec=doc.add_section(WD_SECTION_START.NEW_PAGE)
                sec.header.is_linked_to_previous=False;sec.footer.is_linked_to_previous=False
                pg=OxmlElement('w:pgNumType');pg.set(qn('w:start'),'1');pg.set(qn('w:fmt'),'decimal');sec._sectPr.append(pg)
                h=sec.header.paragraphs[0];h.text='劳法智枢大挑申报说明书';h.alignment=WD_ALIGN_PARAGRAPH.CENTER;h.paragraph_format.first_line_indent=Pt(0)
                p=sec.footer.paragraphs[0];p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.first_line_indent=Pt(0)
                f=OxmlElement('w:fldSimple');f.set(qn('w:instr'),'PAGE');p._p.append(f)
            elif title in ['参考文献','附录']:doc.add_page_break()
            p=doc.add_paragraph(title,style='Heading 1');inrefs=title=='参考文献'
        elif line.startswith('### '):doc.add_paragraph(line[4:],style='Heading 2')
        elif line.startswith('$$'):
            equation(doc,['FILTER','ARREARS','GATE','ERROR'][eqcount]);eqcount+=1
        elif line.startswith('表') and re.match(r'表\d+ ',line):
            p=doc.add_paragraph(line,style='Caption');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.keep_with_next=True
        elif line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                row=[x.strip() for x in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(':?-+:?',x) for x in row):rows.append(row)
                i+=1
            n=len(rows[0]);t=doc.add_table(rows=0,cols=n);t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
            weights=[.23,.28,.49]
            for c,w in zip(t.columns,weights):c.width=Cm(16*w)
            for ri,row in enumerate(rows):
                cells=t.add_row().cells;trpr=t.rows[-1]._tr.get_or_add_trPr();trpr.append(OxmlElement('w:cantSplit'))
                if ri==0:trpr.append(OxmlElement('w:tblHeader'))
                for ci,(c,txt) in enumerate(zip(cells,row)):
                    c.width=Cm(16*weights[ci]);c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
                    pr=c._tc.get_or_add_tcPr();mar=OxmlElement('w:tcMar')
                    for side in ['top','bottom','left','right']:
                        x=OxmlElement('w:'+side);x.set(qn('w:w'),'80');x.set(qn('w:type'),'dxa');mar.append(x)
                    pr.append(mar);b=OxmlElement('w:tcBorders')
                    for side in ['top','left','bottom','right']:
                        x=OxmlElement('w:'+side);x.set(qn('w:val'),'single' if (side=='top' and ri==0) or (side=='bottom' and ri in [0,len(rows)-1]) else 'nil');x.set(qn('w:sz'),'10' if ri in [0,len(rows)-1] else '4');x.set(qn('w:color'),'000000');b.append(x)
                    pr.append(b)
                    p=c.paragraphs[0];p.text=txt;p.paragraph_format.first_line_indent=Pt(0);p.paragraph_format.line_spacing=1.1
                    p.paragraph_format.keep_with_next=ri<2
                    if ri==0:p.alignment=WD_ALIGN_PARAGRAPH.CENTER
                    for r in p.runs:r.font.size=Pt(9);r.bold=ri==0
            continue
        elif line.startswith('!['):
            m=re.fullmatch(r'!\[([^]]+)\]\(([^)]+)\)',line)
            p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.first_line_indent=Pt(0);p.paragraph_format.keep_with_next=True
            p.add_run().add_picture(str(BASE/m[2]),width=Cm(16))
            p=doc.add_paragraph(m[1],style='Caption');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.keep_with_next=True
        else:
            p=doc.add_paragraph(line)
            if cover:p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.first_line_indent=Pt(0);p.paragraph_format.space_before=Pt(24)
            elif line.startswith('资料来源：'):
                p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.first_line_indent=Pt(0);p.paragraph_format.line_spacing=1.0;p.paragraph_format.space_after=Pt(8)
                for r in p.runs:r.font.size=Pt(9)
            elif inrefs:
                p.paragraph_format.line_spacing=1.0;p.paragraph_format.space_after=Pt(7)
            if line.startswith(('关键词：','Key words:')):p.runs[0].bold=True
        i+=1
    for name in ['TOC 1','TOC 2']:
        if name not in doc.styles:doc.styles.add_style(name,1)
        st=doc.styles[name];stylefont(st,12);st.paragraph_format.line_spacing=1.;st.paragraph_format.first_line_indent=Pt(0);st.paragraph_format.left_indent=Pt(24 if name=='TOC 2' else 0);st.paragraph_format.space_after=Pt(4)
    doc.core_properties.title='劳法智枢大挑申报说明书'
    doc.core_properties.author='劳法智枢项目组'
    doc.core_properties.subject='科技创新项目第一版 2026年10月31日'
    doc.save(OUT)
    print(json.dumps({'path':str(OUT),'characters':len(SRC.read_text(encoding='utf-8')),'tables':len(doc.tables),'figures':len(doc.inline_shapes),'equations':eqcount},ensure_ascii=False))

if __name__=='__main__':build()
