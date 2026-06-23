import asyncio
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from legal_ai_agent.agents.doc_agent import DocAgent
from legal_ai_agent.agents.judge_agent import JudgeAgent
from legal_ai_agent.agents.qa_agent import QAAgent
from legal_ai_agent.agents.risk_agent import RiskAgent
from legal_ai_agent.agents.router_agent import RouterAgent
from legal_ai_agent.config.settings import BASE_DIR, FRONTEND_DIR
from legal_ai_agent.memory.memory_manager import conversation_store
from legal_ai_agent.rag.vector_store import load_vector_store
from legal_ai_agent.tools.calculator import (
    build_calculation_context_from_query,
    calculate_compensation,
    calculation_missing_info_message,
    extract_case_facts,
    is_calculation_query,
)
from legal_ai_agent.tools.labor_tools import init_tools_db


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def load_knowledge_base():
    logger.info("正在加载法条向量库 ...")
    law_db = load_vector_store("labor_law")
    logger.info("正在加载案例向量库 ...")
    case_db = load_vector_store("labor_cases")

    if law_db is None or case_db is None:
        logger.warning("知识库未完整初始化；检索工具会返回暂无数据提示")

    init_tools_db(law_db, case_db)
    logger.info("知识库初始化完成")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await load_knowledge_base()
    yield


