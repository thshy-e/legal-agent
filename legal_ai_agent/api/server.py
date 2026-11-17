import asyncio
import json
import logging
import re
import time
from queue import Queue
from threading import Thread
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
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
    from legal_ai_agent.casework.knowledge import KnowledgeRegistry
    registry=KnowledgeRegistry()
    logger.info('法源版本 %s，文档 %s；旧Chroma库保留供回退，不混入现行检索',registry.data['version'],len(registry.documents))


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


def _case_payload(req, emit=None):
    from legal_ai_agent.casework.workflow import CaseWorkflow, CaseInputError
    if not req.get('session_id') or not str(req['session_id']).strip():
        raise CaseInputError('案件协同必须提供独立session_id。')
    expected=req.get('expected_case_version')
    if expected is not None and (not isinstance(expected,int) or isinstance(expected,bool)):
        raise CaseInputError('expected_case_version必须为整数。')
    with conversation_store.case_transaction(str(req['session_id']),expected) as case:
        workflow=CaseWorkflow(qa=qa,judge=judge,doc=doc)
        payload = workflow.run(req,case,emit)
    payload['structured']['presentation'] = {'kind':'case'}
    conversation_store.record_turn(str(req['session_id']),query=str(req.get('query','')),
        route='case',answer_preview=strip_for_preview(payload['answer'],240),answer=payload['answer'],
        metadata={'kind':'case','case_version':payload['structured']['case_version']})
    return payload


