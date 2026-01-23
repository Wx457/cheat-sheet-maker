from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.domain.utils.cleaner import clean_raw_text
from app.infrastructure.rag.vector_store import VectorStore, get_vector_store


@dataclass
class IngestionService:
    """
    Application Layer: 摄入编排服务（文本 / PDF）。
    负责用例级流程：清洗 -> 调用向量存储写入。

    说明：当前底层切分/向量化/写入由 `VectorStore`（infra）承担。
    """

    rag_service: VectorStore

    @classmethod
    def default(cls) -> "IngestionService":
        return cls(rag_service=get_vector_store())

    async def process_text(self, text: str, metadata: Optional[Dict[str, Any]], user_id: str) -> int:
        """
        清洗文本并写入向量库（优化版：批量嵌入 + 上下文增强）。

        Args:
            text: 原始文本
            metadata: 可选元数据（如 source/course/url 等），将用于上下文增强
            user_id: 用户隔离 ID
        """
        source_name = (metadata or {}).get("source") or (metadata or {}).get("course_name") or (metadata or {}).get("url") or "unknown"
        cleaned = clean_raw_text(text)
        # 传递完整元数据以支持上下文增强
        return await self.rag_service.ingest_text(raw_text=cleaned, source_name=source_name, user_id=user_id, metadata=metadata)

    async def process_file(
        self, file_content: bytes, filename: str, user_id: str, metadata: Optional[Dict[str, Any]] = None
    ) -> int:
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
        return await self.rag_service.ingest_pdf(file_content=file_content, filename=filename, user_id=user_id, metadata=metadata)

