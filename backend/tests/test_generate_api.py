from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.generate import router as generate_router


class DummyJob:
    def __init__(self, job_id: str):
        self.job_id = job_id


class DummyArqPool:
    def __init__(self):
        self.calls = []

    async def enqueue_job(self, task_name: str, **kwargs):
        self.calls.append((task_name, kwargs))
        return DummyJob(job_id=f"{task_name}-123")


def create_client():
    app = FastAPI()
    app.include_router(generate_router)
    app.state.arq_pool = DummyArqPool()
    return TestClient(app), app.state.arq_pool


def test_generate_outline_enqueues_task_with_user_id_and_batch():
    client, pool = create_client()

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
    assert response.json()["task_id"] == "generate_outline_task-123"
    assert pool.calls == [
        (
            "generate_outline_task",
            {
                "raw_text": "linear algebra syllabus",
                "user_context": "Math 101",
                "exam_type": "midterm",
                "user_id": "user-42",
                "ingest_batch_id": "batch-1",
            },
        )
    ]


def test_generate_cheat_sheet_serializes_enums_and_topics_for_worker():
    client, pool = create_client()

    response = client.post(
        "/api/generate",
        headers={"X-User-ID": "user-99"},
        json={
            "syllabus": "Focus on gradients",
            "user_context": "ML course",
            "page_limit": "2_pages",
            "academic_level": "graduate",
            "selected_topics": [
                {"title": "Gradient Descent", "relevance_score": 0.95},
                {"title": "Backpropagation", "relevance_score": 0.9},
            ],
            "exam_type": "final",
            "archetype": "stem_theoretical",
        },
    )

    assert response.status_code == 200
    assert response.json()["task_id"] == "generate_cheat_sheet_task-123"

    task_name, task_kwargs = pool.calls[0]
    assert task_name == "generate_cheat_sheet_task"
    assert task_kwargs["page_limit"] == "2_pages"
    assert task_kwargs["academic_level"] == "graduate"
    assert task_kwargs["exam_type"] == "final"
    assert task_kwargs["archetype"] == "stem_theoretical"
    assert task_kwargs["user_id"] == "user-99"
    assert task_kwargs["selected_topics"] == [
        {"title": "Gradient Descent", "relevance_score": 0.95},
        {"title": "Backpropagation", "relevance_score": 0.9},
    ]
