#!/usr/bin/env python3
"""One-shot migration: MongoDB Atlas Vector Search → Qdrant.

Usage (run from backend/ directory with the .env loaded):
    python scripts/migrate_mongo_to_qdrant.py

Reads MONGODB_URI / DB_NAME / COLLECTION_NAME from environment (or .env).
Reads QDRANT_HOST / QDRANT_PORT from environment (defaults: localhost / 6333).

Documents must have an 'embedding' field with 1536-dimensional vectors.
Documents with missing or wrong-dimension vectors are skipped and reported.
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

VECTOR_SIZE = 1536
COLLECTION = "cheat_sheet_chunks"
BATCH_SIZE = 100


def main() -> None:
    mongo_uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("DB_NAME", "cheat_sheet_db")
    coll_name = os.getenv("COLLECTION_NAME", "knowledge_base")
    qdrant_host = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))

    if not mongo_uri:
        print("❌  MONGODB_URI not set — aborting.")
        sys.exit(1)

    try:
        from pymongo import MongoClient
    except ImportError:
        print("❌  pymongo not installed.")
        sys.exit(1)

    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, PointStruct, VectorParams
        from uuid import uuid4
    except ImportError:
        print("❌  qdrant-client not installed.")
        sys.exit(1)

    # ── MongoDB ──────────────────────────────────────────────────────────────
    print(f"Connecting to MongoDB → {db_name}.{coll_name}")
    mongo = MongoClient(mongo_uri)
    src = mongo[db_name][coll_name]
    total = src.count_documents({})
    print(f"  Found {total} documents.")

    # ── Qdrant ───────────────────────────────────────────────────────────────
    print(f"Connecting to Qdrant → {qdrant_host}:{qdrant_port}")
    qdrant = QdrantClient(host=qdrant_host, port=qdrant_port)

    existing = {c.name for c in qdrant.get_collections().collections}
    if COLLECTION not in existing:
        qdrant.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        print(f"  Created collection '{COLLECTION}'.")
    else:
        existing_count = qdrant.count(collection_name=COLLECTION, exact=True).count
        print(f"  Collection '{COLLECTION}' already exists ({existing_count} points).")

    # ── Migration loop ────────────────────────────────────────────────────────
    batch: list[PointStruct] = []
    migrated = 0
    skipped = 0

    for doc in src.find({}, {"page_content": 1, "embedding": 1, "metadata": 1}):
        vec = doc.get("embedding")
        content = doc.get("page_content", "")
        metadata: dict = dict(doc.get("metadata") or {})

        if not vec or len(vec) != VECTOR_SIZE:
            skipped += 1
            continue

        # Convert datetime objects to ISO strings for Qdrant JSON payload
        if "created_at" in metadata and hasattr(metadata["created_at"], "isoformat"):
            metadata["created_at"] = metadata["created_at"].isoformat()

        batch.append(
            PointStruct(
                id=str(uuid4()),
                vector=vec,
                payload={"page_content": content, "metadata": metadata},
            )
        )

        if len(batch) >= BATCH_SIZE:
            qdrant.upsert(collection_name=COLLECTION, points=batch)
            migrated += len(batch)
            batch = []
            print(f"  Migrated {migrated}/{total}…")

    if batch:
        qdrant.upsert(collection_name=COLLECTION, points=batch)
        migrated += len(batch)

    print(
        f"\n✅  Done: {migrated} documents migrated, {skipped} skipped "
        f"(missing/wrong-dimension vector)."
    )
    mongo.close()
    qdrant.close()


if __name__ == "__main__":
    main()