def _uses_case_workflow(req):
    from legal_ai_agent.conversation import wants_case, ambiguous_wage_revision
    sid = str(req.get('session_id') or '').strip()
    prior = (conversation_store.get(sid).get('case') or {}) if sid else {}
    if 'facts' not in req and not req.get('action') and ambiguous_wage_revision(str(req.get('query','')),prior):
        return False
    return wants_case(req, prior)


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

    current_context = build_calculation_context_from_query(query)
    if current_context:
        context.update(_truthy_facts(current_context))
    if context.get('calc_type') in (None,'severance','notice','notice_pay'):
        context.update(reason='历史解除信息和当前法律条件均待核验',conditional_only=True)

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
    return {"level":"unknown","label":"待核验","caption":"按具体请求的成立条件与证据核查，不提供未经验证的固定风险分数。"}


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
        denied = any(re.search(r'(?:没有|没|缺少|未持有|无)\s*'+re.escape(keyword), text) for keyword in keywords)
        mentioned = not denied and any(re.search(r'(?:有|持有|保存了|提供了)\s*'+re.escape(keyword), text) for keyword in keywords)
        evidence.append(
            {
                "label": label,
                "status": "用户称持有" if mentioned else "用户称缺失" if denied else "持有情况未知",
                "note": "未核验真实性" if mentioned else "需向用户确认或补齐",
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
        primary_metric = {"label": "请求条件", "value": "待核验", "unit": "", "kind": "status", "caption": "逐请求核查法律条件和证据。"}
    else:
        primary_metric = {"label": "分析状态", "value": "已生成", "unit": "", "kind": "status", "caption": "AI 正文负责解释和策略。"}

    return {
        "route": route,
        "calculation": calculation,
        "metrics": [
            primary_metric,
            {"label": "风险等级", "value": risk["label"], "unit": "", "kind": "risk", "caption": risk["caption"]},
            {"label": "材料状态", "value": "待核验", "unit": "", "kind": "evidence", "caption": "用户称持有不表示真实性已经核验。"},
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
    from legal_ai_agent.casework.workflow import CaseInputError
    from legal_ai_agent.conversation import VERSION
    if req.get('workflow','consultation') not in ('consultation','case'):
        raise CaseInputError('未知workflow。')
    if _uses_case_workflow(req):
        return _case_payload(req)
    query = _repair_mojibake(str(req.get('query','')).strip())
    sid = str(req.get('session_id') or '').strip()
    state = conversation_store.get(sid) if sid else {}
    history = conversation_store.recent_dialogue(sid) if sid else []
    case = state.get('case') or {}
    # Only tool-owned, current state is available to read-only explanations.
    snapshot = {k:case[k] for k in ('case_version','status','facts','fact_sources','claims',
                'calculations','missing_info','review_issues','confirmation','document_status') if k in case} or None
    from legal_ai_agent.conversation import ambiguous_wage_revision
    if ambiguous_wage_revision(query,case):
        result = {'answer':'你要修改的是哪一期间的应付工资、实付工资，还是解除补偿的平均工资基数？请明确一下，我再重新核对；目前还没有改动案件。',
                  'sources':[],'status':'clarification','used_history':False,'read_case':True,'retrieval_query':''}
    elif query:
        result = qa.respond(query,history=history,case=snapshot)
    else:
        result = {'answer':'你想了解哪方面的劳动法律问题？','sources':[],
                  'status':'clarification','used_history':False,'read_case':False,'retrieval_query':''}
    answer = result['answer']
    sources = [{k:d.get(k) for k in ('id','title','article','version','url','original_text',
                'jurisdictions','effective_from','effective_to','verified_on','limits')} for d in result['sources']]
    structured = {'workflow':'consultation','presentation':{'kind':'conversation'},
                  'status':result['status'],'sources':sources,'conversation_version':VERSION,
                  'conversation':{'session_id':sid or None,'is_continuation':bool(result['used_history']),
                      'read_case':result['read_case'],'case_version':case.get('case_version') if result['read_case'] else None,
                      'used_previous_calculation':False,'turn_count':len(state.get('turns',[])) + bool(query)}}
    if sid and query:
        saved = conversation_store.record_turn(sid,query=query,route='qa',answer_preview=strip_for_preview(answer,240),
            answer=answer,metadata={'kind':'conversation','status':result['status'],
                'retrieval_query':result['retrieval_query'],'source_ids':[d['id'] for d in sources]})
        structured['conversation']['turn_count'] = len(saved['turns'])
    return {'reply':answer,'answer':answer,'route':'qa','structured':structured}


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
        from legal_ai_agent.memory.memory_manager import StateStorageError
        from legal_ai_agent.casework.workflow import CaseConflict, CaseInputError
        if isinstance(e,StateStorageError): raise HTTPException(503,detail=str(e))
        if isinstance(e,CaseConflict): raise HTTPException(409,detail={'message':str(e),'case_version':e.current_version})
        if isinstance(e,(CaseInputError,ValidationError)): raise HTTPException(422,detail=str(e))
        logger.error("处理异常: %s", e, exc_info=True)
        return {"reply": "系统繁忙，请稍后再试。", "route": "error"}


@app.post("/api/chat/stream")
async def chat_stream(req: dict):
    from legal_ai_agent.casework.workflow import CaseConflict, CaseInputError
    if req.get('workflow','consultation') not in ('consultation','case'): raise HTTPException(422,detail='未知workflow')
    from legal_ai_agent.memory.memory_manager import StateStorageError
    try: uses_case=_uses_case_workflow(req)
    except StateStorageError as exc: raise HTTPException(503,detail=str(exc))
    # Reject stale confirmations before returning the event-stream's 200 status.
    if uses_case:
        if not req.get('session_id'): raise HTTPException(422,detail='案件协同必须提供session_id')
        from legal_ai_agent.memory.memory_manager import StateStorageError
        try: current=(conversation_store.get(req['session_id']).get('case') or {}).get('case_version',0)
        except StateStorageError as exc: raise HTTPException(503,detail=str(exc))
        if req.get('action') in ('confirm','generate_document') and not isinstance(req.get('expected_case_version'),int): raise HTTPException(422,detail='确认必须提供expected_case_version')
        if req.get('expected_case_version') is not None and req['expected_case_version']!=current:
            raise HTTPException(409,detail={'message':'案件版本已变化，请重新确认。','case_version':current})
    async def event_generator():
        try:
            if uses_case:
                queue=Queue()
                def worker():
                    try:
                        result=_case_payload(req,lambda event,data:queue.put((event,data)))
                        queue.put(('result',result))
                    except Exception as exc:
                        queue.put(('error',{'message':str(exc),'code':409 if isinstance(exc,CaseConflict) else 422 if isinstance(exc,(CaseInputError,ValidationError)) else 500}))
                    finally: queue.put(('end',None))
                Thread(target=worker,daemon=True).start()
                payload=None
                while True:
                    event,data=await asyncio.to_thread(queue.get)
                    if event=='end': break
                    if event=='result': payload=data
                    else: yield _sse(event,data)
                if payload is None: return
            else:
                yield _sse("thinking", {"status":"thinking","message":"正在查看本轮问题。"})
                payload = await asyncio.to_thread(_build_chat_payload,req)
            route = payload.get("route", "qa")
            structured = payload.get("structured") or {}
            answer = payload.get("answer") or payload.get("reply") or ""

            yield _sse("route", {"route": route})
            yield _sse("structured", {"structured": structured})

            token_count = 0
            for chunk in _chunk_answer(answer, size=max(len(answer),1) if uses_case else 12):
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
