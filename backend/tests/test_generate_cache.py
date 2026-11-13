"""Phase 5：/api/generate/stream 的 Redis 结果缓存（命中重放、只缓存成功结果、知识库变化失效、Redis 故障降级）。"""

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.api import generate as generate_api
from app.api import rag as rag_api
from app.infrastructure.cache import redis_cache
from app.infrastructure.cache.redis_cache import CheatSheetCache, make_cache_key

from conftest import bearer
from fake_redis import FakeRedis

META = {"_type": "meta", "title": "Linear Algebra"}
SECTION = {"title": "Eigenvalues", "items": [{"type": "formula", "content": "Av = \\lambda v"}]}
PAYLOAD = {"page_limit": "1_page", "selected_topics": [{"title": "Eigenvalues", "relevance_score": 0.9}]}


class FakeGemini:
    model_name = "gemini-test"


class StreamingService:
    """按脚本吐 SSE 行；mode 控制正常结束 / 中途异常 / 只有 meta。"""

    def __init__(self, mode="ok"):
        self.mode = mode
        self.calls = 0
        self.gemini = FakeGemini()

    async def stream_cheat_sheet_sections(self, request_data, user_id):
        self.calls += 1
        yield f"data: {json.dumps(META)}\n\n"
        if self.mode == "meta_only":
            yield "data: [DONE]\n\n"
            return
        yield f"data: {json.dumps(SECTION)}\n\n"
        if self.mode == "error":
            raise RuntimeError("Gemini 429")
        yield "data: [DONE]\n\n"


def make_app(monkeypatch, service):
    monkeypatch.setattr(generate_api.CheatSheetService, "default", classmethod(lambda cls: service))
    app = FastAPI()
    app.include_router(generate_api.router)
    app.include_router(rag_api.router, prefix="/api/rag")
    app.include_router(auth_api.router)
    return TestClient(app, raise_server_exceptions=False)


def generate(client, user="user-1", payload=None):
    return client.post("/api/generate/stream", headers=bearer(user), json=payload or PAYLOAD)


def data_lines(body: str) -> list[str]:
    return [chunk for chunk in body.split("\n\n") if chunk]


# ── 缓存键 ────────────────────────────────────────────────────────────────────


def test_cache_key_is_deterministic_and_covers_all_content_fields():
    base = {"page_limit": "1", "selected_topics": [{"title": "A", "relevance_score": 1.0}]}
    k = make_cache_key("u1", base, "m")
    assert k == make_cache_key("u1", dict(reversed(list(base.items()))), "m")
    assert k != make_cache_key("u2", base, "m")
    assert k != make_cache_key("u1", {**base, "selected_topics": [{"title": "B", "relevance_score": 1.0}]}, "m")
    assert k != make_cache_key("u1", {**base, "syllabus": "ch 1-3"}, "m")
    assert k != make_cache_key("u1", base, "other-model")


# ── 命中 / 未命中 ─────────────────────────────────────────────────────────────


def test_second_identical_request_replays_from_cache(monkeypatch):
    service = StreamingService()
    client = make_app(monkeypatch, service)

    first = generate(client)
    second = generate(client)

    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"
    assert service.calls == 1
    assert data_lines(second.text) == data_lines(first.text)
    assert data_lines(second.text)[-1] == "data: [DONE]"


def test_different_topics_or_users_do_not_share_cache(monkeypatch):
    service = StreamingService()
    client = make_app(monkeypatch, service)

    generate(client)
    other_topics = {**PAYLOAD, "selected_topics": [{"title": "Determinants", "relevance_score": 0.9}]}
    assert generate(client, payload=other_topics).headers["X-Cache"] == "MISS"
    assert generate(client, user="user-2").headers["X-Cache"] == "MISS"
    assert service.calls == 3


def test_no_cache_bypasses_and_refreshes_entry(monkeypatch):
    service = StreamingService()
    client = make_app(monkeypatch, service)

    generate(client)
    bypass = generate(client, payload={**PAYLOAD, "no_cache": True})

    assert bypass.headers["X-Cache"] == "BYPASS"
    assert service.calls == 2
    # no_cache 不参与缓存键：之后的普通请求命中（被刷新后的）同一条缓存
    assert generate(client).headers["X-Cache"] == "HIT"
    assert service.calls == 2


