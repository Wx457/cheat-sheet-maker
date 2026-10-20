from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.domain.utils.cleaner import clean_raw_text
from app.infrastructure.db.supabase_store import SupabaseStore, get_supabase_store
from app.infrastructure.rag.qdrant_store import IngestResult, QdrantVectorStore, get_qdrant_store

logger = logging.getLogger(__name__)


@dataclass
class IngestionService:
    """
    Application Layer: 摄入编排服务（文本 / PDF）。
    负责用例级流程：清洗 -> 调用向量存储写入 -> 记录 ingest 批次。

    说明：当前底层切分/向量化/写入由 `QdrantVectorStore`（infra）承担。
    Qdrant 是 chunk 的权威来源；Supabase `ingest_batches` 只是附带记录，
    未配置或写入失败时只记 warning，不影响 ingest 本身。
    """

    rag_service: QdrantVectorStore
    db: Optional[SupabaseStore] = None

    @classmethod
    def default(cls) -> "IngestionService":
        return cls(rag_service=get_qdrant_store(), db=get_supabase_store())

    async def process_text(
        self, text: str, metadata: Optional[Dict[str, Any]], user_id: str
    ) -> IngestResult:
        """
        清洗文本并写入向量库（优化版：批量嵌入 + 上下文增强）。

        Args:
            text: 原始文本
            metadata: 可选元数据（如 source/course/url 等），将用于上下文增强
            user_id: 用户隔离 ID
        """
        source_name = (
            (metadata or {}).get("source")
            or (metadata or {}).get("course_name")
            or (metadata or {}).get("url")
            or "unknown"
        )
        cleaned = clean_raw_text(text)
        # 传递完整元数据以支持上下文增强
        result = await self.rag_service.ingest_text(
            raw_text=cleaned, source_name=source_name, user_id=user_id, metadata=metadata
        )
        await self._record_batch(user_id, source_name, result)
        return result

    async def process_file(
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
            filename: 文件名
            user_id: 用户隔离 ID
            metadata: 可选完整元数据字典（用于上下文增强）
        """
        if not filename or not filename.lower().endswith(".pdf"):
            raise ValueError("仅支持 PDF 文件格式")
        result = await self.rag_service.ingest_pdf(
            file_content=file_content, filename=filename, user_id=user_id, metadata=metadata
        )
        await self._record_batch(user_id, filename, result)
        return result

    async def delete_user_data(self, user_id: str) -> int:
        """删除用户的 Qdrant chunks，并同步删除其 ingest 批次记录。返回删除的 chunk 数。"""
        deleted_count = await asyncio.to_thread(self.rag_service.delete_user_data, user_id)
        if self.db is not None:
            try:
                db_user_id = await asyncio.to_thread(self.db.get_or_create_user_id, user_id)
                await asyncio.to_thread(self.db.delete_user_ingest_batches, db_user_id)
            except Exception as exc:
                logger.warning("Failed to delete ingest_batches for user_id=%s: %s", user_id, exc)
        return deleted_count

    async def _record_batch(self, user_id: str, source: str, result: IngestResult) -> None:
        if self.db is None:
            return
        try:
            db_user_id = await asyncio.to_thread(self.db.get_or_create_user_id, user_id)
            await asyncio.to_thread(
                self.db.record_ingest_batch,
                db_user_id,
                result["ingest_batch_id"],
                source,
                result["chunks_count"],
                result["truncated"],
            )
        except Exception as exc:
            logger.warning(
                "Failed to record ingest batch %s for user_id=%s: %s",
                result.get("ingest_batch_id"),
                user_id,
                exc,
            )
