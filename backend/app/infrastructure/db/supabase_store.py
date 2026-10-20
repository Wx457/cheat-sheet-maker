"""Supabase (PostgreSQL) store — users / cheat_sheets / ingest_batches (Phase 3).

Access model (see UPGRADE_PLAN 3-2): the three tables have RLS enabled with no
policies, so only this backend — using SUPABASE_SECRET_KEY, which bypasses RLS —
can read or write them. Because RLS is bypassed, every query here MUST filter by
the owning user_id; never expose a method that skips that filter.

All methods are synchronous (supabase-py sync client); call them from async code
via asyncio.to_thread.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

from app.core.config import settings

logger = logging.getLogger(__name__)


class SupabaseStore:
    """Infra: Supabase 读写封装。"""

    def __init__(self, client: Client) -> None:
        self.client = client

    # ── users ────────────────────────────────────────────────────────────────

    def get_or_create_user_id(self, anon_id: str) -> str:
        """插件生成的 X-User-ID（anon_id）→ users.id，不存在则创建。

        upsert + on_conflict 保证并发请求下同一 anon_id 只会有一行。
        """
        rows = (
            self.client.table("users")
            .upsert({"anon_id": anon_id}, on_conflict="anon_id")
            .execute()
            .data
        )
        return rows[0]["id"]

    # ── cheat_sheets ─────────────────────────────────────────────────────────

    def create_cheat_sheet(
        self, user_id: str, title: str, sections: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        rows = (
            self.client.table("cheat_sheets")
            .insert({"user_id": user_id, "title": title, "sections": sections})
            .execute()
            .data
        )
        return rows[0]

    def update_cheat_sheet(
        self, user_id: str, sheet_id: str, title: str, sections: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """返回更新后的行；sheet 不存在或不属于该用户时返回 None。"""
        rows = (
            self.client.table("cheat_sheets")
            .update({"title": title, "sections": sections})
            .eq("id", sheet_id)
            .eq("user_id", user_id)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def get_cheat_sheet(self, user_id: str, sheet_id: str) -> Optional[Dict[str, Any]]:
        """sheet 不存在或不属于该用户时返回 None。"""
        rows = (
            self.client.table("cheat_sheets")
            .select("id, title, sections, created_at, updated_at")
            .eq("id", sheet_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
            .data
        )
        return rows[0] if rows else None

    # ── ingest_batches ───────────────────────────────────────────────────────

    def record_ingest_batch(
        self,
        user_id: str,
        ingest_batch_id: str,
        source: Optional[str],
        chunk_count: int,
        truncated: bool,
    ) -> None:
        self.client.table("ingest_batches").insert(
            {
                "user_id": user_id,
                "ingest_batch_id": ingest_batch_id,
                "source": source,
                "chunk_count": chunk_count,
                "truncated": truncated,
            }
        ).execute()

    def delete_user_ingest_batches(self, user_id: str) -> None:
        self.client.table("ingest_batches").delete().eq("user_id", user_id).execute()


_store: Optional[SupabaseStore] = None


def get_supabase_store() -> Optional[SupabaseStore]:
    """返回单例；未配置 SUPABASE_URL / SUPABASE_SECRET_KEY 时返回 None（本地开发可不接 Supabase）。"""
    global _store
    if _store is None:
        if not settings.SUPABASE_URL or not settings.SUPABASE_SECRET_KEY:
            return None
        _store = SupabaseStore(create_client(settings.SUPABASE_URL, settings.SUPABASE_SECRET_KEY))
    return _store
