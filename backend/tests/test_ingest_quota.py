"""Tests for ingestion quota & truncation logic (QdrantVectorStore + /api/rag HTTP layer)."""

from __future__ import annotations

import asyncio
import io
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.rag import router as rag_router
from app.application.services.ingestion_service import IngestionService
from app.infrastructure.rag.qdrant_store import QdrantVectorStore, QuotaExceededError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def create_client():
    app = FastAPI()
    app.include_router(rag_router, prefix="/api/rag")
    return TestClient(app)


def _make_fake_store(existing_chunk_count: int, chunks: list[str]) -> QdrantVectorStore:
    """QdrantVectorStore with __init__ skipped; Qdrant / OpenAI / splitter stubbed."""
    with patch.object(QdrantVectorStore, "__init__", lambda self: None):
        vs = QdrantVectorStore()
    vs.client = MagicMock()
    vs.embeddings = MagicMock()
    vs.embeddings.get_embeddings = MagicMock(side_effect=lambda texts: [[0.1] * 3] * len(texts))
    vs.text_splitter = MagicMock()
    vs.text_splitter.split_text = MagicMock(return_value=chunks)
    vs.get_user_chunk_count = MagicMock(return_value=existing_chunk_count)
    return vs


def _ingest(vs: QdrantVectorStore, max_per_ingest: int = 200, max_per_user: int = 500):
    with patch("app.infrastructure.rag.qdrant_store.settings") as mock_settings:
        mock_settings.MAX_CHUNKS_PER_INGEST = max_per_ingest
        mock_settings.MAX_CHUNKS_PER_USER = max_per_user
        return asyncio.run(vs.ingest_text("text", "src", "user-1"))


# ---------------------------------------------------------------------------
# Unit tests – QdrantVectorStore.ingest_text truncation / quota
# ---------------------------------------------------------------------------


def test_per_ingest_limit_truncates():
    vs = _make_fake_store(0, [f"chunk-{i}" for i in range(250)])

    result = _ingest(vs)

    assert result["truncated"] is True
    assert result["original_chunks_count"] == 250
    assert result["chunks_count"] == 200
    assert len(vs.client.upsert.call_args.kwargs["points"]) == 200


def test_per_user_limit_truncates():
    vs = _make_fake_store(480, [f"chunk-{i}" for i in range(50)])

    result = _ingest(vs)

    assert result["truncated"] is True
    assert result["original_chunks_count"] == 50
    assert result["chunks_count"] == 20


def test_quota_exceeded_raises_without_writing():
    vs = _make_fake_store(500, ["chunk"])

    with pytest.raises(QuotaExceededError):
        _ingest(vs)
    vs.client.upsert.assert_not_called()


def test_no_truncation_within_limits():
    vs = _make_fake_store(10, [f"chunk-{i}" for i in range(5)])

    result = _ingest(vs)

    assert result["truncated"] is False
    assert result["chunks_count"] == 5
    payload = vs.client.upsert.call_args.kwargs["points"][0].payload
    assert payload["metadata"]["user_id"] == "user-1"
    assert payload["metadata"]["ingest_batch_id"] == result["ingest_batch_id"]


# ---------------------------------------------------------------------------
# API integration tests – HTTP layer
# ---------------------------------------------------------------------------


def test_ingest_text_returns_truncated_status():
    fake_result = {
        "chunks_count": 200,
        "ingest_batch_id": "abc123",
        "ingest_at": datetime(2026, 1, 1),
        "truncated": True,
        "original_chunks_count": 350,
    }

    async def _fake_process_text(**kwargs):
        return fake_result

    with patch.object(IngestionService, "default") as mock_default:
        mock_default.return_value = MagicMock(process_text=_fake_process_text)
        resp = create_client().post(
            "/api/rag/ingest",
            json={"text": "x" * 1000, "source": "test"},
            headers={"X-User-ID": "user-1"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "truncated"
    assert data["truncated"] is True
    assert data["original_chunks_count"] == 350
    assert data["chunks_count"] == 200


def test_ingest_text_returns_429_on_quota_exceeded():
    with patch.object(IngestionService, "default") as mock_default:
        mock_default.return_value = MagicMock(
            process_text=MagicMock(
                side_effect=QuotaExceededError("Knowledge base full (500/500 chunks).")
            )
        )
        resp = create_client().post(
            "/api/rag/ingest",
            json={"text": "hello", "source": "test"},
            headers={"X-User-ID": "user-1"},
        )

    assert resp.status_code == 429
    assert "500/500" in resp.json()["detail"]


def test_ingest_file_returns_429_on_quota_exceeded():
    with patch.object(IngestionService, "default") as mock_default:
        mock_default.return_value = MagicMock(
            process_file=MagicMock(side_effect=QuotaExceededError("Knowledge base full"))
        )
        resp = create_client().post(
            "/api/rag/ingest/file",
            headers={"X-User-ID": "user-1"},
            files={"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        )

    assert resp.status_code == 429
    assert "full" in resp.json()["detail"].lower()
