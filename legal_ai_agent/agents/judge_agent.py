# agents/judge_agent.py
from legal_ai_agent.llm.qwen_llm import get_llm
from langchain_core.messages import HumanMessage
from legal_ai_agent.tools.legal_reasoning import build_case_analysis

class JudgeAgent:
    def analyze_case(self, case, runner=None):
        from legal_ai_agent.casework.roles import model_analysis
        return model_analysis(case, runner)

    def __init__(self):
        self.llm = None

    def _get_llm(self):
        if self.llm is None:
            self.llm = get_llm(temperature=0.1)
        return self.llm

    def run(self, case_info):
        structured_analysis = build_case_analysis(case_info)
        prompt = f"""你是一名劳动争议法律辅助分析员，请对以下案件进行条件分析（不得冒充法官或作出认定）：
{case_info}

以下是系统根据案件树、证据缺口和时间轴提取的结构化分析，请在预判中吸收，但不要机械照抄：
{structured_analysis}

请按以下格式输出：
1. 争议类型与待核验事项：区分用户陈述、法律主张和已核实信息；提及辞退不表示违法解除，提及材料不表示持有或真实。
2. 请求成立条件：说明有利因素、不利因素及尚未核验事项，不给出没有实证依据的胜诉百分比。
3. 可主张请求：列出工资、经济补偿、违法解除赔偿金、双倍工资、加班费、社保/工伤待遇等可能项目。
4. 金额分析：本咨询路径仅说明条件和公式，具体金额转案件协同核对地域、日期、工资口径与参数，不自行填地方数值，不将N、2N、代通知金自动相加。
5. 关键证据建议：列工资流水、劳动合同/工作证、考勤、聊天记录、录音、医院记录、同事证言等。
6. 证据缺口分析：区分【关键缺口】【影响】【补强建议】，说明缺口会怎样影响请求成立。
7. 条件推理链：列出关键争议点、证据支持和不利解释，不提供虚构分数。
8. 时间轴与时效：按入职、调岗/降薪、工伤、辞退、离职、仲裁申请等节点判断是否存在时效或因果问题。
9. 维权路径：说明协商、投诉、劳动仲裁、工伤认定或诉讼的先后步骤。
10. 法律依据：引用劳动合同法、劳动法、工伤保险条例等相关规则；不确定时说明需结合当地标准。
"""
        response = self._get_llm().invoke([HumanMessage(content=prompt)])
        return response.content
