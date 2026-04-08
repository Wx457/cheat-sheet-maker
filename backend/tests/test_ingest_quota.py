"""Tests for ingestion quota & truncation logic (Problem 3)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.rag import router as rag_router
from app.infrastructure.rag.vector_store import QuotaExceededError, VectorStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_client():
    app = FastAPI()
    app.include_router(rag_router, prefix="/api/rag")
    return TestClient(app)


def _make_fake_vector_store(existing_chunk_count: int = 0):
    """Return a VectorStore whose __init__ and Mongo calls are stubbed out."""
    with patch.object(VectorStore, "__init__", lambda self: None):
        vs = VectorStore()

    vs.text_splitter = MagicMock()
    vs.embeddings = MagicMock()
    vs.collection = MagicMock()
    vs.client = MagicMock()
    vs.mongo_retry_attempts = 1
    vs.mongo_retry_base_delay_seconds = 0
    vs.retryable_errors = ()

    vs.get_user_chunk_count = MagicMock(return_value=existing_chunk_count)
    vs._run_with_retry = MagicMock(side_effect=lambda name, op: op())

    return vs


# ---------------------------------------------------------------------------
# Unit tests – VectorStore.ingest_text truncation / quota
# ---------------------------------------------------------------------------

class TestIngestTextTruncation:
    """Verify per-ingest and per-user chunk limits."""

    @pytest.mark.asyncio
    async def test_per_ingest_limit_truncates(self):
        """Chunks exceeding MAX_CHUNKS_PER_INGEST are dropped."""
        vs = _make_fake_vector_store(existing_chunk_count=0)

        fake_chunks = [f"chunk-{i}" for i in range(250)]
        vs.text_splitter.split_text = MagicMock(return_value=fake_chunks)
        vs.embeddings.get_embeddings = MagicMock(
            side_effect=lambda texts: [[0.1] * 3] * len(texts)
        )

        with patch("app.infrastructure.rag.vector_store.settings") as mock_settings:
            mock_settings.MAX_CHUNKS_PER_INGEST = 200
            mock_settings.MAX_CHUNKS_PER_USER = 500

            result = await vs.ingest_text("x" * 5000, "src", "user-1")

        assert result["truncated"] is True
        assert result["original_chunks_count"] == 250
        assert result["chunks_count"] == 200

    @pytest.mark.asyncio
    async def test_per_user_limit_truncates(self):
        """When user already has 480 chunks, only 20 more can be ingested."""
        vs = _make_fake_vector_store(existing_chunk_count=480)

        fake_chunks = [f"chunk-{i}" for i in range(50)]
        vs.text_splitter.split_text = MagicMock(return_value=fake_chunks)
        vs.embeddings.get_embeddings = MagicMock(
            side_effect=lambda texts: [[0.1] * 3] * len(texts)
        )

        with patch("app.infrastructure.rag.vector_store.settings") as mock_settings:
            mock_settings.MAX_CHUNKS_PER_INGEST = 200
            mock_settings.MAX_CHUNKS_PER_USER = 500

            result = await vs.ingest_text("x" * 2000, "src", "user-1")

        assert result["truncated"] is True
        assert result["original_chunks_count"] == 50
        assert result["chunks_count"] == 20

    @pytest.mark.asyncio
    async def test_quota_exceeded_raises(self):
        """When user already has MAX_CHUNKS_PER_USER, QuotaExceededError is raised."""
        vs = _make_fake_vector_store(existing_chunk_count=500)

        vs.text_splitter.split_text = MagicMock(return_value=["chunk"])

        with patch("app.infrastructure.rag.vector_store.settings") as mock_settings:
            mock_settings.MAX_CHUNKS_PER_INGEST = 200
            mock_settings.MAX_CHUNKS_PER_USER = 500

            with pytest.raises(QuotaExceededError):
                await vs.ingest_text("some text", "src", "user-1")

    @pytest.mark.asyncio
    async def test_no_truncation_within_limits(self):
        """Normal ingestion within limits returns truncated=False."""
        vs = _make_fake_vector_store(existing_chunk_count=10)

        fake_chunks = [f"chunk-{i}" for i in range(5)]
        vs.text_splitter.split_text = MagicMock(return_value=fake_chunks)
        vs.embeddings.get_embeddings = MagicMock(
            side_effect=lambda texts: [[0.1] * 3] * len(texts)
        )

        with patch("app.infrastructure.rag.vector_store.settings") as mock_settings:
            mock_settings.MAX_CHUNKS_PER_INGEST = 200
            mock_settings.MAX_CHUNKS_PER_USER = 500

            result = await vs.ingest_text("small text", "src", "user-1")

        assert result["truncated"] is False
        assert result["original_chunks_count"] == 5
        assert result["chunks_count"] == 5


# ---------------------------------------------------------------------------
# API integration tests – HTTP layer
# ---------------------------------------------------------------------------

class TestIngestApiQuota:
    """Verify API endpoints propagate truncation info and 429 correctly."""

    def test_ingest_text_returns_truncated_status(self):
        from app.application.services.ingestion_service import IngestionService
        from datetime import datetime

        fake_result = {
            "chunks_count": 200,
            "ingest_batch_id": "abc123",
            "ingest_at": datetime(2026, 1, 1),
            "truncated": True,
            "original_chunks_count": 350,
        }

        client = create_client()

        with patch.object(
            IngestionService, "default"
        ) as mock_default:
            mock_svc = MagicMock()
            async def _fake_process_text(**kwargs):
                return fake_result

            mock_svc.process_text = _fake_process_text
            mock_default.return_value = mock_svc

            resp = client.post(
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

    def test_ingest_text_returns_429_on_quota_exceeded(self):
        from app.application.services.ingestion_service import IngestionService

        client = create_client()

        with patch.object(
            IngestionService, "default"
        ) as mock_default:
            mock_svc = MagicMock()
            mock_svc.process_text = MagicMock(
                side_effect=QuotaExceededError("Knowledge base full (500/500 chunks).")
            )
            mock_default.return_value = mock_svc

            resp = client.post(
                "/api/rag/ingest",
                json={"text": "hello", "source": "test"},
                headers={"X-User-ID": "user-1"},
            )

        assert resp.status_code == 429
        assert "500/500" in resp.json()["detail"]

    def test_ingest_file_returns_429_on_quota_exceeded(self):
        import io
        from app.application.services.ingestion_service import IngestionService

        client = create_client()

        with patch.object(
            IngestionService, "default"
        ) as mock_default:
            mock_svc = MagicMock()
            mock_svc.process_file = MagicMock(
                side_effect=QuotaExceededError("Knowledge base full")
            )
            mock_default.return_value = mock_svc

            resp = client.post(
                "/api/rag/ingest/file",
                headers={"X-User-ID": "user-1"},
                files={"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
            )

        assert resp.status_code == 429
        assert "full" in resp.json()["detail"].lower()
