from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.infrastructure.llm import gemini_client, openai_client, retry_utils


def test_run_with_exponential_backoff_retries_retryable_errors(monkeypatch):
    monkeypatch.setattr(settings, "LLM_MAX_RETRIES", 3)
    monkeypatch.setattr(settings, "LLM_INITIAL_RETRY_DELAY_SECONDS", 1.0)
    monkeypatch.setattr(settings, "LLM_MAX_RETRY_DELAY_SECONDS", 60.0)

    sleep_calls = []
    attempts = {"count": 0}

    def flaky_operation():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("429 rate limit")
        return "ok"

    result = retry_utils.run_with_exponential_backoff(
        "test-op",
        flaky_operation,
        sleep_fn=sleep_calls.append,
    )

    assert result == "ok"
    assert attempts["count"] == 3
    assert sleep_calls == [1.0, 2.0]


def test_run_with_exponential_backoff_does_not_retry_non_retryable_errors(monkeypatch):
    monkeypatch.setattr(settings, "LLM_MAX_RETRIES", 3)

    sleep_calls = []

    with pytest.raises(ValueError, match="bad request"):
        retry_utils.run_with_exponential_backoff(
            "test-op",
            lambda: (_ for _ in ()).throw(ValueError("bad request")),
            sleep_fn=sleep_calls.append,
        )

    assert sleep_calls == []


def test_openai_client_uses_shared_retry_wrapper(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LLM_REQUEST_TIMEOUT_SECONDS", 77)

    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.embeddings = self

        def create(self, input, model):
            captured["input"] = input
            captured["model"] = model
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2]) for _ in input])

    def fake_retry(operation_name, func, sleep_fn=None):
        captured["operation_name"] = operation_name
        return func()

    monkeypatch.setattr(openai_client, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(openai_client, "run_with_exponential_backoff", fake_retry)

    client = openai_client.OpenAIClient()
    embeddings = client.embed_documents(["line 1\nline 2"])

    assert captured["client_kwargs"]["timeout"] == 77
    assert captured["client_kwargs"]["max_retries"] == 0
    assert captured["operation_name"] == "OpenAI embeddings.create (documents)"
    assert captured["input"] == ["line 1 line 2"]
    assert embeddings == [[0.1, 0.2]]


def test_gemini_client_uses_shared_retry_wrapper(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    captured = {"configured_key": None}

    class FakeModel:
        def generate_content(self, prompt):
            captured["prompt"] = prompt
            return SimpleNamespace(text='{"ok": true}')

    monkeypatch.setattr(
        gemini_client.genai,
        "configure",
        lambda api_key: captured.__setitem__("configured_key", api_key),
    )
    monkeypatch.setattr(gemini_client.genai, "GenerativeModel", lambda **kwargs: FakeModel())

    def fake_retry(operation_name, func, sleep_fn=None):
        captured["operation_name"] = operation_name
        return func()

    monkeypatch.setattr(gemini_client, "run_with_exponential_backoff", fake_retry)

    client = gemini_client.GeminiClient()
    result = client.generate_text("hello world")

    assert captured["configured_key"] == "test-key"
    assert captured["operation_name"] == "Gemini generate_content"
    assert captured["prompt"] == "hello world"
    assert result == '{"ok": true}'
