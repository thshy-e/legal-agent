# rag/vector_store.py

from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from legal_ai_agent.config.settings import CHROMA_DIR
from legal_ai_agent.llm.qwen_llm import get_embedding
import os
import re

PERSIST_DIR = str(CHROMA_DIR)

ARTICLE_PATTERN = re.compile(r"(第[一二三四五六七八九十百千万零〇\d]+条)")


def _chinese_number_to_int(value: str) -> str:
    if not value:
        return ""
    if value.isdigit():
        return value

    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100, "千": 1000, "万": 10000}
    total = 0
    current = 0
    for char in value:
        if char in digits:
            current = digits[char]
        elif char in units:
            unit = units[char]
            if current == 0:
                current = 1
            total += current * unit
            current = 0
    total += current
    return str(total) if total else value


def _article_to_number(article_label: str) -> str:
    match = re.search(r"第([一二三四五六七八九十百千万零〇\d]+)条", article_label or "")
    return _chinese_number_to_int(match.group(1)) if match else ""


def split_law_articles(texts, law_name="劳动法"):
    """按法条编号切分，给每条 Document 标注 law_name/article metadata。"""
    if isinstance(texts, str):
        texts = [texts]

    docs = []
    for text in texts:
        parts = re.split(r"(?=第[一二三四五六七八九十百千万零〇\d]+条)", text)
        for part in parts:
            content = part.strip()
            if not content:
                continue
            article_label = ARTICLE_PATTERN.search(content)
            metadata = {"law_name": law_name}
            if article_label:
                metadata["article"] = _article_to_number(article_label.group(1))
                metadata["article_label"] = article_label.group(1)
            docs.append(Document(page_content=content, metadata=metadata))
    return docs


def _default_split_documents(texts):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "；", ""]
    )
    return splitter.create_documents([texts]) if isinstance(texts, str) else splitter.create_documents(texts)


def _query_terms(query: str):
    text = str(query or "")
    article_terms = re.findall(r"第[一二三四五六七八九十百千万零〇\d]+条", text)
    word_terms = re.findall(r"[\u4e00-\u9fa5]{2,}|[A-Za-z0-9]+", text)
    return list(dict.fromkeys(article_terms + word_terms))


def _keyword_score(doc: Document, query: str) -> float:
    content = doc.page_content
    metadata = doc.metadata or {}
    terms = _query_terms(query)
    score = 0.0
    for term in terms:
        if term and term in content:
            score += 2.0 if term.startswith("第") and term.endswith("条") else 1.0

    article_match = ARTICLE_PATTERN.search(query)
    if article_match:
        article = _article_to_number(article_match.group(1))
        if article and str(metadata.get("article")) == article:
            score += 6.0
        if article_match.group(1) in content:
            score += 4.0
    return score


def _keyword_search(db, query, k):
    try:
        raw = db.get(include=["documents", "metadatas"])
    except Exception:
        return []

    docs = []
    documents = raw.get("documents") or []
    metadatas = raw.get("metadatas") or []
    for idx, content in enumerate(documents):
        metadata = metadatas[idx] if idx < len(metadatas) and metadatas[idx] else {}
        doc = Document(page_content=content, metadata=metadata)
        score = _keyword_score(doc, query)
        if score > 0:
            docs.append((score, doc))
    docs.sort(key=lambda item: item[0], reverse=True)
    return [doc for _, doc in docs[:k]]

def build_vector_store(texts, collection_name="labor_law"):
    """
    构建并持久化向量库，支持动态管理（增删改）
    """
    if "law" in collection_name:
        docs = split_law_articles(texts, law_name=collection_name)
    else:
        docs = _default_split_documents(texts)

    embedding = get_embedding()

    db = Chroma.from_documents(
        docs,
        embedding,
        collection_name=collection_name,
        persist_directory=PERSIST_DIR
    )
    return db

def load_vector_store(collection_name="labor_law"):
    """
    加载已有的向量库（用于增删查改及检索）
    """
    try:
        embedding = get_embedding()
        db = Chroma(
            collection_name=collection_name,
            embedding_function=embedding,
            persist_directory=PERSIST_DIR
        )
        return db
    except Exception:
        return None

def add_documents(db, texts, metadatas=None):
    """动态新增文档"""
    docs = [Document(page_content=t) for t in texts] if isinstance(texts, list) else [Document(page_content=texts)]
    db.add_documents(docs, metadatas=metadatas)

def delete_documents(db, ids):
    """删除指定文档"""
    db.delete(ids=ids)

def retrieve_docs(db, query, k=3):
    """向量 + 关键词混合检索，并对法条编号做本地重排。"""
    if db is None:
        return "暂无相关知识库依据。"

    vector_docs = db.similarity_search(query, k=max(k * 3, k))
    keyword_docs = _keyword_search(db, query, k=max(k * 3, k))

    merged = {}
    for rank, doc in enumerate(vector_docs):
        key = (doc.page_content, tuple(sorted((doc.metadata or {}).items())))
        merged[key] = {"doc": doc, "score": max(k * 3 - rank, 0)}
    for rank, doc in enumerate(keyword_docs):
        key = (doc.page_content, tuple(sorted((doc.metadata or {}).items())))
        keyword_score = _keyword_score(doc, query) + max(k * 3 - rank, 0)
        if key in merged:
            merged[key]["score"] += keyword_score
        else:
            merged[key] = {"doc": doc, "score": keyword_score}

    ranked = sorted(merged.values(), key=lambda item: item["score"], reverse=True)
    docs = [item["doc"] for item in ranked[:k]]

    formatted = []
    for i, doc in enumerate(docs):
        metadata = doc.metadata or {}
        source = metadata.get("law_name", "")
        article = metadata.get("article_label", "")
        label = f"{source}{article}" if source or article else f"参考资料 {i+1}"
        formatted.append(f"【{label}】: {doc.page_content}")
    return "\n\n".join(formatted)
