import re
from legal_ai_agent.casework.evidence import evidence_statements


CASE_TREES = {
    "解除争议": {
        "keywords": ["辞退", "解除", "裁员"],
        "rights": ["经济补偿N（限法定情形）", "违法解除赔偿金2N（限违法成立且符合救济条件，与N备选）", "代通知金（限第40条相关条件，不与2N累计）", "未结工资（逐期核对）"],
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
        "keywords": ["加班", "996", "加班费"],
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


def _evidence_view(text,evidence_items):
    aliases={item:('考勤记录','考勤') if item=='考勤记录' else ('辞退通知','解除通知') if item=='辞退通知' else (item,) for item in evidence_items}
    statuses,conflicts=evidence_statements(text,aliases)
    return statuses,conflicts


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

        statuses,conflicts = _evidence_view(text,config['evidence'])
        present = [item for item,status in statuses.items() if status=='claimed_present']
        absent = [item for item,status in statuses.items() if status=='missing']
        missing = [item for item in config["evidence"] if item not in present]
        sections.append(
            "【案件树】\n"
            f"- 案件类型：{case_type}\n"
            f"- 待核对的可能请求（不表示成立）：{'、'.join(config['rights'])}\n"
            f"- 关键争议：{config['key_dispute']}\n"
            "【证据缺口】\n"
            f"- 用户称持有（真实性未核验）：{'、'.join(present) if present else '暂无明确持有陈述'}\n"
            f"- 用户称缺失：{'、'.join(absent) if absent else '暂无明确缺失陈述'}\n"
            f"- 矛盾待澄清：{'；'.join(c['message'] for c in conflicts) if conflicts else '暂无'}\n"
            f"- 建议补强：{'、'.join(missing[:5])}\n"
            "- 影响：关键证据不足会降低对应请求的证明力，尤其影响金额、违法性和劳动关系认定。"
        )

    timeline = _extract_timeline(text)
    sections.append(
        "【时间轴】\n"
        f"- 已识别时间节点：{'、'.join(timeline) if timeline else '暂无明确日期'}\n"
        "- 时效提示：依据劳动争议调解仲裁法第27条，一般为知道或应当知道权利受侵害之日起一年，有中断、中止及劳动关系存续期间欠薪的例外；仅提到日期不足以直接认定已过时效。"
    )
    return "\n\n".join(sections)
