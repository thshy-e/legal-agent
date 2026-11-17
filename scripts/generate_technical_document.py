"""Build the technical document from its reviewed Markdown source.

Run with the Codex document runtime (python-docx and Pillow), not the app venv.
No model requests or legal-index mutations are performed.
"""
from pathlib import Path
import hashlib
import json
import math
import re
import textwrap

from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "docs" / "project"
SOURCE = PROJECT / "劳法智枢技术架构与核心创新说明.md"
TARGET = PROJECT / "劳法智枢技术架构与核心创新说明.docx"
ASSETS = PROJECT / "assets"
INK = "17324D"
TEAL = "087F8C"
FONT = Path("C:/Windows/Fonts/msyh.ttc")


def diagram(name, size, boxes, edges, note):
    im = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype(str(FONT), 29)
    small = ImageFont.truetype(str(FONT), 23)
    for a, b, label in edges:
        d.line((a, b), fill="#738595", width=4)
        theta = math.atan2(b[1] - a[1], b[0] - a[0])
        pts = [b] + [(b[0] - 16 * math.cos(theta + off), b[1] - 16 * math.sin(theta + off)) for off in (-0.45, 0.45)]
        d.polygon(pts, fill="#738595")
        if label:
            x = (a[0] + b[0]) / 2
            y = (a[1] + b[1]) / 2
            width = d.textlength(label, font=small)
            d.rectangle((x - width / 2 - 6, y - 19, x + width / 2 + 6, y + 16), fill="white")
            d.text((x - width / 2, y - 17), label, font=small, fill="#17324D")
    for rect, text, accent in boxes:
        x1, y1, x2, y2 = rect
        d.rounded_rectangle(rect, radius=14, fill="#EDF7F7" if accent else "#F3F6FA", outline="#087F8C" if accent else "#B8C5D1", width=3)
        lines = text.split("\n")
        for i, line in enumerate(lines):
            f = font if i == 0 else small
            w = d.textlength(line, font=f)
            d.text(((x1+x2-w)/2, (y1+y2)/2 - len(lines)*19 + i*40), line, font=f, fill="#17324D")
    d.text((35, size[1]-48), note, font=small, fill="#526576")
    im.save(ASSETS / name)


def figures():
    ASSETS.mkdir(parents=True, exist_ok=True)
    diagram("architecture.png", (1480, 960), [
        ((340, 25, 1140, 130), "浏览器工作台\n自然聊天  案件核对  依据阅读  草稿", True),
        ((340, 190, 1140, 290), "FastAPI 接口\nJSON / SSE  会话绑定  版本错误处理", False),
        ((55, 365, 680, 480), "自然咨询\nQA 与相关历史  只读案件解释", False),
        ((800, 365, 1425, 480), "LangGraph 案件工作流\n接待  检索  分析  计算  审查  确认  文书", True),
        ((55, 575, 470, 705), "知识注册表\n地域与时间过滤\n清单  原文  参数", False),
        ((535, 575, 945, 705), "确定性规则与工具\nPydantic / Decimal\n事实  条件  金额  版本", True),
        ((1010, 575, 1425, 705), "模型服务\n受限解释与结构化输出\nQwen / 可选向量", False),
        ((340, 790, 1140, 885), "本机状态与执行记录\n会话 JSON  共享案件  实际调用与失败", False),
    ], [
        ((740,130),(740,190),""), ((570,290),(365,365),"咨询"), ((910,290),(1110,365),"操作"),
        ((260,480),(260,575),""), ((580,480),(660,575),""), ((1100,480),(1210,575),""),
        ((920,480),(850,575),""), ((740,705),(740,790),""),
    ], "模型不拥有确认和金额权限；当前存储定位为单机单进程演示")
    diagram("workflow.png", (1480, 1150), [
        ((50,35,445,145),"接待 intake\n事实校验与冲突识别",False),
        ((545,35,940,145),"检索 retrieval\n地域与时间筛选",False),
        ((1040,35,1435,145),"分析 analysis\n逐请求意见与引用",False),
        ((1040,245,1435,355),"计算 calculation\n工具金额与缺失参数",True),
        ((545,245,940,355),"初审 analysis_review\n规则与独立模型",False),
        ((50,245,445,355),"引用修订\nanalysis_revision 限一次",False),
        ((50,465,445,575),"独立复审\nanalysis_recheck",False),
        ((545,465,940,595),"confirmation\n缺失或阻断则停止\n完整时等待用户确认",True),
        ((1040,465,1435,595),"停止并保留状态\n追问  专业复核  失败原因",False),
        ((545,745,940,850),"文书 document\n当前确认与固定金额",True),
        ((545,935,940,1040),"文书一致性审查\ndocument_review",False),
        ((1040,935,1435,1040),"有效准备草稿\n仍需材料和专业核对",False),
    ], [
        ((445,90),(545,90),""),((940,90),(1040,90),""),((1235,145),(1235,245),""),
        ((1040,300),(940,300),""),((545,300),(445,300),"引用问题"),
        ((250,355),(250,465),""),((445,520),(545,520),""),((745,355),(745,465),"无需修订"),
        ((940,530),(1040,530),"有阻断"),((745,595),(745,745),"用户确认当前版本"),
        ((745,850),(745,935),""),((940,990),(1040,990),"通过"),
    ], "展示实际节点，不展示内部推理；文书审查未过最多重生成一次，再失败停止")
    diagram("versioning.png", (1480, 730), [
        ((40,65,455,205),"版本 v1\n输入及金额 7000.10 元\n用户确认  草稿有效",False),
        ((535,65,945,205),"修改并保存事实\n应付工资改为 9000.10\n案件版本递增",True),
        ((1025,65,1440,205),"撤销旧产物\n分析  金额  确认  文书\n旧稿停止使用",False),
        ((1025,365,1440,505),"重新分析与测算\n当前金额 8000.10 元\n重新审查",False),
        ((535,365,945,505),"用户确认版本 v2\n快照与所选请求绑定\n过期确认返回 409",True),
        ((40,365,455,505),"新版本草稿\n金额直接引用计算对象\n通过内部一致性检查",False),
    ], [((455,135),(535,135),""),((945,135),(1025,135),""),((1230,205),(1230,365),""),((1025,435),(945,435),""),((535,435),(455,435),"")],
    "知识摘要、计算规则、工作流或模型配置变化，同样触发重新分析与确认")


