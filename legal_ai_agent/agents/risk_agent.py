# agents/risk_agent.py
from legal_ai_agent.llm.qwen_llm import get_llm
from langchain_core.messages import HumanMessage

class RiskAgent:
    def __init__(self):
        self.llm = None

    def _get_llm(self):
        if self.llm is None:
            self.llm = get_llm(temperature=0.1)
        return self.llm

    def run(self, policy_desc):
        prompt = f"""你是一位资深劳动法律师，请对以下公司规定或做法进行风险评估：
{policy_desc}

请按以下格式回答：
1. 风险等级：高风险/中风险/低风险/合规，并给出一句话结论。
2. 风险点拆解：逐条说明哪些做法可能违法或存在证据风险。
3. 涉及法条及解释：引用劳动合同法、劳动法、社会保险法、工伤保险条例等相关规则。
4. 可能法律后果：列明补发工资、经济补偿、赔偿金、行政处罚、败诉风险等。
5. 整改建议：给公司可落地的合规做法。
6. 劳动者应对建议：列投诉、仲裁、证据保全等步骤。
"""
        # ✅ 使用 invoke 方法，传入 HumanMessage 列表
        response = self._get_llm().invoke([HumanMessage(content=prompt)])
        return response.content
