"""Clerk 鉴权依赖、管理员接口、匿名数据关联（Phase 2）。"""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.api import rag as rag_api
from app.application.services.account_service import AccountService
from app.core.config import settings

from conftest import bearer


def create_client():
    app = FastAPI()
    app.include_router(rag_api.router, prefix="/api/rag")
    app.include_router(auth_api.router)
    return TestClient(app)


# ── get_current_user_id（真实 clerk-backend-api，不发网络请求的分支） ─────────


@pytest.mark.real_auth
def test_returns_503_when_clerk_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "CLERK_SECRET_KEY", "")
    monkeypatch.setattr(settings, "CLERK_JWT_KEY", "")

    response = create_client().get("/api/rag/chunks/count", headers=bearer("user-1"))

    assert response.status_code == 503


@pytest.mark.real_auth
def test_returns_401_without_token(monkeypatch):
    monkeypatch.setattr(settings, "CLERK_SECRET_KEY", "sk_test_dummy")

    response = create_client().get("/api/rag/chunks/count")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.real_auth
def test_returns_401_for_malformed_token(monkeypatch):
    monkeypatch.setattr(settings, "CLERK_SECRET_KEY", "sk_test_dummy")

    response = create_client().get(
        "/api/rag/chunks/count", headers={"Authorization": "Bearer not-a-jwt"}
    )

    assert response.status_code == 401


# ── POST /api/rag/clear：仅管理员 ─────────────────────────────────────────────


class FakeVectors:
    def __init__(self, chunks=None):
        self.chunks = dict(chunks or {})
        self.cleared = False

    def clear_vector_data(self):
        self.cleared = True
        return 7

    def reassign_user(self, from_user_id, to_user_id):
        moved = self.chunks.pop(from_user_id, 0)
        self.chunks[to_user_id] = self.chunks.get(to_user_id, 0) + moved
        return moved


def _patch_ingestion(monkeypatch, vectors):
    service = type("S", (), {"rag_service": vectors})()
    monkeypatch.setattr(rag_api.IngestionService, "default", classmethod(lambda cls: service))


def test_clear_all_forbidden_for_non_admin(monkeypatch):
    vectors = FakeVectors()
    _patch_ingestion(monkeypatch, vectors)
    monkeypatch.setattr(settings, "ADMIN_USER_IDS", ["user_admin"])

    response = create_client().post("/api/rag/clear", headers=bearer("user_regular"))

    assert response.status_code == 403
    assert vectors.cleared is False


def test_clear_all_forbidden_when_no_admins_configured(monkeypatch):
    vectors = FakeVectors()
    _patch_ingestion(monkeypatch, vectors)
    monkeypatch.setattr(settings, "ADMIN_USER_IDS", [])

    response = create_client().post("/api/rag/clear", headers=bearer("user_admin"))

    assert response.status_code == 403
    assert vectors.cleared is False


def test_clear_all_allowed_for_admin(monkeypatch):
    vectors = FakeVectors()
    _patch_ingestion(monkeypatch, vectors)
    monkeypatch.setattr(settings, "ADMIN_USER_IDS", ["user_admin"])

    response = create_client().post("/api/rag/clear", headers=bearer("user_admin"))

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 7
    assert vectors.cleared is True


# ── 匿名数据关联 ─────────────────────────────────────────────────────────────


class FakeDb:
    def __init__(self, status):
        self.status = status
        self.calls = []

    def link_anon_user(self, anon_id, clerk_id):
        self.calls.append((anon_id, clerk_id))
        return self.status


@pytest.mark.parametrize("status", ["linked", "merged", "already_linked", "not_found"])
def test_link_moves_chunks_unless_conflict(status):
    vectors = FakeVectors({"anon-1": 12})
    service = AccountService(vectors=vectors, db=FakeDb(status))

    result = asyncio.run(service.link_anon_data("anon-1", "user_a"))

    assert result == {"status": status, "chunks_moved": 12}
    assert vectors.chunks == {"user_a": 12}


def test_link_conflict_leaves_chunks_with_anon_id():
    vectors = FakeVectors({"anon-1": 12})
    service = AccountService(vectors=vectors, db=FakeDb("conflict"))

    result = asyncio.run(service.link_anon_data("anon-1", "user_b"))

    assert result == {"status": "conflict", "chunks_moved": 0}
    assert vectors.chunks == {"anon-1": 12}


def test_link_without_supabase_still_moves_chunks():
    vectors = FakeVectors({"anon-1": 3})
    service = AccountService(vectors=vectors, db=None)

    result = asyncio.run(service.link_anon_data("anon-1", "user_a"))

    assert result == {"status": "not_found", "chunks_moved": 3}


def _patch_account(monkeypatch, status, moved=0):
    calls = []

    class FakeAccount:
        async def link_anon_data(self, anon_id, clerk_id):
            calls.append((anon_id, clerk_id))
            return {"status": status, "chunks_moved": moved}

    monkeypatch.setattr(auth_api.AccountService, "default", classmethod(lambda cls: FakeAccount()))
    return calls


def test_link_endpoint_uses_clerk_user_from_token(monkeypatch):
    calls = _patch_account(monkeypatch, "linked", moved=5)

    response = create_client().post(
        "/api/auth/link-anon", json={"anon_id": "anon-1"}, headers=bearer("user_a")
    )

    assert response.status_code == 200
    assert response.json() == {"status": "linked", "chunks_moved": 5}
    assert calls == [("anon-1", "user_a")]


def test_link_endpoint_returns_409_on_conflict(monkeypatch):
    _patch_account(monkeypatch, "conflict")

    response = create_client().post(
        "/api/auth/link-anon", json={"anon_id": "anon-1"}, headers=bearer("user_b")
    )

    assert response.status_code == 409


def test_link_endpoint_requires_login(monkeypatch):
    calls = _patch_account(monkeypatch, "linked")

    response = create_client().post("/api/auth/link-anon", json={"anon_id": "anon-1"})

    assert response.status_code == 401
    assert calls == []
