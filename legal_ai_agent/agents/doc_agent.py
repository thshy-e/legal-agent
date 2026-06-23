# agents/doc_agent.py
from legal_ai_agent.llm.qwen_llm import get_llm
from langchain_core.messages import HumanMessage
from legal_ai_agent.tools.calculator import calculate_from_query

class DocAgent:
    def __init__(self):
        self.llm = None

    def _get_llm(self):
        if self.llm is None:
            self.llm = get_llm()
        return self.llm

    def run(self, info):
        calculation_result = calculate_from_query(info)
        calculation_context = (
            f"\n【赔偿计算引擎结果】\n{calculation_result}\n"
            if calculation_result
            else "\n【赔偿计算引擎结果】\n用户信息不足时，请在文书中将金额写为“待计算/待补充”，并列明需要补充的工资、年限、期间等信息。\n"
        )
        prompt = f"""
你是一名劳动争议法律文书助手。请根据用户需求生成对应文书，不能只给建议。

文书要求：
1. 根据用户表达自动选择文书类型，如劳动仲裁申请书、劳动监察投诉书、和解协议、民事起诉状等。
2. 必须包含清晰标题。
3. 仲裁/起诉类文书应包含：当事人信息、请求事项、事实与理由、法律依据、证据清单、落款。
4. 投诉类文书应包含：投诉人、被投诉单位、投诉事项、事实经过、处理请求、证据材料、落款。
5. 协议类文书应包含：双方信息、付款金额与期限、权利义务、违约责任、争议解决、签署栏。
6. 信息缺失时使用“待补充”占位，不要编造身份证号、公司地址、日期等具体信息。
7. 金额能够从用户信息中计算的，写出简要计算过程。
8. 需要案号时使用占位格式，例如：案号：（2026）【地区代码】劳仲字第【待补充】号。
9. 证据目录必须联动事实与请求，包含“证据名称”和“证明目的”。

{calculation_context}

用户需求：

{info}
"""
        response = self._get_llm().invoke([HumanMessage(content=prompt)])
        return response.content
