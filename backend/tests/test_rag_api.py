import io

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.rag import router as rag_router


def create_client():
    app = FastAPI()
    app.include_router(rag_router, prefix="/api/rag")
    return TestClient(app)


def test_ingest_file_rejects_non_pdf_upload():
    client = create_client()

    response = client.post(
        "/api/rag/ingest/file",
        headers={"X-User-ID": "user-1"},
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "仅支持 PDF 文件格式"


def test_ingest_text_requires_user_header():
    client = create_client()

    response = client.post(
        "/api/rag/ingest",
        json={"text": "hello", "source": "demo"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["header", "X-User-ID"]
