# agents/risk_agent.py
from legal_ai_agent.llm.qwen_llm import get_llm
from langchain_core.messages import HumanMessage

class RiskAgent:
    def check_case(self, case):
        """Reusable condition checks; no invented score or victory probability."""
        f=case['facts'];issues=[]
        if f.get('termination_basis') in ('article_40','article_41') and f.get('protected_status') is True:
            issues.append({'code':'protected_termination','severity':'critical','message':'所填事实涉及第四十二条保护情形，与第四十、四十一条解除路径冲突，需专业复核。'})
        if f.get('termination_basis')=='illegal_claim':
            issues.append({'code':'alleged_illegality','severity':'warning','message':'违法解除仅为劳动者主张；需核对解除理由、程序、证据及是否请求继续履行，不作已成立认定。'})
        if f.get('wages') and not any(status=='claimed_present' for status in f.get('evidence',{}).values()):
            issues.append({'code':'wage_evidence_missing','severity':'warning','message':'尚无用户称持有的材料，请补劳动关系、工资约定、劳动履行与支付记录；计算只是输入核算。'})
        return issues

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
