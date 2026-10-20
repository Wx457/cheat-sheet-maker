import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from app.application.services.ingestion_service import IngestionService

INGEST_RESULT = {
    "chunks_count": 12,
    "ingest_batch_id": "batch-abc",
    "ingest_at": datetime(2026, 1, 1),
    "truncated": False,
    "original_chunks_count": 12,
}


def make_service(db):
    rag = MagicMock()
    rag.ingest_text = AsyncMock(return_value=INGEST_RESULT)
    rag.ingest_pdf = AsyncMock(return_value=INGEST_RESULT)
    rag.delete_user_data = MagicMock(return_value=12)
    return IngestionService(rag_service=rag, db=db)


def make_db():
    db = MagicMock()
    db.get_or_create_user_id.return_value = "db-user-1"
    return db


def test_process_text_records_ingest_batch():
    db = make_db()
    svc = make_service(db)

    result = asyncio.run(svc.process_text("hello", {"source": "lecture.html"}, "anon-1"))

    assert result == INGEST_RESULT
    db.get_or_create_user_id.assert_called_once_with("anon-1")
    db.record_ingest_batch.assert_called_once_with("db-user-1", "batch-abc", "lecture.html", 12, False)


def test_process_file_records_filename_as_source():
    db = make_db()
    svc = make_service(db)

    asyncio.run(svc.process_file(b"%PDF", "notes.pdf", "anon-1"))

    db.record_ingest_batch.assert_called_once_with("db-user-1", "batch-abc", "notes.pdf", 12, False)


def test_supabase_failure_does_not_fail_ingest():
    db = make_db()
    db.record_ingest_batch.side_effect = RuntimeError("supabase down")
    svc = make_service(db)

    result = asyncio.run(svc.process_text("hello", {"source": "s"}, "anon-1"))

    assert result == INGEST_RESULT


def test_ingest_works_without_supabase():
    svc = make_service(db=None)

    result = asyncio.run(svc.process_text("hello", {"source": "s"}, "anon-1"))

    assert result == INGEST_RESULT


def test_delete_user_data_also_deletes_ingest_batches():
    db = make_db()
    svc = make_service(db)

    deleted = asyncio.run(svc.delete_user_data("anon-1"))

    assert deleted == 12
    svc.rag_service.delete_user_data.assert_called_once_with("anon-1")
    db.delete_user_ingest_batches.assert_called_once_with("db-user-1")
