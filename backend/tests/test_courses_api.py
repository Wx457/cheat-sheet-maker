"""第 8 点 · 8-1：课程 API，以及 ingest / 检索 / 生成按课程隔离。"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import courses as courses_api
from app.api import generate as generate_api
from app.api import rag as rag_api
from app.application.services import course_service

from conftest import bearer
from fake_supabase import FakeSupabase

MISSING_ID = "11111111-1111-4111-8111-111111111111"


class FakeVectors:
    def __init__(self):
        self.deleted = []
        self.counted = []

    def delete_user_data(self, user_id, course_id=None):
        self.deleted.append((user_id, course_id))
        return 5

    def get_user_chunk_count(self, user_id, course_id=None):
        self.counted.append((user_id, course_id))
        return 42


class FakeIngestion:
    def __init__(self, vectors):
        self.rag_service = vectors
        self.ingested = []

    async def process_text(self, text, metadata, user_id):
        self.ingested.append(metadata)
        return {
            "truncated": False,
            "chunks_count": 1,
            "ingest_batch_id": "b1",
            "ingest_at": "2026-11-19T00:00:00Z",
            "original_chunks_count": 1,
        }


class StreamingService:
    class gemini:
        model_name = "gemini-test"

    def __init__(self):
        self.requests = []

    async def stream_cheat_sheet_sections(self, request_data, user_id):
        self.requests.append(request_data)
        yield f"data: {json.dumps({'_type': 'meta', 'title': 'T'})}\n\n"
        yield f"data: {json.dumps({'title': 'S', 'items': []})}\n\n"
        yield "data: [DONE]\n\n"


@pytest.fixture
def env(monkeypatch):
    store = FakeSupabase()
    vectors = FakeVectors()
    ingestion = FakeIngestion(vectors)
    service = StreamingService()
    monkeypatch.setattr(course_service, "get_supabase_store", lambda: store)
    monkeypatch.setattr(course_service, "get_qdrant_store", lambda: vectors)
    monkeypatch.setattr(rag_api.IngestionService, "default", classmethod(lambda cls: ingestion))
    monkeypatch.setattr(generate_api.CheatSheetService, "default", classmethod(lambda cls: service))

    app = FastAPI()
    app.include_router(courses_api.router)
    app.include_router(rag_api.router, prefix="/api/rag")
    app.include_router(generate_api.router)
    client = TestClient(app)
    return client, store, vectors, ingestion, service


def new_course(client, name="CS229", user="user-1", **extra):
    return client.post("/api/courses", headers=bearer(user), json={"name": name, **extra})


# ── 课程 CRUD ────────────────────────────────────────────────────────────────


def test_list_always_contains_default_course(env):
    client, *_ = env

    courses = client.get("/api/courses", headers=bearer("user-1")).json()

    assert [(c["name"], c["is_default"]) for c in courses] == [("Uncategorized", True)]


def test_create_list_and_most_recent_first(env):
    client, *_ = env
    client.get("/api/courses", headers=bearer("user-1"))

    created = new_course(client, "  Machine   Learning ", archetype="stem_theoretical")
    assert created.status_code == 201
    assert created.json()["name"] == "Machine Learning"  # 空白规整
    assert created.json()["archetype"] == "stem_theoretical"

    names = [c["name"] for c in client.get("/api/courses", headers=bearer("user-1")).json()]
    assert names == ["Machine Learning", "Uncategorized"]


def test_duplicate_name_is_409_case_insensitive(env):
    client, *_ = env
    new_course(client, "CS229")

    assert new_course(client, "cs229").status_code == 409
    # 不同用户可以同名
    assert new_course(client, "cs229", user="user-2").status_code == 201


def test_invalid_course_fields_are_422(env):
    client, *_ = env

    assert new_course(client, "   ").status_code == 422
    assert new_course(client, "Lit", archetype="astrology").status_code == 422


def test_rename_and_update_defaults(env):
    client, *_ = env
    cid = new_course(client).json()["id"]

    res = client.patch(
        f"/api/courses/{cid}",
        headers=bearer("user-1"),
        json={"name": "CS229 Fall", "academic_level": "graduate"},
    )

    assert res.status_code == 200
    assert res.json()["name"] == "CS229 Fall"
    assert res.json()["academic_level"] == "graduate"


def test_rename_to_existing_name_is_409(env):
    client, *_ = env
    new_course(client, "A")
    b = new_course(client, "B").json()["id"]

    res = client.patch(f"/api/courses/{b}", headers=bearer("user-1"), json={"name": "a"})

    assert res.status_code == 409


def test_other_users_course_is_404_everywhere(env):
    client, *_ = env
    cid = new_course(client, user="owner").json()["id"]
    intruder = bearer("intruder")

    assert client.get(f"/api/courses/{cid}", headers=intruder).status_code == 404
    assert client.patch(f"/api/courses/{cid}", headers=intruder, json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/courses/{cid}", headers=intruder).status_code == 404
    assert client.get(f"/api/rag/chunks/count?course_id={cid}", headers=intruder).status_code == 404
    assert client.post(
        "/api/rag/ingest", headers=intruder, json={"text": "x", "source": "s", "course_id": cid}
    ).status_code == 404
    assert client.post("/api/outline", headers=intruder, json={"course_id": cid}).status_code == 404
    assert client.post(
        "/api/generate/stream", headers=intruder, json={"course_id": cid}
    ).status_code == 404


def test_detail_lists_versions_newest_first(env):
    client, store, *_ = env
    cid = new_course(client).json()["id"]
    store.create_cheat_sheet("db-user-1", cid, "first", [], {"p": 1})
    store.create_cheat_sheet("db-user-1", cid, "second", [], {"p": 2})

    detail = client.get(f"/api/courses/{cid}", headers=bearer("user-1")).json()

    assert detail["course"]["sheet_count"] == 2
    assert [(s["title"], s["version"]) for s in detail["sheets"]] == [("second", 2), ("first", 1)]
    assert "sections" not in detail["sheets"][0]


def test_delete_course_removes_sheets_chunks_and_cache(env, fake_cache):
    client, store, vectors, *_ = env
    cid = new_course(client).json()["id"]
    store.create_cheat_sheet("db-user-1", cid, "v1", [], None)
    client.post("/api/generate/stream", headers=bearer("user-1"), json={"course_id": cid})

    res = client.delete(f"/api/courses/{cid}", headers=bearer("user-1"))

    assert res.status_code == 200
    assert res.json() == {"deleted_sheets": 1, "deleted_chunks": 5}
    assert vectors.deleted == [("user-1", cid)]
    assert cid not in store.courses and store.sheets == {}
    again = client.post("/api/generate/stream", headers=bearer("user-1"), json={"course_id": cid})
    assert again.status_code == 404


def test_courses_api_503_without_supabase(env, monkeypatch):
    client, *_ = env
    monkeypatch.setattr(course_service, "get_supabase_store", lambda: None)

    assert client.get("/api/courses", headers=bearer("user-1")).status_code == 503


# ── 知识库按课程隔离 ─────────────────────────────────────────────────────────


def test_ingest_tags_chunks_with_course(env):
    client, store, _, ingestion, _ = env
    cid = new_course(client, "CS229").json()["id"]

    res = client.post(
        "/api/rag/ingest", headers=bearer("user-1"), json={"text": "x", "source": "s", "course_id": cid}
    )

    assert res.status_code == 200
    assert ingestion.ingested[-1] == {"source": "s", "course_id": cid, "course_name": "CS229"}


def test_ingest_without_course_goes_to_default(env):
    client, store, _, ingestion, _ = env

    client.post("/api/rag/ingest", headers=bearer("user-1"), json={"text": "x", "source": "s"})

    default = store.get_or_create_default_course("db-user-1")
    assert ingestion.ingested[-1]["course_id"] == default["id"]


def test_chunk_count_scoped_by_course_or_whole_user(env):
    client, _, vectors, *_ = env
    cid = new_course(client).json()["id"]

    client.get(f"/api/rag/chunks/count?course_id={cid}", headers=bearer("user-1"))
    client.get("/api/rag/chunks/count", headers=bearer("user-1"))

    assert vectors.counted == [("user-1", cid), ("user-1", None)]


def test_generate_retrieves_from_course_and_caches_per_course(env):
    client, _, _, _, service = env
    a = new_course(client, "A").json()["id"]
    b = new_course(client, "B").json()["id"]

    first = client.post("/api/generate/stream", headers=bearer("user-1"), json={"course_id": a})
    other = client.post("/api/generate/stream", headers=bearer("user-1"), json={"course_id": b})
    repeat = client.post("/api/generate/stream", headers=bearer("user-1"), json={"course_id": a})

    assert [str(r.course_id) for r in service.requests] == [a, b]
    assert (first.headers["X-Cache"], other.headers["X-Cache"], repeat.headers["X-Cache"]) == (
        "MISS",
        "MISS",
        "HIT",
    )


def test_generate_without_course_uses_default(env):
    client, store, _, _, service = env

    client.post("/api/generate/stream", headers=bearer("user-1"), json={})

    default = store.get_or_create_default_course("db-user-1")
    assert str(service.requests[0].course_id) == default["id"]


def test_unknown_course_id_is_404(env):
    client, *_ = env

    assert client.get(f"/api/courses/{MISSING_ID}", headers=bearer("user-1")).status_code == 404
    assert client.get("/api/courses/not-a-uuid", headers=bearer("user-1")).status_code == 422
