import re


CASE_TREES = {
    "违法辞退": {
        "keywords": ["违法辞退", "无理由辞退", "无故辞退", "违法解除", "被辞退", "直接辞退"],
        "rights": ["违法解除赔偿金2N", "经济补偿N", "代通知金", "未结工资", "未休年休假工资"],
        "evidence": ["辞退通知", "劳动合同", "工资流水", "考勤记录", "规章制度", "违纪或考核证据"],
        "key_dispute": "公司是否能证明解除理由合法、程序合法且证据充分。",
    },
    "调岗降薪": {
        "keywords": ["调岗", "降薪", "变相降薪", "绩效降薪"],
        "rights": ["工资差额", "恢复原岗位/原薪资", "被迫解除经济补偿", "违法解除赔偿金"],
        "evidence": ["劳动合同", "岗位说明", "调岗通知", "工资流水", "绩效制度", "沟通记录"],
        "key_dispute": "调岗降薪是否经协商一致，是否具有合理性且不降低劳动条件。",
    },
    "工伤": {
        "keywords": ["工伤", "受伤", "停工留薪", "伤残", "工伤认定"],
        "rights": ["工伤认定", "停工留薪期工资", "医疗费", "一次性伤残补助金", "医疗补助金", "就业补助金"],
        "evidence": ["事故经过", "医院记录", "工伤认定申请", "劳动关系证明", "同事证言", "现场记录"],
        "key_dispute": "伤害是否发生在工作时间、工作场所并因工作原因造成。",
    },
    "未签合同": {
        "keywords": ["未签合同", "未签劳动合同", "未签书面劳动合同", "双倍工资"],
        "rights": ["双倍工资差额", "确认劳动关系", "经济补偿或赔偿金"],
        "evidence": ["工资流水", "工作证", "考勤记录", "聊天记录", "社保记录", "入职材料"],
        "key_dispute": "劳动关系起止时间和未签书面劳动合同期间能否证明。",
    },
    "加班费": {
        "keywords": ["加班", "996", "考勤", "加班费"],
        "rights": ["工作日加班费", "休息日加班费", "法定节假日加班费"],
        "evidence": ["考勤记录", "排班表", "加班审批", "工作消息", "工资条", "工作成果记录"],
        "key_dispute": "加班是否由公司安排或认可，具体时长能否证明。",
    },
}


def _detect_case_types(text: str) -> list[str]:
    detected = []
    for case_type, config in CASE_TREES.items():
        if any(keyword in text for keyword in config["keywords"]):
            detected.append(case_type)
    return detected or ["一般劳动争议"]


def _present_evidence(text: str, evidence_items: list[str]) -> list[str]:
    return [item for item in evidence_items if item in text]


def _extract_timeline(text: str) -> list[str]:
    patterns = [
        r"20\d{2}[年./-]\d{1,2}(?:[月./-]\d{1,2}日?)?",
        r"\d{4}[年./-]\d{1,2}(?:[月./-]\d{1,2}日?)?",
    ]
    matches = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, text))
    return list(dict.fromkeys(matches))


def build_case_analysis(case_info: str) -> str:
    text = str(case_info or "")
    case_types = _detect_case_types(text)
    sections = []

    for case_type in case_types:
        config = CASE_TREES.get(case_type)
        if not config:
            sections.append(
                "【案件树】\n"
                "- 案件类型：一般劳动争议\n"
                "- 建议先确认：劳动关系、工资基数、争议发生时间、证据材料。"
            )
            continue

        present = _present_evidence(text, config["evidence"])
        missing = [item for item in config["evidence"] if item not in present]
        sections.append(
            "【案件树】\n"
            f"- 案件类型：{case_type}\n"
            f"- 可主张权益：{'、'.join(config['rights'])}\n"
            f"- 关键争议：{config['key_dispute']}\n"
            "【证据缺口】\n"
            f"- 已提及证据：{'、'.join(present) if present else '暂无明确证据'}\n"
            f"- 建议补强：{'、'.join(missing[:5])}\n"
            "- 影响：关键证据不足会降低对应请求的证明力，尤其影响金额、违法性和劳动关系认定。"
        )

    timeline = _extract_timeline(text)
    sections.append(
        "【时间轴】\n"
        f"- 已识别时间节点：{'、'.join(timeline) if timeline else '暂无明确日期'}\n"
        "- 时效提示：劳动仲裁一般应在知道或应当知道权利受侵害之日起一年内申请。"
    )
    return "\n\n".join(sections)
