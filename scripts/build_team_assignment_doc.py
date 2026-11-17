from pathlib import Path
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "project" / "劳法智枢六人协作与AI实践分工方案.docx"


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_borders(cell, color="D9D9D9", size="6"):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        el = borders.find(qn(tag))
        if el is None:
            el = OxmlElement(tag)
            borders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), size)
        el.set(qn("w:color"), color)


def set_cell_margin(cell, top=100, start=120, bottom=100, end=120):
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.find(qn("w:tcMar"))
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for name, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn("w:" + name))
        if node is None:
            node = OxmlElement("w:" + name)
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_repeat_table_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def set_run_font(run, chinese="Microsoft YaHei", western="Arial", size=10.5, bold=None, color="000000"):
    run.font.name = western
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), chinese)
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), western)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), western)
    run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)


def add_field(paragraph, instr):
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    text = OxmlElement("w:instrText")
    text.set(qn("xml:space"), "preserve")
    text.text = instr
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([begin, text, separate, end])
    return run


def add_paragraph(doc, text="", bold_lead=None, style=None, first_indent=True, space_after=5):
    p = doc.add_paragraph(style=style)
    p.paragraph_format.line_spacing = 1.45
    p.paragraph_format.space_after = Pt(space_after)
    if first_indent and style is None:
        p.paragraph_format.first_line_indent = Pt(21)
    if bold_lead and text.startswith(bold_lead):
        r = p.add_run(bold_lead)
        set_run_font(r, bold=True)
        r = p.add_run(text[len(bold_lead):])
        set_run_font(r)
    else:
        r = p.add_run(text)
        set_run_font(r)
    return p


def add_numbered(doc, items):
    for item in items:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Pt(21)
        p.paragraph_format.first_line_indent = Pt(-21)
        p.paragraph_format.line_spacing = 1.4
        p.paragraph_format.space_after = Pt(4)
        r = p.add_run(item)
        set_run_font(r)


def add_table(doc, headers, rows, widths=None, center_cols=None):
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    header = table.rows[0]
    set_repeat_table_header(header)
    for idx, (cell, label) in enumerate(zip(header.cells, headers)):
        if widths:
            cell.width = Cm(widths[idx])
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        set_cell_shading(cell, "17324D")
        set_cell_borders(cell)
        set_cell_margin(cell)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(label)
        set_run_font(r, size=9.5, bold=True, color="FFFFFF")
    for ridx, row_data in enumerate(rows):
        row = table.add_row()
        for cidx, (cell, value) in enumerate(zip(row.cells, row_data)):
            if widths:
                cell.width = Cm(widths[cidx])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_borders(cell)
            set_cell_margin(cell)
            if ridx % 2:
                set_cell_shading(cell, "F2F7F8")
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center_cols and cidx in center_cols else WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.line_spacing = 1.2
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(str(value))
            set_run_font(r, size=9.2)
    doc.add_paragraph().paragraph_format.space_after = Pt(1)
    return table


def add_code_block(doc, lines):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    set_cell_shading(cell, "F5F7FA")
    set_cell_borders(cell, "D9D9D9")
    set_cell_margin(cell, top=80, start=150, bottom=80, end=150)
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.05
    for i, line in enumerate(lines):
        if i:
            p.add_run("\n")
        r = p.add_run(line)
        set_run_font(r, chinese="Microsoft YaHei", western="Consolas", size=8.5)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


doc = Document()
section = doc.sections[0]
section.page_width = Cm(21)
section.page_height = Cm(29.7)
section.top_margin = Cm(2.2)
section.bottom_margin = Cm(2.0)
section.left_margin = Cm(2.4)
section.right_margin = Cm(2.4)

styles = doc.styles
normal = styles["Normal"]
normal.font.name = "Arial"
normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
normal.font.size = Pt(10.5)

for name, size, before, after in (("Title", 22, 0, 16), ("Heading 1", 15, 16, 8), ("Heading 2", 12, 10, 5)):
    st = styles[name]
    st.font.name = "Arial"
    st._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    st.font.size = Pt(size)
    st.font.bold = True
    st.font.color.rgb = RGBColor(0, 0, 0)
    st.paragraph_format.space_before = Pt(before)
    st.paragraph_format.space_after = Pt(after)
    st.paragraph_format.keep_with_next = True

