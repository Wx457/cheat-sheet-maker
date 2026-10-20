"""Qdrant-backed vector store — drop-in replacement for MongoDB VectorStore (Phase 1)."""
from __future__ import annotations

import asyncio
import io
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict
from uuid import uuid4

import numpy as np
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    VectorParams,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.infrastructure.llm.openai_client import OpenAIClient

logger = logging.getLogger(__name__)


class QuotaExceededError(Exception):
    """Raised when a user's knowledge base has reached its chunk limit."""


class IngestResult(TypedDict):
    chunks_count: int
    ingest_batch_id: str
    ingest_at: datetime
    truncated: bool
    original_chunks_count: int

_COLLECTION = "cheat_sheet_chunks"
_VECTOR_SIZE = 1536  # text-embedding-3-small output dimension


class QdrantVectorStore:
    """Infra: Qdrant vector store — replaces MongoVectorStore in Phase 1."""

    def __init__(self) -> None:
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
        )
        self.embeddings = OpenAIClient()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500, chunk_overlap=50
        )
        self._ensure_collection()

    # ── internal helpers ──────────────────────────────────────────────────────

    def _ensure_collection(self) -> None:
        existing = {c.name for c in self.client.get_collections().collections}
        if _COLLECTION not in existing:
            self.client.create_collection(
                collection_name=_COLLECTION,
                vectors_config=VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE),
            )

    @staticmethod
    def _user_filter(user_id: str) -> Filter:
        return Filter(
            must=[FieldCondition(key="metadata.user_id", match=MatchValue(value=user_id))]
        )

    @staticmethod
    def _batch_filter(user_id: str, ingest_batch_id: str) -> Filter:
        return Filter(
            must=[
                FieldCondition(key="metadata.user_id", match=MatchValue(value=user_id)),
                FieldCondition(
                    key="metadata.ingest_batch_id",
                    match=MatchValue(value=ingest_batch_id),
                ),
            ]
        )

    def _enrich_chunk(self, chunk: str, metadata: Dict[str, Any]) -> str:
        parts = []
        if metadata.get("source"):
            parts.append(f"Source: {metadata['source']}")
        if metadata.get("course_name"):
            parts.append(f"Course: {metadata['course_name']}")
        if metadata.get("url"):
            parts.append(f"URL: {metadata['url']}")
        ctx = ", ".join(parts) or "Unknown"
        return f"Context: {ctx}\nContent: {chunk}"

    # ── ingest ────────────────────────────────────────────────────────────────

    async def ingest_text(
        self,
        raw_text: str,
        source_name: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IngestResult:
        chunks = self.text_splitter.split_text(raw_text)
        original_chunks_count = len(chunks)
        truncated = False

        if len(chunks) > settings.MAX_CHUNKS_PER_INGEST:
            chunks = chunks[: settings.MAX_CHUNKS_PER_INGEST]
            truncated = True

        existing_count = await asyncio.to_thread(self.get_user_chunk_count, user_id)
        remaining = settings.MAX_CHUNKS_PER_USER - existing_count
        if remaining <= 0:
            raise QuotaExceededError(
                f"Knowledge base full ({existing_count}/{settings.MAX_CHUNKS_PER_USER} chunks). "
                "Clear some data before adding more."
            )
        if len(chunks) > remaining:
            chunks = chunks[:remaining]
            truncated = True

        ingest_batch_id = uuid4().hex
        ingest_at = datetime.utcnow()
        full_metadata: Dict[str, Any] = {
            "source": source_name,
            "user_id": user_id,
            "created_at": ingest_at.isoformat(),
            "ingest_batch_id": ingest_batch_id,
        }
        if metadata:
            for k, v in metadata.items():
                if k != "ingest_batch_id":
                    full_metadata.setdefault(k, v)

        texts_to_embed = [self._enrich_chunk(c, full_metadata) for c in chunks]
        embeddings_list = await asyncio.to_thread(
            self.embeddings.get_embeddings, texts_to_embed
        )

        points = [
            PointStruct(
                id=str(uuid4()),
                vector=emb,
                payload={"page_content": chunk, "metadata": full_metadata},
            )
            for chunk, emb in zip(chunks, embeddings_list)
        ]

        if points:
            await asyncio.to_thread(
                self.client.upsert,
                collection_name=_COLLECTION,
                points=points,
            )

        return {
            "chunks_count": len(points),
            "ingest_batch_id": ingest_batch_id,
            "ingest_at": ingest_at,
            "truncated": truncated,
            "original_chunks_count": original_chunks_count,
        }

    async def ingest_pdf(
        self,
        file_content: bytes,
        filename: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IngestResult:
        pdf_reader = PdfReader(io.BytesIO(file_content))
        raw_text = "".join(
            page.extract_text() + "\n"
            for page in pdf_reader.pages
            if page.extract_text()
        )
        pdf_meta: Dict[str, Any] = {"source": filename}
        if metadata:
            pdf_meta.update(metadata)
        return await self.ingest_text(
            raw_text, source_name=filename, user_id=user_id, metadata=pdf_meta
        )

    # ── search ────────────────────────────────────────────────────────────────

    def _embed_query(self, query: str) -> List[float]:
        return self.embeddings.get_embeddings([query])[0]

    async def search_context(
        self, query: str, user_id: str, k: int = 5
    ) -> List[dict]:
        qvec = await asyncio.to_thread(self._embed_query, query)
        hits = await asyncio.to_thread(
            self.client.search,
            collection_name=_COLLECTION,
            query_vector=qvec,
            query_filter=self._user_filter(user_id),
            limit=k,
            with_payload=True,
        )
        return [
            {
                "content": h.payload.get("page_content", ""),
                "source": (h.payload.get("metadata") or {}).get("source", "unknown"),
                "score": float(h.score),
            }
            for h in hits
        ]

    async def search_context_mmr(
        self, query: str, user_id: str, k: int = 3, fetch_k: int = 10
    ) -> List[dict]:
        """Fetch fetch_k candidates then select k diverse results via greedy MMR."""
        qvec = await asyncio.to_thread(self._embed_query, query)
        candidates = await asyncio.to_thread(
            self.client.search,
            collection_name=_COLLECTION,
            query_vector=qvec,
            query_filter=self._user_filter(user_id),
            limit=fetch_k,
            with_payload=True,
            with_vectors=True,
        )
        if not candidates:
            return []
        if len(candidates) <= k:
            return [
                {
                    "content": c.payload.get("page_content", ""),
                    "source": (c.payload.get("metadata") or {}).get("source", "unknown"),
                    "score": float(c.score),
                }
                for c in candidates
            ]

        vecs = np.array([c.vector for c in candidates], dtype=float)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms < 1e-9] = 1e-9
        vecs = vecs / norms

        scores = np.array([c.score for c in candidates])
        selected: List[int] = [0]
        remaining = list(range(1, len(candidates)))

        lambda_mult = 0.5
        while len(selected) < k and remaining:
            sel_vecs = vecs[selected]
            remaining_arr = np.array(remaining)
            redundancy = np.max(vecs[remaining_arr] @ sel_vecs.T, axis=1)
            mmr_scores = lambda_mult * scores[remaining_arr] - (1 - lambda_mult) * redundancy
            best_local = int(np.argmax(mmr_scores))
            best_global = remaining[best_local]
            selected.append(best_global)
            remaining.remove(best_global)

        return [
            {
                "content": candidates[i].payload.get("page_content", ""),
                "source": (candidates[i].payload.get("metadata") or {}).get("source", "unknown"),
                "score": float(candidates[i].score),
            }
            for i in selected
        ]

    async def is_batch_searchable(
        self, query: str, user_id: str, ingest_batch_id: str
    ) -> bool:
        qvec = await asyncio.to_thread(self._embed_query, query)
        hits = await asyncio.to_thread(
            self.client.search,
            collection_name=_COLLECTION,
            query_vector=qvec,
            query_filter=self._batch_filter(user_id, ingest_batch_id),
            limit=1,
            with_payload=False,
        )
        return len(hits) > 0

    # ── management ────────────────────────────────────────────────────────────

    def find_chunks_by_user(
        self, user_id: str, limit: int = 10, query: Optional[str] = None
    ) -> List[dict]:
        """BM25 keyword fallback; scrolls all user chunks (quota max is 500)."""
        from rank_bm25 import BM25Okapi

        records, _ = self.client.scroll(
            collection_name=_COLLECTION,
            scroll_filter=self._user_filter(user_id),
            limit=settings.MAX_CHUNKS_PER_USER + 100,
            with_payload=True,
            with_vectors=False,
        )
        if not records:
            return []

        contents = [r.payload.get("page_content", "") for r in records]
        sources = [
            (r.payload.get("metadata") or {}).get("source", "unknown") for r in records
        ]

        if query:
            tokenized = [c.lower().split() for c in contents]
            bm25 = BM25Okapi(tokenized)
            scores = bm25.get_scores(query.lower().split())
            ranked = sorted(
                zip(range(len(records)), scores), key=lambda x: x[1], reverse=True
            )[:limit]
            return [
                {"content": contents[i], "source": sources[i], "score": float(s)}
                for i, s in ranked
            ]

        return [
            {"content": c, "source": s, "score": 0.0}
            for c, s in list(zip(contents, sources))[:limit]
        ]

    def get_user_chunk_count(self, user_id: str) -> int:
        result = self.client.count(
            collection_name=_COLLECTION,
            count_filter=self._user_filter(user_id),
            exact=True,
        )
        return result.count

    def delete_user_data(self, user_id: str) -> int:
        count = self.get_user_chunk_count(user_id)
        self.client.delete(
            collection_name=_COLLECTION,
            points_selector=FilterSelector(filter=self._user_filter(user_id)),
        )
        logger.info("Deleted %d chunks for user_id=%s", count, user_id)
        return count

    def clear_vector_data(self) -> int:
        info = self.client.get_collection(_COLLECTION)
        total = info.points_count or 0
        self.client.delete_collection(_COLLECTION)
        self._ensure_collection()
        logger.info("Cleared all %d chunks from Qdrant", total)
        return total

    def close(self) -> None:
        self.client.close()


_qdrant_store: Optional[QdrantVectorStore] = None


def get_qdrant_store() -> QdrantVectorStore:
    global _qdrant_store
    if _qdrant_store is None:
        _qdrant_store = QdrantVectorStore()
    return _qdrant_store
