import asyncio
import io
import time
from datetime import datetime
from typing import List

from pymongo import MongoClient
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_mongodb import MongoDBAtlasVectorSearch

from app.core.config import settings
from app.infrastructure.llm.openai_client import OpenAIClient


class VectorStore:
    """Infra: MongoDB Atlas Vector Search 读写封装（含 PDF/文本摄入与检索）。"""

    def __init__(self):
        if not settings.MONGODB_URI:
            raise ValueError("MONGODB_URI 未在环境变量中设置")

        self.client = MongoClient(settings.MONGODB_URI)
        self.db = self.client[settings.DB_NAME]
        self.collection = self.db[settings.COLLECTION_NAME]

        # OpenAIClient 实现了 LangChain Embeddings 接口，可直接用于向量库
        self.embeddings = OpenAIClient()

        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

    def _get_vector_store(self) -> MongoDBAtlasVectorSearch:
        return MongoDBAtlasVectorSearch(collection=self.collection, embedding=self.embeddings, index_name="default")

    async def ingest_text(self, raw_text: str, source_name: str, user_id: str) -> int:
        ingest_start_time = time.time()
        split_start_time = time.time()

        chunks = self.text_splitter.split_text(raw_text)
        split_elapsed = time.time() - split_start_time
        print(f"⏱️ [性能监控] ingest_text - 文本切分耗时: {split_elapsed:.2f} 秒，生成 {len(chunks)} 个块")

        metadata = {
            "source": source_name,
            "user_id": user_id,
            "created_at": datetime.utcnow(),
        }

        documents = [Document(page_content=chunk, metadata=metadata) for chunk in chunks]

        vector_store = self._get_vector_store()
        embed_start_time = time.time()
        await asyncio.to_thread(vector_store.add_documents, documents)
        embed_elapsed = time.time() - embed_start_time
        print(f"⏱️ [性能监控] ingest_text - 向量化并存储耗时: {embed_elapsed:.2f} 秒")

        total_elapsed = time.time() - ingest_start_time
        print(f"⏱️ [性能监控] ingest_text - 总耗时: {total_elapsed:.2f} 秒")
        return len(documents)

    async def ingest_pdf(self, file_content: bytes, filename: str, user_id: str) -> int:
        pdf_start_time = time.time()
        extract_start_time = time.time()

        pdf_reader = PdfReader(io.BytesIO(file_content))
        raw_text = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                raw_text += page_text + "\n"

        extract_elapsed = time.time() - extract_start_time
        print(f"⏱️ [性能监控] ingest_pdf - PDF 文本提取耗时: {extract_elapsed:.2f} 秒，提取 {len(raw_text)} 字符")

        chunks_count = await self.ingest_text(raw_text, source_name=filename, user_id=user_id)
        total_elapsed = time.time() - pdf_start_time
        print(f"⏱️ [性能监控] ingest_pdf - 总耗时: {total_elapsed:.2f} 秒")
        return chunks_count

    async def search_context_mmr(self, query: str, user_id: str, k: int = 3, fetch_k: int = 10) -> List[dict]:
        search_start_time = time.time()

        vector_store = self._get_vector_store()
        pre_filter = {"user_id": {"$eq": user_id}}
        search_kwargs = {"k": k, "fetch_k": fetch_k, "lambda_mult": 0.5, "pre_filter": pre_filter}

        results = await asyncio.to_thread(vector_store.max_marginal_relevance_search, query, **search_kwargs)
        search_elapsed = time.time() - search_start_time
        print(
            f"⏱️ [性能监控] search_context_mmr - MMR 搜索耗时: {search_elapsed:.2f} 秒，查询: {query[:50]}...，返回 {len(results)} 个结果"
        )

        return [{"content": doc.page_content, "source": doc.metadata.get("source", "unknown"), "score": 0.0} for doc in results]

    async def search_context(self, query: str, user_id: str, k: int = 5) -> List[dict]:
        search_start_time = time.time()

        vector_store = self._get_vector_store()
        pre_filter = {"user_id": {"$eq": user_id}}

        results = await asyncio.to_thread(vector_store.similarity_search_with_score, query, k=k, pre_filter=pre_filter)
        search_elapsed = time.time() - search_start_time
        print(f"⏱️ [性能监控] search_context - 向量搜索耗时: {search_elapsed:.2f} 秒，查询: {query[:50]}...，返回 {len(results)} 个结果")

        return [{"content": doc.page_content, "source": doc.metadata.get("source", "unknown"), "score": float(score)} for doc, score in results]

    def delete_user_data(self, user_id: str) -> int:
        result = self.collection.delete_many({"user_id": {"$eq": user_id}})
        deleted_count = result.deleted_count
        print(f"✅ 已删除用户 {user_id} 的向量数据 {deleted_count} 条")
        return deleted_count

    def clear_vector_data(self) -> int:
        result = self.collection.delete_many({})
        deleted_count = result.deleted_count
        print(f"✅ 已清理 {deleted_count} 条旧向量数据")
        return deleted_count

    def close(self):
        if self.client:
            self.client.close()


_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store


