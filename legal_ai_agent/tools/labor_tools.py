# tools/labor_tools.py

from langchain_core.tools import tool
from legal_ai_agent.rag.vector_store import retrieve_docs
from legal_ai_agent.tools.calculator import calculate_compensation

# 全局向量库实例，在应用启动时初始化
LAW_DB = None
CASE_DB = None

def init_tools_db(law_db, case_db):
    global LAW_DB, CASE_DB
    LAW_DB = law_db
    CASE_DB = case_db

def search_law_text(query: str, k: int = 3) -> str:
    from legal_ai_agent.casework.knowledge import KnowledgeRegistry, CITIES
    import re
    city=next((city for city in CITIES if city in query),None)
    when=re.search(r'20\d{2}-\d{2}-\d{2}',query)
    return KnowledgeRegistry().render(query,city,when[0] if when else None,k=k)

def search_case_text(query: str, k: int = 3) -> str:
    from legal_ai_agent.casework.knowledge import KnowledgeRegistry, CITIES
    city=next((city for city in CITIES if city in query),None)
    if city is None: return '请先说明案件地区，再检索地区相关官方案例。'
    return KnowledgeRegistry().render(query,city,kind='case',k=k)

@tool
def search_law(query: str) -> str:
    """当用户询问劳动法规定、辞退赔偿标准、加班费规定时，必须调用此工具检索法律依据。"""
    return search_law_text(query)

@tool
def search_case(query: str) -> str:
    """当用户询问以往的劳动仲裁案例、法院判决结果时，调用此工具检索相似案例。"""
    return search_case_text(query)

@tool
def calculate_severance_pay(context: dict) -> str:
    """
    劳动争议计算引擎。
    支持经济补偿/违法解除赔偿、N+1代通知金、未签合同双倍工资、
    加班费、未休年休假、竞业限制补偿、社保补缴估算、违法调岗降薪损失、
    工伤停工留薪/伤残补助、经济补偿个税估算等场景。
    """
    standalone_types={'double_wage','no_contract','overtime_rest_day','rest_overtime','overtime_holiday','holiday_overtime','annual_leave','unused_annual_leave','non_compete','noncompetition','social_security','social_insurance','salary_reduction','pay_cut','position_salary_cut','work_injury','injury','work_injury_benefits','compensation_tax','tax','after_tax'}
    if context.get('calc_type') not in standalone_types:
        return '解除补偿及代通知金须通过案件协同的事实、地域、法律条件与参数核查；不能仅凭模型填写的reason字段直接确定N、2N或N+1。'
    return calculate_compensation(context)
