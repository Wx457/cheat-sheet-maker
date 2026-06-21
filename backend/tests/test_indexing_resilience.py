"""Tests for Atlas indexing resilience — exponential backoff + MongoDB fallback (Problem 2)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.services.cheat_sheet_service import CheatSheetService
from app.infrastructure.rag.vector_store import VectorStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(
    is_batch_searchable_seq: list[bool] | None = None,
    search_context_results: list[list[dict]] | None = None,
    find_chunks_results: list[dict] | None = None,
) -> CheatSheetService:
    """Build a CheatSheetService with mocked VectorStore."""
    rag = MagicMock(spec=VectorStore)

    if is_batch_searchable_seq is not None:
        rag.is_batch_searchable = AsyncMock(side_effect=is_batch_searchable_seq)
    else:
        rag.is_batch_searchable = AsyncMock(return_value=True)

    if search_context_results is not None:
        rag.search_context = AsyncMock(side_effect=search_context_results)
    else:
        rag.search_context = AsyncMock(return_value=[])

    rag.find_chunks_by_user = MagicMock(return_value=find_chunks_results or [])

    svc = CheatSheetService(
        gemini=MagicMock(),
        rag_service=rag,
        storage_client=MagicMock(),
    )
    return svc


FAKE_CHUNK = {"content": "test content", "source": "test.pdf", "score": 0.8}
FALLBACK_CHUNK = {"content": "fallback content", "source": "test.pdf", "score": 0.0}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSearchContextWithRetry:
    """Verify the retry + fallback logic in _search_context_with_retry."""

    @pytest.mark.asyncio
    async def test_immediate_success_no_extra_retries(self):
        svc = _make_service(search_context_results=[[FAKE_CHUNK]])

        with patch("app.application.services.cheat_sheet_service.settings") as s:
            s.RAG_RETRY_ATTEMPTS = 6
            s.RAG_RETRY_DELAY_SECONDS = 2
            result = await svc._search_context_with_retry("q", "u1", k=5)

        assert len(result) == 1
        assert result[0]["content"] == "test content"
        svc.rag_service.search_context.assert_awaited_once()
        svc.rag_service.find_chunks_by_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_succeeds_on_third_attempt(self):
        svc = _make_service(search_context_results=[[], [], [FAKE_CHUNK]])

        with patch("app.application.services.cheat_sheet_service.settings") as s:
            s.RAG_RETRY_ATTEMPTS = 6
            s.RAG_RETRY_DELAY_SECONDS = 0  # no real sleep in test
            result = await svc._search_context_with_retry("q", "u1", k=5)

        assert len(result) == 1
        assert svc.rag_service.search_context.await_count == 3
        svc.rag_service.find_chunks_by_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_plain_mongo_when_vector_exhausted(self):
        svc = _make_service(
            search_context_results=[[], [], []],
            find_chunks_results=[FALLBACK_CHUNK],
        )

        with patch("app.application.services.cheat_sheet_service.settings") as s:
            s.RAG_RETRY_ATTEMPTS = 3
            s.RAG_RETRY_DELAY_SECONDS = 0
            result = await svc._search_context_with_retry("q", "u1", k=5)

        assert len(result) == 1
        assert result[0]["content"] == "fallback content"
        assert svc.rag_service.search_context.await_count == 3
        svc.rag_service.find_chunks_by_user.assert_called_once_with("u1", 5, "q")

    @pytest.mark.asyncio
    async def test_fallback_also_empty_returns_empty(self):
        svc = _make_service(
            search_context_results=[[], []],
            find_chunks_results=[],
        )

        with patch("app.application.services.cheat_sheet_service.settings") as s:
            s.RAG_RETRY_ATTEMPTS = 2
            s.RAG_RETRY_DELAY_SECONDS = 0
            result = await svc._search_context_with_retry("q", "u1", k=5)

        assert result == []

    @pytest.mark.asyncio
    async def test_batch_not_ready_retries_with_backoff(self):
        """When batch isn't searchable, retries skip search_context and wait."""
        svc = _make_service(
            is_batch_searchable_seq=[False, False, True],
            search_context_results=[[FAKE_CHUNK]],
        )

        with patch("app.application.services.cheat_sheet_service.settings") as s:
            s.RAG_RETRY_ATTEMPTS = 4
            s.RAG_RETRY_DELAY_SECONDS = 0
            result = await svc._search_context_with_retry(
                "q", "u1", k=5, required_batch_id="batch-abc"
            )

        assert len(result) == 1
        assert svc.rag_service.is_batch_searchable.await_count == 3
        svc.rag_service.search_context.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_batch_never_ready_triggers_fallback(self):
        svc = _make_service(
            is_batch_searchable_seq=[False, False, False],
            find_chunks_results=[FALLBACK_CHUNK],
        )

        with patch("app.application.services.cheat_sheet_service.settings") as s:
            s.RAG_RETRY_ATTEMPTS = 3
            s.RAG_RETRY_DELAY_SECONDS = 0
            result = await svc._search_context_with_retry(
                "q", "u1", k=5, required_batch_id="batch-xyz"
            )

        assert len(result) == 1
        assert result[0]["content"] == "fallback content"
        svc.rag_service.search_context.assert_not_awaited()
        svc.rag_service.find_chunks_by_user.assert_called_once()


