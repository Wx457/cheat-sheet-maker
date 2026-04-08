from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import task as task_api


class DummyStorageClient:
    def get_presigned_url(self, file_key: str):
        return f"https://example.com/download/{file_key}"


class CompletedJob:
    def __init__(self, job_id: str, redis):
        self.job_id = job_id
        self.redis = redis

    async def status(self):
        return "complete"

    async def result(self):
        return {"file_key": "abc/report.pdf", "status": "completed"}


class NotFoundJob:
    def __init__(self, job_id: str, redis):
        self.job_id = job_id
        self.redis = redis

    async def status(self):
        return "not_found"


def create_client():
    app = FastAPI()
    app.include_router(task_api.router)
    app.state.arq_pool = object()
    return TestClient(app)


def test_task_status_returns_presigned_url_for_completed_file(monkeypatch):
    monkeypatch.setattr(task_api, "Job", CompletedJob)
    monkeypatch.setattr(task_api, "get_minio_client", lambda: DummyStorageClient())
    client = create_client()

    response = client.get("/api/task/task-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["download_url"] == "https://example.com/download/abc/report.pdf"
    assert payload["result"]["download_url"] == "https://example.com/download/abc/report.pdf"


def test_task_status_returns_404_for_missing_job(monkeypatch):
    monkeypatch.setattr(task_api, "Job", NotFoundJob)
    client = create_client()

    response = client.get("/api/task/missing-task")

    assert response.status_code == 404
    assert response.json()["detail"] == "任务不存在: missing-task"