app = FastAPI(title="劳法智枢 API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


router = RouterAgent()
qa = QAAgent()
doc = DocAgent()
risk = RiskAgent()
judge = JudgeAgent()


def _count_cjk(text: str) -> int:
    return sum(1 for char in text if "\u4e00" <= char <= "\u9fff")


def _repair_mojibake(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    for encoding in ("latin1", "cp1252"):
        try:
            repaired = text.encode(encoding).decode("utf-8")
        except UnicodeError:
            continue
        if _count_cjk(repaired) > _count_cjk(text):
            return repaired
    return text


def _is_explicit_doc_intent(query: str) -> bool:
    text = str(query or "")
    return any(
        keyword in text
        for keyword in [
            "生成仲裁文书",
            "生成文书",
            "仲裁文书",
            "劳动仲裁申请书",
            "仲裁申请书",
            "帮我写",
            "起草",
            "文书",
            "申请书",
            "投诉书",
            "起诉状",
            "答辩状",
            "和解协议",
            "模板",
        ]
    )


def _is_explicit_risk_intent(query: str) -> bool:
    text = str(query or "")
    return any(
        keyword in text
        for keyword in [
            "风险评估",
            "合规",
            "规章制度",
            "公司规定",
            "管理制度",
            "违法风险",
            "法律风险",
            "用工风险",
        ]
    )


def _is_explicit_judge_intent(query: str) -> bool:
    text = str(query or "")
    return any(
        keyword in text
        for keyword in [
            "胜诉率",
            "胜诉概率",
            "胜算",
            "能否仲裁",
            "能不能仲裁",
            "仲裁预判",
            "案件预判",
            "证据强弱",
            "证据够不够",
            "维权路径",
            "怎么打官司",
            "仲裁胜算",
        ]
    )


def _is_general_law_query(query: str) -> bool:
    text = str(query or "")
    law_markers = ["劳动法", "劳动合同法", "社会保险法", "工伤保险条例", "劳动争议调解仲裁法"]
    question_markers = ["第", "条", "是什么", "规定", "怎么规定", "如何规定", "解释", "含义"]
    return any(marker in text for marker in law_markers) and any(marker in text for marker in question_markers)


def _mentions_case_context(query: str) -> bool:
    text = str(query or "")
    return any(
        keyword in text
        for keyword in [
            "结合上面",
            "结合上述",
            "结合前面",
            "结合我上面",
            "以上内容",
            "上面的情况",
            "我这个案子",
            "我的情况",
            "刚才",
            "前面说的",
            "上述情况",
            "这个案子",
            "这个情况",
        ]
    )


def _is_explicit_calculation_intent(query: str, calculation: dict[str, Any] | None = None) -> bool:
    text = str(query or "")
    if calculation and calculation.get("show"):
        return True
    return is_calculation_query(text) or any(
        keyword in text
        for keyword in [
            "赔多少",
            "赔我多少",
            "能赔",
            "赔偿多少",
            "补偿多少",
            "多少钱",
            "多少元",
            "金额",
            "算一下",
            "计算",
            "赔偿金",
            "补偿金",
        ]
    )


def _normalize_mode(mode: Any) -> str | None:
    text = str(mode or "").strip()
    return text if text in ["qa", "doc", "risk", "judge"] else None


def _resolve_effective_route(
    query: str,
    preferred_mode: str | None,
    state_summary: dict[str, Any] | None = None,
    calculation: dict[str, Any] | None = None,
    force_mode: bool = False,
    mode: str | None = None,
) -> tuple[str, str]:
    forced_mode = _normalize_mode(mode)
    normalized_preference = _normalize_mode(preferred_mode)

    if force_mode and forced_mode:
        return forced_mode, f"force_mode:{forced_mode}"

    if _is_explicit_doc_intent(query):
        return "doc", "explicit_doc_intent"
    if _is_explicit_calculation_intent(query, calculation):
        return "qa", "explicit_calculation_intent"
    if _is_explicit_risk_intent(query):
        return "risk", "explicit_risk_intent"
    if _is_explicit_judge_intent(query):
        return "judge", "explicit_judge_intent"

    if normalized_preference:
        return normalized_preference, f"preferred_mode:{normalized_preference}"

    routed = router.route(query, state_summary=state_summary) or "qa"
    return routed, f"router:{routed}"


def _resolve_route(query: str, forced_mode: str | None, state_summary: dict[str, Any] | None = None) -> str:
    return _resolve_effective_route(query, None, state_summary=state_summary, force_mode=True, mode=forced_mode)[0]


def _run_agent(route: str, query: str, session_id: str) -> str:
    if route == "qa":
        return qa.run(query, session_id=session_id)
    if route == "doc":
        return doc.run(query)
    if route == "risk":
        return risk.run(query)
    if route == "judge":
        return judge.run(query)
    return qa.run(query, session_id=session_id)


def _truthy_facts(facts: dict[str, Any] | None) -> dict[str, Any]:
    return {
        key: value
        for key, value in (facts or {}).items()
        if value is False or value not in (None, "", 0, [], {})
    }


def _merge_facts(*fact_sets: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for facts in fact_sets:
        merged.update(_truthy_facts(facts))
    return merged


def _format_fact_value(value: Any) -> str:
    if isinstance(value, float):
        return _format_plain_number(value)
    return str(value)


def _format_facts_for_prompt(facts: dict[str, Any] | None) -> str:
    labels = {
        "years": "工作年限",
        "employment_months": "在职月数",
        "salary": "月工资/工资基数",
        "termination_reason": "解除/辞退性质",
        "has_contract": "是否签订劳动合同",
        "injury_grade": "伤残等级",
    }
    lines = []
    for key, value in _truthy_facts(facts).items():
        label = labels.get(key, key)
        lines.append(f"- {label}: {_format_fact_value(value)}")
    return "\n".join(lines) if lines else "- 暂无已沉淀事实"


def _summarize_calculation_for_prompt(calculation: dict[str, Any] | None) -> str:
    if not calculation or not calculation.get("show"):
        return "- 暂无上次赔偿计算"
    fields = [
        ("状态", calculation.get("status")),
        ("金额", calculation.get("amount")),
        ("公式", calculation.get("formula")),
        ("工资基数", calculation.get("wage")),
        ("工作年限", calculation.get("years")),
        ("补偿月数", calculation.get("months")),
        ("赔偿类型", calculation.get("compensation_type")),
    ]
    lines = [f"- {label}: {value}" for label, value in fields if value not in (None, "", [], {})]
    raw = calculation.get("raw_result")
    if raw:
        lines.append(f"- 原始计算摘要: {strip_for_preview(raw, 220)}")
    return "\n".join(lines) if lines else "- 已有计算结果，但缺少可展示字段"


def _build_contextual_query(query: str, state_summary: dict[str, Any], facts: dict[str, Any]) -> str:
    if not state_summary.get("is_continuation") and not facts:
        return query

    return (
        "【前文案件状态】\n"
        f"{_format_facts_for_prompt(facts)}\n\n"
        "【上次赔偿计算】\n"
        f"{_summarize_calculation_for_prompt(state_summary.get('last_calculation'))}\n\n"
        "【本轮问题】\n"
        f"{query}"
    )


def _should_use_case_context(route: str, query: str, route_reason: str) -> bool:
    if _mentions_case_context(query):
        return True
    if _is_general_law_query(query) and route == "qa":
        return False
    if route in ["doc", "risk", "judge"]:
        return True
    return route_reason in {"router:judge", "explicit_judge_intent", "explicit_doc_intent", "explicit_risk_intent"}


def _build_agent_query(
    query: str,
    route: str,
    route_reason: str,
    state_summary: dict[str, Any],
    facts: dict[str, Any],
) -> str:
    if _should_use_case_context(route, query, route_reason):
        return _build_contextual_query(query, state_summary, facts)
    return query


def _build_structured_query(
    query: str,
    route: str,
    route_reason: str,
    state_summary: dict[str, Any],
    facts: dict[str, Any],
) -> str:
    if _should_use_case_context(route, query, route_reason):
        return _build_contextual_query(query, state_summary, facts)
    return query


def _calculation_context_from_facts(facts: dict[str, Any], query: str) -> dict[str, Any] | None:
    if not (is_calculation_query(query) or any(keyword in query for keyword in ["赔偿", "补偿", "金额", "多少", "重新算", "再算"])):
        return None

    context: dict[str, Any] = {}
    for key in ["years", "salary", "employment_months", "has_contract", "injury_grade"]:
        if key in facts:
            context[key] = facts[key]

    reason = facts.get("termination_reason")
    if reason:
        context["reason"] = "非法辞退" if reason == "待判断辞退" else reason
    if any(keyword in query for keyword in ["n+1", "N+1", "代通知金", "未提前通知"]):
        context["reason"] = "n_plus_1"
    elif any(keyword in query for keyword in ["2N", "2n", "违法", "无理由", "无故", "非法"]):
        context["reason"] = "非法辞退"
    elif any(keyword in query for keyword in ["N", "n", "合法解除", "经济补偿"]):
        context["reason"] = "合法解除"

    current_context = build_calculation_context_from_query(query)
    if current_context:
        if (
            current_context.get("reason") == "合法解除"
            and context.get("reason")
            and not any(keyword in query for keyword in ["合法解除", "经济补偿", "协商解除", "协商离职"])
        ):
            current_context = dict(current_context)
            current_context.pop("reason", None)
        context.update(_truthy_facts(current_context))

    if context.get("salary") and (context.get("years") or context.get("calc_type") == "notice_pay"):
        return context
    return current_context


def _extract_calculation_payload_with_state(query: str, facts: dict[str, Any]) -> tuple[dict[str, Any], str, bool]:
    direct_context = build_calculation_context_from_query(query)
    contextual_context = _calculation_context_from_facts(facts, query)
    context = contextual_context or direct_context
    used_previous = bool(contextual_context and (direct_context is None or contextual_context != direct_context))

    if context is None:
        if not is_calculation_query(query):
            return {"show": False}, "", False
        missing_text = calculation_missing_info_message(query)
        return {
            "show": True,
            "status": "missing_info",
            "title": "待补充后计算",
            "amount": "",
            "formula": "",
            "raw_result": missing_text,
            "missing": _extract_first(missing_text, [r"需要补充[:：]\s*([^\n]+)"]),
        }, missing_text, False

    result_text = calculate_compensation(context)
    calculation, _ = _extract_calculation_payload(query)
    if not calculation.get("show") or used_previous:
        amount = _extract_first(
            result_text,
            [
                r"(?:最终金额|合计金额|估算金额|税后估算金额)[:：]\s*([0-9][0-9,.\s]*)\s*元",
                r"月度补偿金[:：]\s*([0-9][0-9,.\s]*)\s*元",
            ],
        )
        formula = _extract_first(result_text, [r"计算公式[:：]\s*([^\n]+)"])
        compensation_type = _extract_first(result_text, [r"(?:解除/赔偿类型|赔偿类型)[:：]\s*([^\n]+)"])
        months = _extract_first(result_text, [r"(?:补偿月数|可主张月份|补缴月份|降薪期间|计算期间)[:：]\s*([0-9.]+)"])
        years = _extract_first(result_text, [r"工作年限[:：]\s*([0-9.]+)"])
        wage = _extract_first(result_text, [r"(?:工资基数|月工资|月工资基数|原月工资|本人工资/月工资)[:：]\s*([0-9][0-9,.\s]*)\s*元"])
        calculation = {
            "show": True,
            "status": "complete",
            "title": "赔偿计算结果",
            "amount": _format_plain_number(amount),
            "formula": formula,
            "wage": _format_plain_number(wage or context.get("salary", "")),
            "years": _format_plain_number(years or context.get("years", "")),
            "months": _format_plain_number(months),
            "compensation_type": compensation_type,
            "raw_result": result_text,
            "context": context,
        }

    return calculation, result_text, used_previous


def _extract_first(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1).strip()
    return ""


def _format_number_value(value: Any) -> str:
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return str(value or "")
    if number == int(number):
        return f"{int(number):,}"
    return f"{number:,.2f}".rstrip("0").rstrip(".")


def _format_plain_number(value: Any) -> str:
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return str(value or "")
    if number == int(number):
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _extract_calculation_payload(query: str) -> tuple[dict[str, Any], str]:
    context = build_calculation_context_from_query(query)
    if context is None:
        if not is_calculation_query(query):
            return {"show": False}, ""
        missing_text = calculation_missing_info_message(query)
        return {
            "show": True,
            "status": "missing_info",
            "title": "待补充后计算",
            "amount": "",
            "formula": "",
            "raw_result": missing_text,
            "missing": _extract_first(missing_text, [r"需要补充[:：]\s*([^\n]+)"]),
        }, missing_text

    result_text = calculate_compensation(context)
    amount = _extract_first(
        result_text,
        [
            r"(?:最终金额|合计金额|估算金额|税后估算金额)[:：]\s*([0-9][0-9,.\s]*)\s*元",
            r"月度补偿金[:：]\s*([0-9][0-9,.\s]*)\s*元",
        ],
    )
    formula = _extract_first(result_text, [r"计算公式[:：]\s*([^\n]+)"])
    compensation_type = _extract_first(result_text, [r"(?:解除/赔偿类型|赔偿类型)[:：]\s*([^\n]+)"])
    months = _extract_first(result_text, [r"(?:补偿月数|可主张月份|补缴月份|降薪期间|计算期间)[:：]\s*([0-9.]+)"])
    years = _extract_first(result_text, [r"工作年限[:：]\s*([0-9.]+)"])
    wage = _extract_first(result_text, [r"(?:工资基数|月工资|月工资基数|原月工资|本人工资/月工资)[:：]\s*([0-9][0-9,.\s]*)\s*元"])

    return {
        "show": True,
        "status": "complete",
        "title": "赔偿计算结果",
        "amount": _format_plain_number(amount),
        "formula": formula,
        "wage": _format_plain_number(wage or context.get("salary", "")),
        "years": _format_plain_number(years or context.get("years", "")),
        "months": _format_plain_number(months),
        "compensation_type": compensation_type,
        "raw_result": result_text,
        "context": context,
    }, result_text


def _infer_risk(query: str, route: str, calculation: dict[str, Any]) -> dict[str, Any]:
    text = str(query or "")
    if route == "error":
        return {"level": "high", "label": "服务异常", "score": 18, "caption": "当前请求未能完成，请稍后重试。"}
    if any(keyword in text for keyword in ["工伤", "孕期", "医疗期", "无理由辞退", "违法解除", "违法辞退", "降薪逼离"]):
        return {"level": "high", "label": "高风险", "score": 82, "caption": "用人单位行为或证据争议较强，建议优先固定原始证据。"}
    if calculation.get("status") == "missing_info":
        return {"level": "medium", "label": "信息不足", "score": 56, "caption": "关键数字或解除原因未补齐，结果需要二次校准。"}
    if route == "risk":
        return {"level": "medium", "label": "待评估", "score": 64, "caption": "需结合制度文本、民主程序和实际执行方式判断。"}
    return {"level": "medium", "label": "中风险", "score": 62, "caption": "结论取决于解除理由、工资基数和证据完整度。"}


def _build_evidence_items(query: str) -> list[dict[str, Any]]:
    text = str(query or "")
    items = [
        ("劳动合同", ["劳动合同", "合同", "入职", "未签"]),
        ("工资流水", ["工资", "月薪", "流水", "银行", "薪资"]),
        ("解除通知", ["解除", "辞退", "裁员", "离职", "通知"]),
        ("考勤记录", ["考勤", "加班", "打卡", "工时", "排班"]),
        ("沟通记录", ["微信", "聊天", "邮件", "录音", "沟通"]),
    ]
    evidence = []
    for label, keywords in items:
        mentioned = any(keyword in text for keyword in keywords)
        evidence.append(
            {
                "label": label,
                "status": "已提及" if mentioned else "待补充",
                "strength": 78 if mentioned else 38,
                "note": "可作为事实链条的一部分" if mentioned else "建议补齐后再提交",
            }
        )
    return evidence


def _build_timeline(query: str) -> list[dict[str, str]]:
    text = str(query or "")
    date_pattern = r"((?:19|20)\d{2}[年/-]\d{1,2}(?:[月/-]\d{1,2}日?)?|\d{1,2}月\d{1,2}日)"
    pieces = re.split(r"[。；;\n]", text)
    timeline = []
    for piece in pieces:
        if not piece.strip():
            continue
        date = _extract_first(piece, [date_pattern])
        if date or any(keyword in piece for keyword in ["入职", "解除", "辞退", "降薪", "工伤", "仲裁", "离职"]):
            timeline.append({"date": date or "待核实", "text": piece.strip()[:80]})
        if len(timeline) >= 4:
            break
    return timeline or [{"date": "待补充", "text": "补充入职、解除、离职、仲裁申请等节点后，可形成完整时间线。"}]


def _build_actions(route: str, calculation: dict[str, Any]) -> list[dict[str, str]]:
    if calculation.get("status") == "missing_info":
        return [
            {"label": "补齐数字", "text": "先补充月工资、工作年限、解除原因和具体期间。"},
            {"label": "固定证据", "text": "同步保存劳动合同、工资流水、解除通知和沟通记录。"},
            {"label": "再做测算", "text": "信息补齐后再确认 N、N+1、2N 或其他项目。"},
        ]
    if calculation.get("show"):
        return [
            {"label": "核对基数", "text": "用离职前十二个月平均工资校准工资基数。"},
            {"label": "锁定解除理由", "text": "重点证明公司解除依据是否成立、程序是否合规。"},
            {"label": "准备请求", "text": "仲裁请求中分别列明赔偿、补偿、工资差额等项目。"},
        ]
    if route == "doc":
        return [
            {"label": "补充主体", "text": "补齐公司名称、地址、法定代表人和个人身份信息。"},
            {"label": "核对请求", "text": "将金额请求、事实理由和证据目录逐项对应。"},
        ]
    if route == "risk":
        return [
            {"label": "保留制度文本", "text": "保存规章制度、通知、签收和执行记录。"},
            {"label": "核查程序", "text": "确认是否经过民主程序、公示告知和一致执行。"},
        ]
    return [
        {"label": "整理事实", "text": "按时间顺序梳理入职、变更、解除和沟通经过。"},
        {"label": "补强证据", "text": "优先准备合同、流水、通知、考勤和聊天记录原件。"},
        {"label": "选择路径", "text": "根据争议类型选择协商、投诉、仲裁或诉讼。"},
    ]


def _build_issues(query: str, route: str, calculation: dict[str, Any]) -> list[str]:
    if calculation.get("show"):
        return ["解除原因是否成立", "工资基数和工作年限是否可证明", "能否适用 2N、N+1 或其他计算规则"]
    if route == "judge":
        return ["公司行为是否违法", "劳动者证据是否足以支撑主张", "仲裁请求和时效是否清晰"]
    if route == "risk":
        return ["制度依据是否有效", "执行过程是否一致", "员工救济路径是否被限制"]
    if route == "doc":
        return ["请求事项是否完整", "事实理由是否对应证据", "法律依据是否支撑主张"]
    return ["适用规则是否明确", "关键事实是否完整", "下一步维权路径是否可执行"]


def _build_structured_payload(query: str, route: str, answer: str, calculation: dict[str, Any]) -> dict[str, Any]:
    risk = _infer_risk(query, route, calculation)
    evidence = _build_evidence_items(query)
    evidence_count = sum(1 for item in evidence if item["status"] == "已提及")

    if calculation.get("show") and calculation.get("amount"):
        primary_metric = {
            "label": "赔偿金额",
            "value": _format_number_value(calculation["amount"]),
            "unit": "元",
            "kind": "amount",
            "caption": "由本地公式引擎提取，需结合证据复核。",
        }
    elif route == "judge":
        primary_metric = {"label": "胜诉概率", "value": "待评估", "unit": "", "kind": "probability", "caption": "结合事实和证据动态判断。"}
    else:
        primary_metric = {"label": "分析状态", "value": "已生成", "unit": "", "kind": "status", "caption": "AI 正文负责解释和策略。"}

    return {
        "route": route,
        "calculation": calculation,
        "metrics": [
            primary_metric,
            {"label": "风险等级", "value": risk["label"], "unit": "", "kind": "risk", "caption": risk["caption"]},
            {"label": "证据完整度", "value": f"{evidence_count}/5", "unit": "", "kind": "evidence", "caption": "按已提及证据类型估算。"},
        ],
        "risk": risk,
        "evidence": evidence,
        "timeline": _build_timeline(query),
        "actions": _build_actions(route, calculation),
        "issues": _build_issues(query, route, calculation),
        "answer_preview": strip_for_preview(answer),
    }


def strip_for_preview(text: str, limit: int = 80) -> str:
    preview = re.sub(r"\s+", " ", str(text or "")).strip()
    return preview[:limit]


def _build_calculation_strategy_answer(query: str, structured: dict[str, Any]) -> str:
    calculation = structured.get("calculation", {})
    if calculation.get("status") == "missing_info":
        missing = calculation.get("missing") or "工资、年限、解除原因等关键事实"
        return (
            f"当前还不能直接判断赔偿路径，关键缺口在于：{missing}。\n\n"
            "建议先把工资基数、工作年限、解除通知或离职原因补齐，再判断是经济补偿、代通知金，还是违法解除赔偿。\n\n"
            "在补充信息前，先保存劳动合同、工资流水、考勤和公司沟通记录，避免后续主张时只剩口头描述。"
        )

    compensation_type = calculation.get("compensation_type") or "当前测算路径"
    if "2N" in compensation_type or any(keyword in query for keyword in ["违法", "无理由", "无补偿", "突然辞退"]):
        focus = "当前争议核心不在测算数字本身，而在于公司是否构成违法解除。"
        strategy = "如果公司拿不出合法解除理由、制度依据或送达证据，主张违法解除赔偿的空间会更大。"
    else:
        focus = "当前重点不是重复公式，而是确认解除类型和工资基数是否能被证据支撑。"
        strategy = "如果解除原因、通知程序或协商记录存在争议，最终适用的补偿路径可能发生变化。"

    return (
        f"{focus}\n\n"
        f"{strategy}\n\n"
        "下一步应把证据按“劳动关系、工资基数、解除事实、公司理由”四组整理。仲裁请求里让结构化测算负责金额，正文论证重点放在公司解除依据是否成立、程序是否合规，以及你方证据能否闭合。"
    )


def _build_chat_payload(req: dict) -> dict[str, Any]:
    start_time = time.time()
    query = _repair_mojibake(str(req.get("query", "")).strip())
    session_id = str(req.get("session_id") or "user_web")
    if not query:
        return {
            "reply": "请输入需要分析的问题。",
            "answer": "请输入需要分析的问题。",
            "route": "error",
            "structured": _build_structured_payload("", "error", "请输入需要分析的问题。", {"show": False})
            | {"conversation": conversation_store.build_summary(session_id)},
        }

    mode = req.get("mode")
    preferred_mode = req.get("preferred_mode") or req.get("ui_mode") or mode
    force_mode = bool(req.get("force_mode"))
    previous_state = conversation_store.get(session_id)
    previous_summary = conversation_store.build_summary(session_id, previous_state)
    current_facts = extract_case_facts(query)
    facts = _merge_facts(previous_state.get("facts"), current_facts)
    state_summary = conversation_store.build_summary(session_id, previous_state)
    state_summary["known_facts"] = facts

    calculation, calculation_text, used_previous_calculation = _extract_calculation_payload_with_state(query, facts)
    route, route_reason = _resolve_effective_route(
        query,
        preferred_mode,
        state_summary=state_summary,
        calculation=calculation,
        force_mode=force_mode,
        mode=mode,
    )
    used_previous_calculation = used_previous_calculation or bool(
        state_summary.get("is_continuation")
        and (state_summary.get("last_calculation") or {}).get("show")
        and route in ["doc", "risk", "judge"]
    )

    logger.info(
        "收到请求：%s... ui_mode/preferred_mode=%s, mode=%s, force_mode=%s, effective_route=%s, route_reason=%s",
        query[:30],
        preferred_mode,
        mode,
        force_mode,
        route,
        route_reason,
    )
    agent_query = _build_agent_query(query, route, route_reason, state_summary, facts)
    structured_query = _build_structured_query(query, route, route_reason, state_summary, facts)
    if route == "qa" and (calculation.get("show") or is_calculation_query(query)):
        structured = _build_structured_payload(structured_query, route, calculation_text, calculation)
        answer = _build_calculation_strategy_answer(agent_query, structured)
    else:
        result = _run_agent(route, agent_query, session_id=session_id)
        answer = _repair_mojibake(result)
        structured = _build_structured_payload(structured_query, route, answer, calculation)

    conversation = conversation_store.build_summary(session_id, previous_state)
    conversation.update(
        {
            "is_continuation": bool(previous_summary.get("is_continuation")),
            "turn_count": int(previous_summary.get("turn_count") or 0) + 1,
            "last_route": previous_summary.get("last_route") or "",
            "known_facts": facts,
            "used_previous_calculation": used_previous_calculation,
            "route_reason": route_reason,
        }
    )
    structured["conversation"] = conversation

    saved_state = conversation_store.record_turn(
        session_id,
        query=query,
        route=route,
        answer_preview=strip_for_preview(answer, 240),
        facts=facts,
        calculation=calculation,
        structured_summary={
            "route": route,
            "route_reason": route_reason,
            "used_previous_calculation": used_previous_calculation,
            "calculation_status": calculation.get("status", ""),
        },
    )
    structured["conversation"].update(
        {
            "turn_count": len(saved_state.get("turns") or []),
            "last_route": route,
            "known_facts": saved_state.get("facts") or facts,
        }
    )

    elapsed = time.time() - start_time
    logger.info("路由: %s, 耗时: %.2fs", route, elapsed)
    return {"reply": answer, "answer": answer, "route": route, "structured": structured}


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _chunk_answer(text: str, size: int = 12) -> list[str]:
    clean = str(text or "")
    if not clean:
        return []
    return [clean[index : index + size] for index in range(0, len(clean), size)]


@app.post("/api/chat")
async def chat(req: dict):
    try:
        return _build_chat_payload(req)

    except Exception as e:
        logger.error("处理异常: %s", e, exc_info=True)
        return {"reply": "系统繁忙，请稍后再试。", "route": "error"}


@app.post("/api/chat/stream")
async def chat_stream(req: dict):
    async def event_generator():
        try:
            payload = _build_chat_payload(req)
            route = payload.get("route", "qa")
            structured = payload.get("structured") or {}
            answer = payload.get("answer") or payload.get("reply") or ""

            yield _sse("route", {"route": route})
            yield _sse("thinking", {"status": "thinking", "message": "正在识别问题类型、提取结构化要点。"})
            yield _sse("structured", {"structured": structured})

            token_count = 0
            for chunk in _chunk_answer(answer):
                token_count += 1
                yield _sse("token", {"delta": chunk})
                await asyncio.sleep(0)

            yield _sse(
                "done",
                {
                    "answer": answer,
                    "route": route,
                    "structured": structured,
                    "token_count": token_count,
                },
            )
        except Exception as exc:
            logger.error("流式处理异常: %s", exc, exc_info=True)
            yield _sse("error", {"message": "系统繁忙，请稍后再试。", "route": "error"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


static_dir = FRONTEND_DIR if FRONTEND_DIR.exists() else BASE_DIR
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


def run_server(host: str = "0.0.0.0", port: int = 8000, log_level: str = "info"):
    uvicorn.run("legal_ai_agent.api.server:app", host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    run_server()