# Remove the border inherited by Word's built-in Title style.
title_style_ppr = styles["Title"]._element.get_or_add_pPr()
title_style_border = title_style_ppr.find(qn("w:pBdr"))
if title_style_border is not None:
    title_style_ppr.remove(title_style_border)

title = doc.add_paragraph(style="Title")
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
title.paragraph_format.space_before = Pt(12)
title.paragraph_format.space_after = Pt(10)
r = title.add_run("劳法智枢六人协作与AI实践分工方案")
set_run_font(r, size=22, bold=True)
title_ppr = title._p.get_or_add_pPr()
title_border = title_ppr.find(qn("w:pBdr"))
if title_border is not None:
    title_ppr.remove(title_border)

meta = doc.add_paragraph()
meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
meta.paragraph_format.line_spacing = 1.35
for i, line in enumerate(("第一版", "适用对象  六名AI零基础或非计算机专业同学", "组织方式  两人一组 共三组", "基础周期  一周")):
    if i:
        meta.add_run("\n")
    rr = meta.add_run(line)
    set_run_font(rr, size=11, color="425466")

doc.add_paragraph().paragraph_format.space_after = Pt(4)
add_paragraph(doc, "本方案用于把劳法智枢项目拆成六名同学可以完成的真实任务。三组分别负责系统测试、知识库候选资料和答辩材料；每组只提交一套共同成果，并保留一次完整的AI使用与人工核验过程。", first_indent=False, space_after=8)
add_paragraph(doc, "执行原则：任务量以一周内可完成为准；先保证事实、来源和数据真实，再考虑数量与美化；组员不直接修改正式知识库、核心代码和已定稿申报材料。", bold_lead="执行原则：", first_indent=False)

doc.add_heading("一 任务目标", level=1)
add_paragraph(doc, "本轮协作以劳法智枢项目为实践载体，通过测试、知识库补充和答辩材料制作三类低门槛任务，让成员在完成真实项目成果的同时，掌握基本的AI使用方法。")
add_paragraph(doc, "所有成员应经历“明确任务、向AI提问、检查输出、修正结果、形成交付”的完整过程。任务不以代码开发为前提，也不要求成员独立作出法律结论。")

doc.add_heading("二 总体分组", level=1)
add_table(doc, ["组别", "成员", "主要任务", "本轮核心交付"], [
    ["第一组\n功能与体验测试", "P01、P02", "完成指定流程，记录问题和用户理解偏差", "测试记录、问题清单、关键截图"],
    ["第二组\n知识库候选资料", "P03、P04", "查找并核验全国、广东、广州和深圳官方资料", "候选法源清单、官方链接、核验说明"],
    ["第三组\n答辩文档与PPT", "P05、P06", "整理现有报告、图件和数据，制作比赛表达材料", "PPT、讲稿、答辩问答"],
], widths=[3.2, 2.2, 6.1, 5.0], center_cols={0, 1})
add_paragraph(doc, "项目负责人负责发放材料、解释验收标准、统一收集成果，并决定测试建议和候选法源是否纳入正式系统。", first_indent=False)

doc.add_heading("三 第一组 功能与体验测试", level=1)
doc.add_heading("1 任务目标", level=2)
add_paragraph(doc, "从普通劳动者第一次使用系统的角度，检查咨询、查依据、欠薪核算、事实修订和草稿生成是否容易理解。测试重点是操作和表达是否清楚，不要求组员评价复杂法律结论。")
doc.add_heading("2 个人分工", level=2)
add_paragraph(doc, "P01负责桌面端正常流程：", bold_lead="P01负责桌面端正常流程：", first_indent=False)
add_numbered(doc, [
    "（1）连续询问试用期签合同、转正后再签和应如何准备，观察系统能否承接上下文。",
    "（2）查询《劳动合同法》第47条，打开来源，核对法名、条款、版本和官方链接。",
    "（3）填写广州欠薪案例：应付8000.10元、实付1000元，核对7000.10元并尝试确认和生成草稿。",
])
add_paragraph(doc, "P02负责修订与窄屏流程：", bold_lead="P02负责修订与窄屏流程：", first_indent=False)
add_numbered(doc, [
    "（1）将应付工资改为9000.10元，观察旧金额、确认和草稿是否失效，重新确认后是否为8000.10元。",
    "（2）切换对话并返回，检查原会话内容是否保留。",
    "（3）使用手机或窄屏检查输入框、来源面板、案件核对和草稿是否可以正常操作。",
])
doc.add_heading("3 提交与验收", level=2)
add_paragraph(doc, "两人共同提交一份测试记录。每个问题必须包含操作步骤、预期结果、实际结果、截图和影响说明。问题分为阻断、影响理解和体验建议三级。")
add_paragraph(doc, "完成五项指定任务；至少记录三条有效观察；重要问题能够复现；截图与文字一一对应；不使用真实身份证、工资流水或个人案件资料。", bold_lead="验收标准：", first_indent=False)

