from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from legal_ai_agent.llm.qwen_llm import BALANCED_MODEL, DEFAULT_MODEL, FAST_MODEL, get_llm
from legal_ai_agent.memory.case_profile import CaseProfileStore
from legal_ai_agent.tools.calculator import calculation_missing_info_message, calculate_from_query, is_calculation_query
from legal_ai_agent.tools.labor_tools import (
    calculate_severance_pay,
    search_case,
    search_case_text,
    search_law,
    search_law_text,
)


CASE_HINT_KEYWORDS = [
    "案例",
    "判决",
    "裁判",
    "胜诉",
    "证据",
    "仲裁结果",
    "类似",
]


class QAAgent:
    def __init__(self):
        self.fast_llm = None
        self.balanced_llm = None
        self.tools = [search_law, search_case, calculate_severance_pay]
        self.memory = MemorySaver()
        self.case_profiles = CaseProfileStore()
        self.agent_executor = None

        self.system_prompt = """你是“劳法智枢”的中国劳动法问答智能体。
回答要求：
1. 先给简明结论，再给法律依据、计算/证据要点和行动建议。
2. 劳动法规定、辞退、社保、工伤、加班、年休假、竞业限制等问题，优先调用 search_law 检索法条依据。
3. 用户询问案例、胜诉可能、证据强弱或类似裁判结果时，调用 search_case 补充案例参考。
4. 用户问题包含工资、工作年限、加班天数、未签合同月数、社保比例、竞业限制比例等数字，并询问“多少、计算、补发、赔偿金、补偿金、加班费、双倍工资、补缴”时，必须调用 calculate_severance_pay。
5. 计算类回答必须列出适用项目、计算公式、最终金额和法律依据；缺少关键数字时，先说明需要补充的信息。
6. 不编造不存在的法条；检索结果不足时，明确说明需要结合当地标准或证据进一步确认。
7. 语气专业、通俗，面向劳动者给出可执行步骤。"""

    def _needs_case_context(self, query: str) -> bool:
        text = str(query or "")
        return any(keyword in text for keyword in CASE_HINT_KEYWORDS)

    def _get_agent_executor(self):
        if self.agent_executor is None:
            from langgraph.prebuilt import create_react_agent

            llm = get_llm(
                model_name=DEFAULT_MODEL,
                temperature=0.1,
                timeout=30,
                max_retries=3,
                max_tokens=1200,
            )
            self.agent_executor = create_react_agent(
                model=llm,
                tools=self.tools,
                prompt=self.system_prompt,
            checkpointer=self.memory,
        )
        return self.agent_executor

    def _get_fast_llm(self):
        if self.fast_llm is None:
            self.fast_llm = get_llm(
                model_name=FAST_MODEL,
                temperature=0.1,
                timeout=10,
                max_retries=3,
                max_tokens=500,
            )
        return self.fast_llm

    def _get_balanced_llm(self):
        if self.balanced_llm is None:
            self.balanced_llm = get_llm(
                model_name=BALANCED_MODEL,
                temperature=0.1,
                timeout=16,
                max_retries=3,
                max_tokens=800,
            )
        return self.balanced_llm

    def _build_direct_prompt(self, query: str, law_context: str, case_context: str = "") -> str:
        case_block = f"\n\n【案例参考】\n{case_context}" if case_context else ""
        return f"""你是中国劳动法问答助手。请严格基于参考资料回答用户问题，不要编造不存在的法条或案例。

回答格式：
1. 先给一句话结论。
2. 列出法律依据；资料不足时，要说明“需要结合当地标准或证据进一步确认”。
3. 给出 2-4 条可执行行动建议。
4. 控制在 500 字以内，语言通俗、专业。

【用户问题】
{query}

【法条参考】
{law_context}{case_block}
"""

    def _run_direct_qa(self, query: str) -> str:
        law_context = search_law_text(query, k=3)
        case_context = ""
        if self._needs_case_context(query):
            case_context = search_case_text(query, k=2)

        prompt = self._build_direct_prompt(query, law_context, case_context)
        llm = self._get_balanced_llm() if case_context else self._get_fast_llm()
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content

    def _run_agent_fallback(self, query: str, session_id: str) -> str:
        config = {"configurable": {"thread_id": session_id}}
        inputs = {"messages": [("user", query)]}
        response = self._get_agent_executor().invoke(inputs, config=config)
        return response["messages"][-1].content

    def run(self, query, session_id="default_user"):
        self.case_profiles.update(session_id, query)

        direct_calculation = calculate_from_query(query)
        if direct_calculation:
            return direct_calculation

        contextual_calculation = self.case_profiles.maybe_contextual_calculation(session_id, query)
        if contextual_calculation:
            return contextual_calculation

        if is_calculation_query(query):
            return calculation_missing_info_message(query)

        try:
            return self._run_direct_qa(query)
        except Exception as exc:
            print(f"\n[QA direct fallback]: {exc}")
            return self._run_agent_fallback(query, session_id)