def font_style(style, size, bold=False):
    style.font.name = "Microsoft YaHei"
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.cs_bold = bold
    style.font.color.rgb = RGBColor(0,0,0)
    style.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "微软雅黑")


def inline(paragraph, text):
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    for piece in re.split(r"(`[^`]+`|\*\*[^*]+\*\*)", text):
        run = paragraph.add_run(piece.strip("`*") if piece.startswith(("`", "**")) else piece)
        if piece.startswith("**"):
            run.bold = True
        if piece.startswith("`"):
            run.font.name = "Consolas"


def build():
    figures()
    document = Document()
    # The runtime's default template can contain a title border. Remove it.
    for border in list(document.styles.element.iter(qn('w:pBdr'))):
        border.getparent().remove(border)
    s = document.sections[0]
    s.page_width, s.page_height = Cm(21), Cm(29.7)
    s.top_margin, s.bottom_margin, s.left_margin, s.right_margin = Cm(1.9), Cm(1.8), Cm(2.0), Cm(2.0)
    s.header_distance, s.footer_distance = Cm(.8), Cm(.8)
    font_style(document.styles["Normal"], 10.5)
    normal = document.styles["Normal"].paragraph_format
    normal.line_spacing = 1.35
    normal.space_after = Pt(6)
    font_style(document.styles["Title"], 24, True)
    for label, size in (("Heading 1",16),("Heading 2",12.5),("Heading 3",11)):
        font_style(document.styles[label], size, True)
        pf = document.styles[label].paragraph_format
        pf.space_before, pf.space_after = Pt(14), Pt(7)
        pf.keep_with_next = True
    font_style(document.styles["Caption"], 9)
    font_style(document.styles["Header"], 8)
    font_style(document.styles["Footer"], 8)
    header = s.header.paragraphs[0]
    header.text = "劳法智枢  技术架构与核心创新说明"
    footer = s.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run("v18 技术说明 1.0   |   ")
    field = OxmlElement("w:fldSimple"); field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1; continue
        if line.startswith("```"):
            code=[]; i+=1
            while i < len(lines) and not lines[i].startswith("```"):
                code.extend(textwrap.wrap(lines[i], width=84, subsequent_indent="    ", replace_whitespace=False, drop_whitespace=False) or [""])
                i+=1
            p=document.add_paragraph()
            p.paragraph_format.line_spacing=1.1
            p.paragraph_format.space_after=Pt(8)
            r=p.add_run("\n".join(code));r.font.name="Consolas";r.font.size=Pt(8)
        elif line.startswith("|"):
            rows=[]
            while i < len(lines) and lines[i].strip().startswith("|"):
                row=[x.strip() for x in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", x) for x in row):rows.append(row)
                i+=1
            count=len(rows[0]); table=document.add_table(rows=0, cols=count)
            table.alignment=WD_TABLE_ALIGNMENT.CENTER; table.autofit=False
            if count==2: weights=[.30,.70]
            elif count==3:weights=[.23,.23,.54]
            elif count==4:weights=[.17,.28,.29,.26]
            else:weights=[.22]+[.78/(count-1)]*(count-1)
            if rows[0][0] in ("路径","编号"):weights=[.55,.45] if count==2 else [.13,.62,.25]
            if count==6:weights=[.23,.11,.13,.12,.22,.19]
            for col,w in zip(table.columns,weights):col.width=Cm(17*w)
            for ri,row in enumerate(rows):
                cells=table.add_row().cells
                trpr=table.rows[-1]._tr.get_or_add_trPr()
                trpr.append(OxmlElement("w:cantSplit"))
                if ri==0:trpr.append(OxmlElement("w:tblHeader"))
                for ci,(cell,txt) in enumerate(zip(cells,row)):
                    cell.width=Cm(17*weights[ci]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
                    tcpr=cell._tc.get_or_add_tcPr()
                    margins=OxmlElement("w:tcMar")
                    for side in ("top","left","bottom","right"):
                        node=OxmlElement("w:"+side);node.set(qn("w:w"),"80");node.set(qn("w:type"),"dxa");margins.append(node)
                    tcpr.append(margins)
                    borders=OxmlElement("w:tcBorders")
                    for side in ("top","left","bottom","right"):
                        node=OxmlElement("w:"+side);node.set(qn("w:val"),"single");node.set(qn("w:sz"),"4");node.set(qn("w:color"),"D9D9D9");borders.append(node)
                    tcpr.append(borders)
                    shading=OxmlElement("w:shd");shading.set(qn("w:fill"),INK if ri==0 else ("F3F6FA" if ri%2 else "FFFFFF"));tcpr.append(shading)
                    p=cell.paragraphs[0];p.paragraph_format.space_after=Pt(0);p.paragraph_format.line_spacing=1.2
                    if ri < min(3, len(rows)-1):
                        p.paragraph_format.keep_with_next=True
                    if ri==0 or (len(txt)<9 and ci>0):p.alignment=WD_ALIGN_PARAGRAPH.CENTER
                    inline(p,txt)
                    for run in p.runs:
                        run.font.size=Pt(8.5 if count<6 else 8)
                        if ri==0:run.bold=True;run.font.color.rgb=RGBColor(255,255,255)
            document.add_paragraph().paragraph_format.space_after=Pt(1)
            continue
        elif line.startswith("!["):
            m=re.fullmatch(r"!\[([^]]+)\]\(([^)]+)\)",line)
            path=(SOURCE.parent/m[2]).resolve()
            with Image.open(path) as im:
                width=min(17, (18.4*im.width/im.height))
            p=document.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.keep_with_next=True
            p.add_run().add_picture(str(path),width=Cm(width))
            p=document.add_paragraph(m[1],style="Caption");p.alignment=WD_ALIGN_PARAGRAPH.CENTER
        elif line.startswith("# "):
            document.add_paragraph(line[2:],style="Title")
        elif line.startswith("### "):
            document.add_paragraph(line[4:],style="Heading 2")
        elif line.startswith("## "):
            p=document.add_paragraph(line[3:],style="Heading 1")
            if line.startswith('## 附录C'):
                p.paragraph_format.page_break_before=True
        else:
            p=document.add_paragraph();inline(p,line)
        i+=1
    document.core_properties.title="劳法智枢技术架构与核心创新说明"
    document.core_properties.subject="v18 实现、创新机制、验证证据与边界"
    document.core_properties.author="劳法智枢项目组"
    document.core_properties.comments="依据项目源码和已有验证记录编制，法律专家评分待完成。"
    document.save(TARGET)
    record={"source":str(SOURCE.relative_to(ROOT)),"source_sha256":hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            "docx":str(TARGET.relative_to(ROOT)),"docx_sha256":hashlib.sha256(TARGET.read_bytes()).hexdigest(),
            "characters":len(SOURCE.read_text(encoding="utf-8")),"headings":len(re.findall(r"^#{1,3} ",SOURCE.read_text(encoding="utf-8"),re.M)),
            "tables":len(document.tables),"figures":len(document.inline_shapes),"render_review":"pending", "regressions_rerun":False,
            "new_model_calls":0,"scope":"Document authoring only; app source and legal rules unchanged"}
    out=ROOT/"docs/evaluation/technical_document_v18";out.mkdir(parents=True,exist_ok=True)
    (out/"validation.json").write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(record,ensure_ascii=True,indent=2))


if __name__=="__main__":
    build()
