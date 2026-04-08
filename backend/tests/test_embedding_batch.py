"""Tests for embedding sub-batching logic (Problem 1)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call
from types import SimpleNamespace

from app.infrastructure.llm.openai_client import OpenAIClient


def _make_client(batch_size: int = 3, batch_delay: float = 0.0) -> OpenAIClient:
    """Build an OpenAIClient with a stubbed OpenAI SDK client."""
    with patch.object(OpenAIClient, "__init__", lambda self, *a, **kw: None):
        client = OpenAIClient()

    client.model = "text-embedding-3-small"
    client.batch_size = batch_size
    client.batch_delay = batch_delay

    mock_openai = MagicMock()
    client.client = mock_openai
    return client


def _fake_embeddings_create(input, model):  # noqa: A002
    """Return a fake response whose embeddings are the index of each text."""
    data = [SimpleNamespace(embedding=[float(i)]) for i in range(len(input))]
    return SimpleNamespace(data=data)


class TestEmbedDocumentsSubBatch:
    def test_small_input_single_batch(self):
        """Inputs <= batch_size go through in one API call."""
        client = _make_client(batch_size=10)
        client.client.embeddings.create = MagicMock(side_effect=_fake_embeddings_create)

        result = client.embed_documents(["a", "b", "c"])

        assert len(result) == 3
        assert client.client.embeddings.create.call_count == 1

    def test_large_input_splits_into_batches(self):
        """Inputs > batch_size are split into ceil(N/batch_size) API calls."""
        client = _make_client(batch_size=3)
        client.client.embeddings.create = MagicMock(side_effect=_fake_embeddings_create)

        texts = [f"text-{i}" for i in range(10)]
        result = client.embed_documents(texts)

        assert len(result) == 10
        assert client.client.embeddings.create.call_count == 4  # ceil(10/3)

    def test_batch_delay_applied_between_batches(self):
        """Inter-batch delay is called (N-1) times for N batches."""
        client = _make_client(batch_size=2, batch_delay=0.25)
        client.client.embeddings.create = MagicMock(side_effect=_fake_embeddings_create)

        with patch("app.infrastructure.llm.openai_client.time.sleep") as mock_sleep:
            client.embed_documents(["a", "b", "c", "d", "e"])

        assert mock_sleep.call_count == 2  # 3 batches → 2 delays
        mock_sleep.assert_called_with(0.25)

    def test_no_delay_when_zero(self):
        """No sleep call when batch_delay is 0."""
        client = _make_client(batch_size=2, batch_delay=0.0)
        client.client.embeddings.create = MagicMock(side_effect=_fake_embeddings_create)

        with patch("app.infrastructure.llm.openai_client.time.sleep") as mock_sleep:
            client.embed_documents(["a", "b", "c"])

        mock_sleep.assert_not_called()

    def test_empty_input_returns_empty(self):
        client = _make_client()
        assert client.embed_documents([]) == []

    def test_order_preserved_across_batches(self):
        """Embedding order must match the original text order."""
        client = _make_client(batch_size=2)

        call_counter = {"n": 0}

        def _ordered_create(input, model):  # noqa: A002
            base = call_counter["n"] * 2
            call_counter["n"] += 1
            data = [SimpleNamespace(embedding=[float(base + i)]) for i in range(len(input))]
            return SimpleNamespace(data=data)

        client.client.embeddings.create = MagicMock(side_effect=_ordered_create)

        result = client.embed_documents(["a", "b", "c", "d", "e"])

        assert result == [[0.0], [1.0], [2.0], [3.0], [4.0]]

    def test_get_embeddings_delegates_to_embed_documents(self):
        """get_embeddings is an alias for embed_documents."""
        client = _make_client(batch_size=10)
        client.client.embeddings.create = MagicMock(side_effect=_fake_embeddings_create)

        result = client.get_embeddings(["x", "y"])

        assert len(result) == 2
        assert client.client.embeddings.create.call_count == 1