doc.add_heading("四 第二组 知识库候选资料", level=1)
doc.add_heading("1 任务目标", level=2)
add_paragraph(doc, "补充与劳动合同解除、经济补偿、代通知金和欠薪直接相关的官方资料。组员负责查找和整理候选资料，不负责判断某条规则一定适用于具体案件。")
doc.add_heading("2 个人分工", level=2)
add_paragraph(doc, "P03负责全国和广东省级资料：查找全国法律、行政法规、司法解释、人社部门文件及广东省工资支付、劳动争议处理和办事指引，本轮整理5至8条。", bold_lead="P03负责全国和广东省级资料：", first_indent=False)
add_paragraph(doc, "P04负责广州和深圳资料：查找两市现行工资支付规则、仲裁办事指南、材料要求和官方公开案例，本轮整理5至8条；历史版本单独标注。", bold_lead="P04负责广州和深圳资料：", first_indent=False)
doc.add_heading("3 记录和验收", level=2)
add_paragraph(doc, "每条资料记录法源名称、发布机关、发布日期、生效时间、适用地域、涉及问题、官方链接、当前状态、原文位置、核验日期和备注。当前状态只填写现行候选、历史版本或状态待核验。")
add_paragraph(doc, "两人共同提交10至16条候选资料。每条链接由本人实际打开；名称、机关、日期和地域与原文一致；不直接修改正式manifest.json，由项目负责人统一复核入库。", bold_lead="验收标准：", first_indent=False)

doc.add_heading("五 第三组 答辩文档与PPT", level=1)
doc.add_heading("1 任务目标", level=2)
add_paragraph(doc, "复用现有研究报告、架构图、系统截图和实验数据，形成一套简明、可信、适合比赛现场的答辩材料，重点说明项目解决什么问题、怎样工作、有什么创新和已有何种验证。")
doc.add_heading("2 个人分工", level=2)
add_paragraph(doc, "P05负责内容和讲稿：提炼每页的核心结论，编写约5分钟讲稿，整理项目定位、业务流程、核心创新、测试结果和应用价值。", bold_lead="P05负责内容和讲稿：", first_indent=False)
add_paragraph(doc, "P06负责PPT和答辩问答：放置现有图件和截图，统一字体与颜色，整理不少于15个答辩问题及参考答案，并组织一次模拟答辩。", bold_lead="P06负责PPT和答辩问答：", first_indent=False)
doc.add_heading("3 页面结构和验收", level=2)
add_paragraph(doc, "PPT控制在12至14页：项目定位、用户痛点、目标用户、业务流程、总体架构、多智能体协同、广深知识库、确定性计算、确认与版本联动、系统案例、测试实验、竞品差异、应用价值和总结。")
add_paragraph(doc, "内容与系统现状一致；数据能在现有记录中找到；截图与讲解对应；每页只有一个主要观点；5分钟内完成讲解；两人均能回答自己负责部分的问题。", bold_lead="验收标准：", first_indent=False)

doc.add_heading("六 统一AI使用要求", level=1)
add_paragraph(doc, "每组至少保存一次完整的AI使用记录，包括原始任务、第一次提示词、AI第一次输出、发现的问题、修改后的提示词、最终采用内容和人工核验方式。")
add_code_block(doc, [
    "你正在协助完成劳法智枢项目的【任务名称】。",
    "输入材料：【粘贴或说明材料范围】。",
    "请输出：【指定字段、结构或页数】。",
    "资料要求：【仅使用官方来源或现有项目材料】。",
    "请将无法确认的信息标记为待核验，不要自行补全。",
    "完成后列出仍需人工检查的内容。",
])
add_paragraph(doc, "AI可以辅助提取、归纳、改写、生成检查清单和整理格式。成员本人必须核对链接、日期、数字、页面操作和最终表达，不得把AI回答直接视为法律结论、测试事实或项目已实现功能。")

