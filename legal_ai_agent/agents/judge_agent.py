# agents/judge_agent.py
from legal_ai_agent.llm.qwen_llm import get_llm
from langchain_core.messages import HumanMessage
from legal_ai_agent.tools.legal_reasoning import build_case_analysis

class JudgeAgent:
    def __init__(self):
        self.llm = None

    def _get_llm(self):
        if self.llm is None:
            self.llm = get_llm(temperature=0.1)
        return self.llm

    def run(self, case_info):
        structured_analysis = build_case_analysis(case_info)
        prompt = f"""你是一名劳动仲裁庭法官，请对以下案件进行预判：
{case_info}

以下是系统根据案件树、证据缺口和时间轴提取的结构化分析，请在预判中吸收，但不要机械照抄：
{structured_analysis}

请按以下格式输出：
1. 案件性质认定：明确属于未签合同、违法解除、加班费、工伤、调岗降薪、竞业限制、搬迁补偿等哪类争议。
2. 胜诉概率评估：给出百分比区间，并说明有利因素和不利因素。
3. 可主张请求：列出工资、经济补偿、违法解除赔偿金、双倍工资、加班费、社保/工伤待遇等可能项目。
4. 可能赔偿范围：能根据题目信息估算的，给出公式；信息不足的，说明还缺哪些数字。
5. 关键证据建议：列工资流水、劳动合同/工作证、考勤、聊天记录、录音、医院记录、同事证言等。
6. 证据缺口分析：区分【关键缺口】【影响】【补强建议】，说明缺口会怎样影响请求成立。
7. 胜诉率推理链：列出加分项、减分项、关键争议点，不要只给百分比。
8. 时间轴与时效：按入职、调岗/降薪、工伤、辞退、离职、仲裁申请等节点判断是否存在时效或因果问题。
9. 维权路径：说明协商、投诉、劳动仲裁、工伤认定或诉讼的先后步骤。
10. 法律依据：引用劳动合同法、劳动法、工伤保险条例等相关规则；不确定时说明需结合当地标准。
"""
        response = self._get_llm().invoke([HumanMessage(content=prompt)])
        return response.content