# ── 只缓存成功结果 ────────────────────────────────────────────────────────────


def test_failed_generation_is_not_cached(monkeypatch):
    service = StreamingService(mode="error")
    client = make_app(monkeypatch, service)

    generate(client)
    service.mode = "ok"
    retry = generate(client)

    assert retry.headers["X-Cache"] == "MISS"
    assert service.calls == 2


def test_result_without_sections_is_not_cached(monkeypatch):
    service = StreamingService(mode="meta_only")
    client = make_app(monkeypatch, service)

    generate(client)
    assert generate(client).headers["X-Cache"] == "MISS"


# ── 知识库变化 → 失效 ─────────────────────────────────────────────────────────


class FakeIngestion:
    async def process_text(self, text, metadata, user_id):
        return {
            "truncated": False,
            "chunks_count": 1,
            "ingest_batch_id": "b1",
            "ingest_at": "2026-11-13T00:00:00Z",
            "original_chunks_count": 1,
        }

    async def delete_user_data(self, user_id):
        return 3


def test_ingest_invalidates_only_that_users_cache(monkeypatch):
    service = StreamingService()
    client = make_app(monkeypatch, service)
    monkeypatch.setattr(rag_api.IngestionService, "default", classmethod(lambda cls: FakeIngestion()))

    generate(client, user="user-1")
    generate(client, user="user-2")
    res = client.post("/api/rag/ingest", headers=bearer("user-1"), json={"text": "new notes", "source": "s"})
    assert res.status_code == 200

    assert generate(client, user="user-1").headers["X-Cache"] == "MISS"
    assert generate(client, user="user-2").headers["X-Cache"] == "HIT"


def test_deleting_chunks_invalidates_cache(monkeypatch):
    service = StreamingService()
    client = make_app(monkeypatch, service)
    monkeypatch.setattr(rag_api.IngestionService, "default", classmethod(lambda cls: FakeIngestion()))

    generate(client)
    assert client.delete("/api/rag/chunks", headers=bearer("user-1")).status_code == 200
    assert generate(client).headers["X-Cache"] == "MISS"


@pytest.mark.parametrize("moved,expected", [(2, "MISS"), (0, "HIT")])
def test_link_anon_invalidates_when_chunks_moved(monkeypatch, moved, expected):
    service = StreamingService()
    client = make_app(monkeypatch, service)

    class FakeAccount:
        async def link_anon_data(self, anon_id, clerk_id):
            return {"status": "linked", "chunks_moved": moved}

    monkeypatch.setattr(auth_api.AccountService, "default", classmethod(lambda cls: FakeAccount()))

    generate(client)
    assert client.post("/api/auth/link-anon", headers=bearer("user-1"), json={"anon_id": "a"}).status_code == 200
    assert generate(client).headers["X-Cache"] == expected


def test_invalidate_all_removes_every_users_entries():
    cache = CheatSheetCache(FakeRedis(), ttl_seconds=60)

    async def scenario():
        await cache.set("u1", make_cache_key("u1", {}, "m"), ["{}"])
        await cache.set("u2", make_cache_key("u2", {}, "m"), ["{}"])
        return await cache.invalidate_all()

    assert asyncio.run(scenario()) == 4  # 2 个结果键 + 2 个索引集合
    assert cache.client.data == {}


# ── Redis 故障降级 ────────────────────────────────────────────────────────────


def test_generation_still_works_when_redis_is_down(monkeypatch):
    monkeypatch.setattr(redis_cache, "_cache", CheatSheetCache(FakeRedis(fail=True), ttl_seconds=60))
    service = StreamingService()
    client = make_app(monkeypatch, service)

    first = generate(client)
    second = generate(client)

    assert first.status_code == second.status_code == 200
    assert data_lines(second.text)[-1] == "data: [DONE]"
    assert service.calls == 2


def test_ttl_zero_disables_cache(monkeypatch):
    monkeypatch.setattr(redis_cache, "_cache", CheatSheetCache(FakeRedis(), ttl_seconds=0))
    service = StreamingService()
    client = make_app(monkeypatch, service)

    generate(client)
    assert generate(client).headers["X-Cache"] == "MISS"
    assert service.calls == 2