doc.add_heading("七 一周执行安排", level=1)
add_table(doc, ["时间", "工作内容", "阶段成果"], [
    ["第一天", "项目负责人讲解项目、演示一次任务、分发材料", "确认分工和交付格式"],
    ["第二至四天", "两人分别完成个人任务，保存AI使用记录", "个人初稿、截图或资料记录"],
    ["第五天", "组内交换检查，合并重复内容", "每组一套共同初稿"],
    ["第六天", "三组各用10分钟汇报，负责人提出修改项", "修改清单"],
    ["第七天", "完成修订并提交", "三套正式成果"],
], widths=[2.5, 8.5, 5.5], center_cols={0})
add_paragraph(doc, "如无法按期完成，应优先保证数据和来源真实，再缩减数量。不得为凑足数量编造测试结果、资料来源或项目能力。", first_indent=False)

doc.add_heading("八 成果提交与评分", level=1)
add_paragraph(doc, "每组建立一个以组别和日期命名的文件夹，至少包括正式成果、AI使用记录、截图或来源附件。")
add_table(doc, ["评价项目", "分值", "判断标准"], [
    ["成果完整度", "30", "完成指定任务，文件可以直接查看和复用"],
    ["信息与证据", "25", "操作、链接、数字和截图能够相互对应"],
    ["AI使用过程", "20", "保留提示词、问题发现和修正过程"],
    ["组内协作", "15", "两人分工明确，并完成交叉检查"],
    ["汇报表达", "10", "能说明AI如何参与以及哪些内容经过核验"],
], widths=[3.0, 2.0, 11.5], center_cols={0, 1})
add_paragraph(doc, "本轮不以成果数量评价个人，重点观察是否能把AI输出转化为经过检查的项目材料。", first_indent=False)

doc.add_heading("附录一 测试问题记录模板", level=1)
add_code_block(doc, ["问题编号：", "测试设备和浏览器：", "操作步骤：", "预期结果：", "实际结果：", "问题级别：阻断／影响理解／体验建议", "截图名称：", "是否可以稳定复现：", "建议："])

doc.add_heading("附录二 候选法源记录模板", level=1)
add_code_block(doc, ["法源名称：", "发布机关：", "发布日期：", "生效时间：", "适用地域：", "涉及问题：", "官方链接：", "当前状态：现行候选／历史版本／状态待核验", "原文或下载位置：", "核验日期：", "备注："])

doc.add_heading("附录三 答辩页面记录模板", level=1)
add_code_block(doc, ["页码和标题：", "本页核心结论：", "使用的图或数据：", "讲稿：", "预计用时：", "可能被问到的问题：", "回答依据："])

doc.add_heading("附录四 AI使用记录模板", level=1)
add_code_block(doc, ["本次任务：", "第一次提示词：", "AI第一次输出的主要问题：", "修改后的提示词：", "最终采用了哪些内容：", "人工核验了哪些内容：", "本次学到的AI使用方法："])

doc.add_heading("九 项目材料入口", level=1)
add_numbered(doc, [
    "（1）测试任务：docs/evaluation/frontend_v18/USABILITY_TEST.md。",
    "（2）正式法源清单：data/legal_sources/manifest.json，仅供查看和对照。",
    "（3）研究报告：docs/project/劳法智枢研究与开发报告（参赛版）.docx。",
    "（4）运行说明：docs/project/劳法智枢软件运行操作与测试说明.docx。",
    "（5）图件和验证材料：docs/project/参赛作品材料索引.md。",
])

header = section.header.paragraphs[0]
header.alignment = WD_ALIGN_PARAGRAPH.CENTER
rr = header.add_run("劳法智枢  六人协作任务书")
set_run_font(rr, size=9, color="647383")

footer = section.footer.paragraphs[0]
footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
rr = footer.add_run("第 ")
set_run_font(rr, size=9, color="647383")
field = add_field(footer, " PAGE ")
set_run_font(field, size=9, color="647383")
rr = footer.add_run(" 页")
set_run_font(rr, size=9, color="647383")

core = doc.core_properties
core.title = "劳法智枢六人协作与AI实践分工方案"
core.subject = "六名零基础成员的测试、知识库和答辩材料分工"
core.author = "劳法智枢项目组"

OUT.parent.mkdir(parents=True, exist_ok=True)
doc.save(OUT)
print(OUT)
