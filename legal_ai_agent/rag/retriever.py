# rag/retriever.py

from legal_ai_agent.rag.vector_store import retrieve_docs as hybrid_retrieve_docs


def retrieve_docs(vector_db, query, k=3):
    return hybrid_retrieve_docs(vector_db, query, k=k)
