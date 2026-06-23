from typing import Any, Literal, Optional

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel

from legal_ai_agent.llm.qwen_llm import FAST_MODEL, get_llm


class RouteDecision(BaseModel):
    intent: Literal["qa", "doc", "risk", "judge"]
    reason: str


class RouterAgent:
    def __init__(self):
        self.parser = PydanticOutputParser(pydantic_object=RouteDecision)
        self.prompt = PromptTemplate(
            template="""你是劳动法助手的轻量路由器，只能输出 qa、doc、risk、judge 四类。

{format_instructions}

分类规则：
- qa：法规问答、赔偿计算、社保、工伤、工资、加班、解除合同等普通咨询。
- doc：用户明确要求起草、生成、润色法律文书。
- risk：用户要求评估公司制度、管理规定或用工行为的合规风险。
- judge：用户要求胜诉率、仲裁预判、证据强弱、维权路径或案件策略。

用户输入：{query}
""",
            input_variables=["query"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()},
        )
        self._chain = None

    def _get_chain(self):
        if self._chain is None:
            llm = get_llm(
                temperature=0,
                model_name=FAST_MODEL,
                timeout=5,
                max_retries=1,
                max_tokens=80,
            )
            self._chain = self.prompt | llm | self.parser
        return self._chain

    def _keyword_route(self, query: str, state_summary: dict[str, Any] | None = None) -> Optional[str]:
        text = str(query or "")
        summary = state_summary or {}
        has_context = bool(summary.get("is_continuation"))
        has_calculation = bool((summary.get("last_calculation") or {}).get("show"))

        doc_keywords = [
            "生成",
            "起草",
            "文书",
            "申请书",
            "投诉书",
            "起诉状",
            "答辩状",
            "和解协议",
            "仲裁申请",
            "帮我写",
            "模板",
        ]
        if any(keyword in text for keyword in doc_keywords):
            return "doc"

        risk_keywords = [
            "风险评估",
            "合规",
            "规章制度",
            "公司规定",
            "管理制度",
            "是否合法",
            "违法风险",
            "法律风险",
            "用工风险",
        ]
        if any(keyword in text for keyword in risk_keywords):
            return "risk"

        judge_keywords = [
            "胜诉率",
            "胜诉概率",
            "胜算",
            "能否仲裁",
            "能不能仲裁",
            "能否主张",
            "能不能主张",
            "能否要求",
            "能不能要求",
            "如何维权",
            "仲裁预判",
            "案件预判",
            "证据强弱",
            "证据够不够",
            "该先投诉",
            "直接仲裁",
            "维权路径",
            "怎么打官司",
            "仲裁胜算",
        ]
        if any(keyword in text for keyword in judge_keywords):
            return "judge"

        if has_context and any(keyword in text for keyword in ["下一步", "怎么办", "怎么做", "如何处理", "怎么维权", "能赢吗"]):
            return "judge"

        if has_calculation and any(keyword in text for keyword in ["仲裁", "胜诉", "证据", "路径", "策略", "主张", "请求"]):
            return "judge"

        calculation_keywords = [
            "赔偿金",
            "赔偿",
            "补偿金",
            "经济补偿",
            "加班费",
            "双倍工资",
            "未签合同",
            "未签劳动合同",
            "年休假工资",
            "竞业限制补偿",
            "社保补缴",
            "支付多少",
            "应支付多少",
            "补发多少",
            "降薪损失",
            "调岗降薪",
            "工伤待遇",
            "停工留薪",
            "伤残补助",
            "税后",
            "个税",
            "计算",
            "多少钱",
            "多少",
        ]
        if any(keyword in text for keyword in calculation_keywords):
            return "qa"

        return None

    def plan(self, query: str, state_summary: dict[str, Any] | None = None) -> list[str]:
        route = self._keyword_route(query, state_summary=state_summary)
        return [route or "qa"]

    def route_with_llm(self, query) -> str:
        try:
            decision = self._get_chain().invoke({"query": query})
            print(f"\n[Router LLM]: route => {decision.intent} ({decision.reason})")
            return decision.intent
        except Exception as e:
            print(f"\n[Router LLM fallback]: {e}")
            return "qa"

    def route(self, query, state_summary: dict[str, Any] | None = None, forced_mode: str | None = None) -> str:
        if forced_mode in ["qa", "doc", "risk", "judge"]:
            print(f"\n[Router forced]: route => {forced_mode}")
            return forced_mode

        keyword_route = self._keyword_route(query, state_summary=state_summary)
        if keyword_route:
            print(f"\n[Router keyword]: route => {keyword_route}")
            return keyword_route

        print("\n[Router default]: route => qa")
        return "qa"