class TestFindChunksByUser:
    """Verify VectorStore.find_chunks_by_user returns properly formatted results."""

    def test_returns_formatted_chunks(self):
        """No-query path: time-based ordering, score=0.0."""
        with patch.object(VectorStore, "__init__", lambda self: None):
            vs = VectorStore()

        vs.mongo_retry_attempts = 1
        vs.mongo_retry_base_delay_seconds = 0
        vs.retryable_errors = ()

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.limit.return_value = iter([
            {"page_content": "chunk A", "metadata": {"source": "s1"}},
            {"page_content": "chunk B", "metadata": {"source": "s2"}},
        ])

        vs.collection = MagicMock()
        vs.collection.find.return_value = mock_cursor
        vs._run_with_retry = MagicMock(side_effect=lambda name, op: op())

        result = vs.find_chunks_by_user("user-1", limit=5)

        assert len(result) == 2
        assert result[0] == {"content": "chunk A", "source": "s1", "score": 0.0}
        assert result[1] == {"content": "chunk B", "source": "s2", "score": 0.0}

    def test_bm25_ranks_by_query_relevance(self):
        """BM25 path: query-relevant chunks ranked first with non-zero scores."""
        with patch.object(VectorStore, "__init__", lambda self: None):
            vs = VectorStore()

        vs.mongo_retry_attempts = 1
        vs.mongo_retry_base_delay_seconds = 0
        vs.retryable_errors = ()

        mock_docs = [
            {"page_content": "cooking recipes food kitchen", "metadata": {"source": "s1"}},
            {"page_content": "eigenvalue decomposition matrix algebra", "metadata": {"source": "s2"}},
            {"page_content": "matrix operations linear algebra eigenvalue", "metadata": {"source": "s3"}},
        ]

        vs.collection = MagicMock()
        vs.collection.find.return_value = iter(mock_docs)
        vs._run_with_retry = MagicMock(side_effect=lambda name, op: op())

        result = vs.find_chunks_by_user("user-1", limit=2, query="eigenvalue matrix")

        assert len(result) == 2
        # BM25 should put the math-related chunks ahead of the cooking chunk
        assert result[0]["source"] in ("s2", "s3")
        assert result[1]["source"] in ("s2", "s3")
        # Scores should be positive (keyword overlap exists)
        assert result[0]["score"] > 0.0

    def test_bm25_returns_empty_when_no_docs(self):
        """BM25 path with empty collection returns empty list without error."""
        with patch.object(VectorStore, "__init__", lambda self: None):
            vs = VectorStore()

        vs.mongo_retry_attempts = 1
        vs.mongo_retry_base_delay_seconds = 0
        vs.retryable_errors = ()

        vs.collection = MagicMock()
        vs.collection.find.return_value = iter([])
        vs._run_with_retry = MagicMock(side_effect=lambda name, op: op())

        result = vs.find_chunks_by_user("user-1", limit=5, query="some query")

        assert result == []
