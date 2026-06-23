from langchain_community.embeddings import DashScopeEmbeddings
from langchain_openai import ChatOpenAI

from legal_ai_agent.config.settings import EMBEDDING_MODEL, QWEN_BASE_URL, get_dashscope_api_key


DEFAULT_MODEL = "qwen-max"
BALANCED_MODEL = "qwen-plus"
FAST_MODEL = "qwen-turbo"


def get_llm(
    temperature=0.1,
    model_name=DEFAULT_MODEL,
    timeout=None,
    max_retries=3,
    max_tokens=None,
    streaming=False,
):
    """Create a DashScope-compatible chat model.

    DashScope compatible mode was more reliable in this project without a
    custom httpx client or short request_timeout, so timeout is intentionally
    accepted for caller compatibility but not passed through by default.
    """
    api_key = get_dashscope_api_key()
    kwargs = {
        "openai_api_base": QWEN_BASE_URL,
        "openai_api_key": api_key,
        "model_name": model_name,
        "temperature": temperature,
        "max_retries": max_retries,
        "streaming": streaming,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ChatOpenAI(**kwargs)


def get_embedding():
    """Create the DashScope embedding model used by Chroma retrieval."""
    return DashScopeEmbeddings(
        dashscope_api_key=get_dashscope_api_key(),
        model=EMBEDDING_MODEL,
    )
