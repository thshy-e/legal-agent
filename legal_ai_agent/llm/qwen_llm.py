from langchain_community.embeddings import DashScopeEmbeddings
from langchain_openai import ChatOpenAI

from legal_ai_agent.config.settings import EMBEDDING_MODEL, QWEN_BASE_URL, DASHSCOPE_EMBEDDING_BASE_URL, embedding_base_url, get_dashscope_api_key


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
    base_url=None,
):
    """Create a DashScope-compatible model, honoring bounded caller timeouts."""
    api_key = get_dashscope_api_key()
    kwargs = {
        "openai_api_base": base_url or QWEN_BASE_URL,
        "openai_api_key": api_key,
        "model_name": model_name,
        "temperature": temperature,
        "max_retries": max_retries,
        "streaming": streaming,
    }
    if timeout is not None:
        kwargs['timeout'] = timeout
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ChatOpenAI(**kwargs)


class _WorkspaceEmbeddingClient:
    def __init__(self, api_key, base_url, timeout):
        self.api_key=api_key;self.base_url=base_url;self.timeout=timeout

    def call(self, **kwargs):
        from dashscope import TextEmbedding
        return TextEmbedding.call(**{**kwargs,'api_key':self.api_key,
            'base_address':self.base_url,'request_timeout':self.timeout})


def get_embedding(base_url=None, timeout=40):
    """Use the matching native workspace endpoint with a per-call timeout."""
    api_key=get_dashscope_api_key()
    embedding=DashScopeEmbeddings(
        dashscope_api_key=api_key,
        model=EMBEDDING_MODEL,
        max_retries=1,
    )
    # The upstream validator unconditionally replaces constructor clients.
    native_url=base_url or DASHSCOPE_EMBEDDING_BASE_URL or embedding_base_url(QWEN_BASE_URL)
    embedding.client=_WorkspaceEmbeddingClient(api_key,native_url,timeout)
    return embedding
