#!/usr/bin/env python3
"""第 8 点 · 8-1 数据迁移：把旧数据归入每个用户的默认课程「Uncategorized」。

对 Supabase users 表里的每个用户（含 Phase 2 之前的匿名用户行）：
  1. 建默认课程（已存在则复用）
  2. 没有 course_id 的 cheat_sheets / ingest_batches → 默认课程
  3. Qdrant 中该用户（metadata.user_id = clerk_id / anon_id）没有 metadata.course_id 的 chunk → 默认课程

可重复执行；--dry-run 只统计不写入。前提：已执行 migrations/8-1_courses_and_versions.sql 第 1 步。

Usage (from backend/, e.g. inside the cheat-backend container):
    python -m scripts.migrate_courses --dry-run
    python -m scripts.migrate_courses
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infrastructure.db.supabase_store import get_supabase_store  # noqa: E402
from app.infrastructure.rag.qdrant_store import get_qdrant_store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写入")
    args = parser.parse_args()

    store = get_supabase_store()
    if store is None:
        print("SUPABASE_URL / SUPABASE_SECRET_KEY 未配置", file=sys.stderr)
        return 1
    vectors = get_qdrant_store()

    totals = {"users": 0, "cheat_sheets": 0, "ingest_batches": 0, "chunks": 0}
    for user in store.list_users():
        totals["users"] += 1
        qdrant_ids = [i for i in (user.get("clerk_id"), user.get("anon_id")) if i]
        if args.dry_run:
            orphans = {
                table: len(
                    store.client.table(table)
                    .select("id")
                    .eq("user_id", user["id"])
                    .is_("course_id", "null")
                    .execute()
                    .data
                )
                for table in ("cheat_sheets", "ingest_batches")
            }
            chunks = sum(vectors._count(vectors._missing_course_filter(q)) for q in qdrant_ids)
            course_label = "(dry run)"
        else:
            course = store.get_or_create_default_course(user["id"])
            orphans = store.assign_orphans_to_course(user["id"], course["id"])
            chunks = sum(vectors.assign_missing_course(q, course["id"]) for q in qdrant_ids)
            course_label = course["id"]

        totals["cheat_sheets"] += orphans["cheat_sheets"]
        totals["ingest_batches"] += orphans["ingest_batches"]
        totals["chunks"] += chunks
        if any(orphans.values()) or chunks:
            print(
                f"user {user['id']} ({', '.join(qdrant_ids) or 'no identity'}) → {course_label}: "
                f"sheets={orphans['cheat_sheets']} batches={orphans['ingest_batches']} chunks={chunks}"
            )

    verb = "would move" if args.dry_run else "moved"
    print(
        f"\n{totals['users']} users; {verb} {totals['cheat_sheets']} cheat sheets, "
        f"{totals['ingest_batches']} ingest batches, {totals['chunks']} chunks"
    )
    if not args.dry_run:
        left = {
            table: len(store.client.table(table).select("id").is_("course_id", "null").execute().data)
            for table in ("cheat_sheets", "ingest_batches")
        }
        print(f"remaining without course: {left}  (both 0 → run step 2 of the SQL migration)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
