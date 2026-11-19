from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import cheat_sheets as cheat_sheets_api

from conftest import bearer
from fake_supabase import FakeSupabase

MISSING_ID = "11111111-1111-4111-8111-111111111111"


def create_client(monkeypatch, store):
    monkeypatch.setattr(cheat_sheets_api, "get_supabase_store", lambda: store)
    app = FastAPI()
    app.include_router(cheat_sheets_api.router)
    return TestClient(app)


SECTIONS_FROM_WEBAPP = [
    {
        "id": "section-1",  # 前端运行时字段，应被丢弃
        "isStreaming": False,
        "title": "Eigenvalues",
        "items": [{"type": "equation", "content": "Av = \\lambda v"}],
    }
]


def create(client, user="anon-1", **body):
    body.setdefault("title", "Linear Algebra")
    body.setdefault("sections", [])
    return client.post("/api/cheat-sheets", headers=bearer(user), json=body)


def test_create_strips_runtime_fields_and_returns_id(monkeypatch):
    store = FakeSupabase()
    client = create_client(monkeypatch, store)

    response = create(client, sections=SECTIONS_FROM_WEBAPP)

    assert response.status_code == 201
    saved = store.sheets[response.json()["id"]]
    assert saved["user_id"] == "db-anon-1"
    assert saved["sections"] == [
        {"title": "Eigenvalues", "items": [{"type": "equation", "content": "Av = \\lambda v"}]}
    ]


def test_create_accepts_item_type_outside_enum(monkeypatch):
    client = create_client(monkeypatch, FakeSupabase())

    response = create(
        client, title="", sections=[{"title": "S", "items": [{"type": "example", "content": "x"}]}]
    )

    assert response.status_code == 201


def test_get_and_update_are_scoped_to_owner(monkeypatch):
    store = FakeSupabase()
    client = create_client(monkeypatch, store)
    sheet_id = create(client, title="Mine").json()["id"]

    assert client.get(f"/api/cheat-sheets/{sheet_id}", headers=bearer("anon-1")).status_code == 200
    assert client.get(f"/api/cheat-sheets/{sheet_id}", headers=bearer("anon-2")).status_code == 404

    other = client.put(
        f"/api/cheat-sheets/{sheet_id}",
        headers=bearer("anon-2"),
        json={"title": "Hijacked", "sections": []},
    )
    assert other.status_code == 404
    assert store.sheets[sheet_id]["title"] == "Mine"

    mine = client.put(
        f"/api/cheat-sheets/{sheet_id}",
        headers=bearer("anon-1"),
        json={"title": "Renamed", "sections": []},
    )
    assert mine.status_code == 200
    assert mine.json()["title"] == "Renamed"


def test_invalid_sheet_id_is_rejected(monkeypatch):
    client = create_client(monkeypatch, FakeSupabase())

    response = client.get("/api/cheat-sheets/not-a-uuid", headers=bearer("anon-1"))

    assert response.status_code == 422


def test_returns_503_when_supabase_not_configured(monkeypatch):
    client = create_client(monkeypatch, None)

    response = create(client, title="x")

    assert response.status_code == 503


# ── 第 8 点：课程与版本 ──────────────────────────────────────────────────────


def test_create_without_course_goes_to_default_course(monkeypatch):
    store = FakeSupabase()
    client = create_client(monkeypatch, store)

    body = create(client).json()

    course = store.courses[body["course_id"]]
    assert course["is_default"] is True
    assert course["name"] == "Uncategorized"
    assert body["version"] == 1
    assert body["origin"] == "generate"


def test_each_generation_is_a_new_version_and_edits_keep_the_version(monkeypatch):
    store = FakeSupabase()
    client = create_client(monkeypatch, store)
    course = store.create_course("db-anon-1", "CS229")

    v1 = create(client, course_id=course["id"], generation_params={"topics": ["a"]}).json()
    v2 = create(client, course_id=course["id"], generation_params={"topics": ["b"]}).json()
    assert (v1["version"], v2["version"]) == (1, 2)
    assert v1["id"] != v2["id"]

    edited = client.put(
        f"/api/cheat-sheets/{v2['id']}",
        headers=bearer("anon-1"),
        json={"title": "Edited", "sections": []},
    ).json()
    assert edited["version"] == 2
    assert len(store.list_course_sheets("db-anon-1", course["id"])) == 2


def test_reopening_same_cached_generation_does_not_duplicate_version(monkeypatch):
    store = FakeSupabase()
    client = create_client(monkeypatch, store)
    params = {"selected_topics": [{"title": "Eigenvalues", "relevance_score": 1}]}

    first = create(client, generation_params=params, sections=SECTIONS_FROM_WEBAPP).json()
    again = create(client, generation_params=params, sections=SECTIONS_FROM_WEBAPP).json()

    assert again["id"] == first["id"]
    assert again["version"] == 1


def test_create_rejects_other_users_course(monkeypatch):
    store = FakeSupabase()
    client = create_client(monkeypatch, store)
    foreign = store.create_course("db-anon-2", "Not yours")

    response = create(client, course_id=foreign["id"])

    assert response.status_code == 404
    assert store.sheets == {}


def test_create_rejects_unknown_parent_version(monkeypatch):
    client = create_client(monkeypatch, FakeSupabase())

    response = create(client, parent_sheet_id=MISSING_ID, origin="regenerate")

    assert response.status_code == 404


def test_create_records_parent_and_origin(monkeypatch):
    store = FakeSupabase()
    client = create_client(monkeypatch, store)
    parent = create(client).json()

    child = create(client, parent_sheet_id=parent["id"], origin="regenerate", title="v2").json()

    assert child["parent_sheet_id"] == parent["id"]
    assert child["origin"] == "regenerate"
    assert child["version"] == 2
