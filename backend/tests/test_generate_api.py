from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import generate as generate_api
from app.schemas import ExamType, OutlineResponse


class DummyService:
    def __init__(self):
        self.calls = []

    async def generate_outline(self, **kwargs):
        self.calls.append(kwargs)
        return OutlineResponse(topics=[{"title": "Eigenvalues", "relevance_score": 0.9}])


def create_client(monkeypatch):
    service = DummyService()
    monkeypatch.setattr(generate_api.CheatSheetService, "default", classmethod(lambda cls: service))
    app = FastAPI()
    app.include_router(generate_api.router)
    return TestClient(app), service


def test_generate_outline_returns_topics_with_user_id_and_batch(monkeypatch):
    client, service = create_client(monkeypatch)

    response = client.post(
        "/api/outline",
        headers={"X-User-ID": "user-42"},
        json={
            "raw_text": "linear algebra syllabus",
            "user_context": "Math 101",
            "exam_type": "midterm",
            "ingest_batch_id": "batch-1",
        },
    )

    assert response.status_code == 200
    assert response.json()["topics"][0]["title"] == "Eigenvalues"
    assert service.calls == [
        {
            "text": "linear algebra syllabus",
            "context": "Math 101",
            "exam_type": ExamType.midterm,
            "user_id": "user-42",
            "ingest_batch_id": "batch-1",
        }
    ]


def test_generate_outline_falls_back_to_user_context_as_query(monkeypatch):
    client, service = create_client(monkeypatch)

    response = client.post(
        "/api/outline",
        headers={"X-User-ID": "user-42"},
        json={"user_context": "Math 101"},
    )

    assert response.status_code == 200
    assert service.calls[0]["text"] == "Math 101"
