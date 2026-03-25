import asyncio
import io
import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TypeVar, TypedDict
from uuid import uuid4

from pymongo import MongoClient
from pymongo import errors as pymongo_errors
from pypdf import PdfReader
from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.infrastructure.llm.openai_client import OpenAIClient

logger = logging.getLogger(__name__)
T = TypeVar("T")


class IngestResult(TypedDict):
    chunks_count: int
    ingest_batch_id: str
    ingest_at: datetime


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

        # 优化分块策略：较小块大小适合学术密度内容
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        self.mongo_retry_attempts = 4
        self.mongo_retry_base_delay_seconds = 0.5
        not_primary_error = getattr(pymongo_errors, "NotPrimaryError", pymongo_errors.AutoReconnect)
        not_primary_no_secondary_ok = getattr(
            pymongo_errors, "NotPrimaryNoSecondaryOk", pymongo_errors.AutoReconnect
        )
        self.retryable_errors = (
            pymongo_errors.AutoReconnect,
            pymongo_errors.ServerSelectionTimeoutError,
            pymongo_errors.ConnectionFailure,
            pymongo_errors.NetworkTimeout,
            not_primary_error,
            not_primary_no_secondary_ok,
        )

    def _run_with_retry(self, operation_name: str, operation: Callable[[], T]) -> T:
        """
        对 Mongo 读写进行短暂重试，缓解副本集主从切换导致的瞬时失败。
        """
        for attempt in range(1, self.mongo_retry_attempts + 1):
            try:
                return operation()
            except self.retryable_errors as exc:
                is_last_attempt = attempt == self.mongo_retry_attempts
                if is_last_attempt:
                    logger.exception("Mongo operation failed after retries: %s", operation_name)
                    raise
                sleep_seconds = self.mongo_retry_base_delay_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "Mongo transient error on %s (attempt %d/%d): %s; retry in %.1fs",
                    operation_name,
                    attempt,
                    self.mongo_retry_attempts,
                    exc,
                    sleep_seconds,
                )
                time.sleep(sleep_seconds)

    def _get_vector_store(self) -> MongoDBAtlasVectorSearch:
        # 指定 text_key 为 page_content，因为我们存储的文档使用 page_content 字段而不是默认的 text 字段
        return MongoDBAtlasVectorSearch(
            collection=self.collection,
            embedding=self.embeddings,
            index_name="default",
            text_key="page_content",  # 指定文本字段名为 page_content
        )

    def _format_metadata_string(self, metadata: Dict[str, Any]) -> str:
        """将元数据字典格式化为字符串用于上下文增强。"""
        parts = []
        if metadata.get("source"):
            parts.append(f"Source: {metadata['source']}")
        if metadata.get("course_name"):
            parts.append(f"Course: {metadata['course_name']}")
        if metadata.get("url"):
            parts.append(f"URL: {metadata['url']}")
        return ", ".join(parts) if parts else "Unknown"

    def _enrich_chunk_with_context(self, chunk_text: str, metadata: Dict[str, Any]) -> str:
        """为块文本添加上下文元数据，用于嵌入生成。"""
        metadata_str = self._format_metadata_string(metadata)
        return f"Context: {metadata_str}\nContent: {chunk_text}"

    async def ingest_text(
        self,
        raw_text: str,
        source_name: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IngestResult:
        """
        摄入文本到向量库（优化版：批量嵌入 + 上下文增强）。

        Args:
            raw_text: 原始文本
            source_name: 来源名称（用于兼容旧接口）
            user_id: 用户隔离 ID
            metadata: 可选完整元数据字典（用于上下文增强）
        """
        # 1. 文本切分
        chunks = self.text_splitter.split_text(raw_text)

        # 2. 构建元数据
        ingest_batch_id = uuid4().hex
        ingest_at = datetime.utcnow()
        full_metadata = {
            "source": source_name,
            "user_id": user_id,
            "created_at": ingest_at,
        }
        if metadata:
            full_metadata.update(metadata)
        # 每次摄入强制写入新的批次标识，避免被外部 metadata 覆盖
        full_metadata["ingest_batch_id"] = ingest_batch_id

        # 3. 上下文增强：为嵌入准备增强文本，但保留原始文本用于显示
        texts_to_embed = [self._enrich_chunk_with_context(chunk, full_metadata) for chunk in chunks]

        # 4. 批量嵌入（性能优化：N 次网络请求 -> 1 次）
        embeddings_list = await asyncio.to_thread(self.embeddings.get_embeddings, texts_to_embed)

        # 5. 构建 MongoDB 文档（存储原始文本，但使用增强文本的嵌入）
        # 注意：使用标准 LangChain/LlamaIndex 结构，元数据嵌套在 metadata 字段下
        documents_to_insert = []
        for i, (original_chunk, embedding) in enumerate(zip(chunks, embeddings_list)):
            doc = {
                "page_content": original_chunk,  # 存储原始文本用于显示（LangChain 期望此字段名）
                "embedding": embedding,  # 向量字段（MongoDB Atlas Vector Search 索引期望此字段名）
                "metadata": full_metadata,  # 元数据嵌套在 metadata 字段下（标准 LangChain/LlamaIndex 结构）
            }
            documents_to_insert.append(doc)

        # 6. 批量插入 MongoDB
        if documents_to_insert:
            await asyncio.to_thread(
                self._run_with_retry,
                "insert_many",
                lambda: self.collection.insert_many(documents_to_insert),
            )

        return {
            "chunks_count": len(documents_to_insert),
            "ingest_batch_id": ingest_batch_id,
            "ingest_at": ingest_at,
        }

    async def ingest_pdf(
        self,
        file_content: bytes,
        filename: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IngestResult:
        """
        摄入 PDF 文件到向量库（优化版：支持上下文增强元数据）。

        Args:
            file_content: PDF 文件二进制内容
            filename: 文件名（用作 source_name）
            user_id: 用户隔离 ID
            metadata: 可选完整元数据字典（用于上下文增强）
        """
        pdf_reader = PdfReader(io.BytesIO(file_content))
        raw_text = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                raw_text += page_text + "\n"

        # 构建 PDF 特定元数据
        pdf_metadata = {"source": filename}
        if metadata:
            pdf_metadata.update(metadata)

        ingest_result = await self.ingest_text(
            raw_text, source_name=filename, user_id=user_id, metadata=pdf_metadata
        )
        return ingest_result

    async def search_context_mmr(
        self, query: str, user_id: str, k: int = 3, fetch_k: int = 10
    ) -> List[dict]:
        vector_store = self._get_vector_store()
        # 使用 metadata.user_id 路径匹配新的数据结构
        pre_filter = {"metadata.user_id": {"$eq": user_id}}
        search_kwargs = {"k": k, "fetch_k": fetch_k, "lambda_mult": 0.5, "pre_filter": pre_filter}

        results = await asyncio.to_thread(
            self._run_with_retry,
            "max_marginal_relevance_search",
            lambda: vector_store.max_marginal_relevance_search(query, **search_kwargs),
        )

        return [
            {
                "content": doc.page_content,
                "source": doc.metadata.get("source", "unknown"),
                "score": 0.0,
            }
            for doc in results
        ]

    async def search_context(self, query: str, user_id: str, k: int = 5) -> List[dict]:
        vector_store = self._get_vector_store()
        # 使用 metadata.user_id 路径匹配新的数据结构
        pre_filter = {"metadata.user_id": {"$eq": user_id}}

        results = await asyncio.to_thread(
            self._run_with_retry,
            "similarity_search_with_score",
            lambda: vector_store.similarity_search_with_score(query, k=k, pre_filter=pre_filter),
        )

        return [
            {
                "content": doc.page_content,
                "source": doc.metadata.get("source", "unknown"),
                "score": float(score),
            }
            for doc, score in results
        ]

    async def is_batch_searchable(self, query: str, user_id: str, ingest_batch_id: str) -> bool:
        """
        检查指定批次是否已可被向量检索命中（用于索引最终一致性等待）。
        """
        vector_store = self._get_vector_store()
        pre_filter = {
            "metadata.user_id": {"$eq": user_id},
            "metadata.ingest_batch_id": {"$eq": ingest_batch_id},
        }
        results = await asyncio.to_thread(
            self._run_with_retry,
            "batch_searchable_check",
            lambda: vector_store.similarity_search_with_score(query, k=1, pre_filter=pre_filter),
        )
        return len(results) > 0

    def get_user_chunk_count(self, user_id: str) -> int:
        """获取指定用户的 chunks 数量。"""
        # 使用 metadata.user_id 路径匹配新的数据结构
        count = self._run_with_retry(
            "count_documents",
            lambda: self.collection.count_documents({"metadata.user_id": {"$eq": user_id}}),
        )
        return count

    def delete_user_data(self, user_id: str) -> int:
        # 使用 metadata.user_id 路径匹配新的数据结构
        result = self._run_with_retry(
            "delete_user_data",
            lambda: self.collection.delete_many({"metadata.user_id": {"$eq": user_id}}),
        )
        deleted_count = result.deleted_count
        print(f"✅ Deleted User {user_id} {deleted_count} chunks")
        return deleted_count

    def clear_vector_data(self) -> int:
        result = self._run_with_retry("clear_vector_data", lambda: self.collection.delete_many({}))
        deleted_count = result.deleted_count
        print(f"✅ Cleared {deleted_count} old chunks")
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
