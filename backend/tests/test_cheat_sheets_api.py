from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import cheat_sheets as cheat_sheets_api

SHEET_ID = "11111111-1111-4111-8111-111111111111"
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()


class FakeStore:
    """内存版 SupabaseStore：按 user_id 隔离，模拟归属校验。"""

    def __init__(self):
        self.users = {}
        self.sheets = {}

    def get_or_create_user_id(self, anon_id):
        return self.users.setdefault(anon_id, f"db-{anon_id}")

    def create_cheat_sheet(self, user_id, title, sections):
        row = {
            "id": SHEET_ID,
            "user_id": user_id,
            "title": title,
            "sections": sections,
            "created_at": NOW,
            "updated_at": NOW,
        }
        self.sheets[SHEET_ID] = row
        return row

    def update_cheat_sheet(self, user_id, sheet_id, title, sections):
        row = self.sheets.get(sheet_id)
        if row is None or row["user_id"] != user_id:
            return None
        row.update(title=title, sections=sections)
        return row

    def get_cheat_sheet(self, user_id, sheet_id):
        row = self.sheets.get(sheet_id)
        if row is None or row["user_id"] != user_id:
            return None
        return row


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


def test_create_strips_runtime_fields_and_returns_id(monkeypatch):
    store = FakeStore()
    client = create_client(monkeypatch, store)

    response = client.post(
        "/api/cheat-sheets",
        headers={"X-User-ID": "anon-1"},
        json={"title": "Linear Algebra", "sections": SECTIONS_FROM_WEBAPP},
    )

    assert response.status_code == 201
    assert response.json()["id"] == SHEET_ID
    saved = store.sheets[SHEET_ID]
    assert saved["user_id"] == "db-anon-1"
    assert saved["sections"] == [
        {"title": "Eigenvalues", "items": [{"type": "equation", "content": "Av = \\lambda v"}]}
    ]


def test_create_accepts_item_type_outside_enum(monkeypatch):
    client = create_client(monkeypatch, FakeStore())

    response = client.post(
        "/api/cheat-sheets",
        headers={"X-User-ID": "anon-1"},
        json={"title": "", "sections": [{"title": "S", "items": [{"type": "example", "content": "x"}]}]},
    )

    assert response.status_code == 201


def test_get_and_update_are_scoped_to_owner(monkeypatch):
    store = FakeStore()
    client = create_client(monkeypatch, store)
    client.post(
        "/api/cheat-sheets",
        headers={"X-User-ID": "anon-1"},
        json={"title": "Mine", "sections": []},
    )

    assert client.get(f"/api/cheat-sheets/{SHEET_ID}", headers={"X-User-ID": "anon-1"}).status_code == 200
    assert client.get(f"/api/cheat-sheets/{SHEET_ID}", headers={"X-User-ID": "anon-2"}).status_code == 404

    other = client.put(
        f"/api/cheat-sheets/{SHEET_ID}",
        headers={"X-User-ID": "anon-2"},
        json={"title": "Hijacked", "sections": []},
    )
    assert other.status_code == 404
    assert store.sheets[SHEET_ID]["title"] == "Mine"

    mine = client.put(
        f"/api/cheat-sheets/{SHEET_ID}",
        headers={"X-User-ID": "anon-1"},
        json={"title": "Renamed", "sections": []},
    )
    assert mine.status_code == 200
    assert mine.json()["title"] == "Renamed"


def test_invalid_sheet_id_is_rejected(monkeypatch):
    client = create_client(monkeypatch, FakeStore())

    response = client.get("/api/cheat-sheets/not-a-uuid", headers={"X-User-ID": "anon-1"})

    assert response.status_code == 422


def test_returns_503_when_supabase_not_configured(monkeypatch):
    client = create_client(monkeypatch, None)

    response = client.post(
        "/api/cheat-sheets",
        headers={"X-User-ID": "anon-1"},
        json={"title": "x", "sections": []},
    )

    assert response.status_code == 503
