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
    return retrieve_docs(LAW_DB, query, k=k)

def search_case_text(query: str, k: int = 3) -> str:
    return retrieve_docs(CASE_DB, query, k=k)

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
    return calculate_compensation(context)
