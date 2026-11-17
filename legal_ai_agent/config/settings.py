import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
from dotenv import load_dotenv
load_dotenv(BASE_DIR / '.env', override=False)
PACKAGE_DIR = BASE_DIR / "legal_ai_agent"
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
LAW_DATA_DIR = DATA_DIR / "law"
CASE_DATA_DIR = DATA_DIR / "case"
FRONTEND_DIR = BASE_DIR / "frontend"
CHROMA_DIR = BASE_DIR / "chroma_db"

QWEN_API_KEY = os.getenv("DASHSCOPE_API_KEY", "").strip()
QWEN_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").strip().rstrip('/')
def embedding_base_url(chat_base, explicit=None):
    """Keep workspace/region credentials on their corresponding native API."""
    if explicit and explicit.strip(): return explicit.strip().rstrip('/')
    suffix='/compatible-mode/v1'
    if not chat_base.endswith(suffix):
        raise ValueError('Configure DASHSCOPE_EMBEDDING_BASE_URL for a custom chat endpoint')
    return chat_base[:-len(suffix)]+'/api/v1'

DASHSCOPE_EMBEDDING_BASE_URL = os.getenv('DASHSCOPE_EMBEDDING_BASE_URL','').strip() or (embedding_base_url(QWEN_BASE_URL) if QWEN_BASE_URL.endswith('/compatible-mode/v1') else '')
EMBEDDING_MODEL = "text-embedding-v3"


def get_dashscope_api_key() -> str:
    """Return the DashScope API key or raise a clear configuration error."""
    if not QWEN_API_KEY:
        raise RuntimeError(
            "DASHSCOPE_API_KEY is not configured. Copy .env.example to .env "
            "or set the environment variable before calling LLM/RAG services."
        )
    return QWEN_API_KEY
