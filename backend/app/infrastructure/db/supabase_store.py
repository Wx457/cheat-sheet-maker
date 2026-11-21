"""Supabase (PostgreSQL) store — users / courses / cheat_sheets / ingest_batches.

Access model (see UPGRADE_PLAN 3-2): all tables have RLS enabled with no
policies, so only this backend — using SUPABASE_SECRET_KEY, which bypasses RLS —
can read or write them. Because RLS is bypassed, every query here MUST filter by
the owning user_id; never expose a method that skips that filter.
(Exception: `list_users`, used only by the offline migration script.)

All methods are synchronous (supabase-py sync client); call them from async code
via asyncio.to_thread.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from postgrest.exceptions import APIError
from supabase import Client, create_client

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_COURSE_NAME = "Uncategorized"

_COURSE_COLUMNS = "id, name, archetype, academic_level, is_default, created_at, updated_at"
_SHEET_COLUMNS = (
    "id, title, sections, course_id, version, origin, parent_sheet_id, generation_params, "
    "created_at, updated_at"
)
_SHEET_SUMMARY_COLUMNS = "id, title, version, origin, parent_sheet_id, created_at, updated_at"


class DuplicateCourseNameError(Exception):
    """同一用户下课程名（不区分大小写）已存在。"""


def _is_unique_violation(exc: Exception) -> bool:
    return isinstance(exc, APIError) and getattr(exc, "code", None) == "23505"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupabaseStore:
    """Infra: Supabase 读写封装。"""

    def __init__(self, client: Client) -> None:
        self.client = client

    # ── users ────────────────────────────────────────────────────────────────

    def get_or_create_user_id(self, clerk_id: str) -> str:
        """Clerk user id（session token 的 sub）→ users.id，不存在则创建。

        upsert + on_conflict 保证并发请求下同一 clerk_id 只会有一行。
        """
        rows = (
            self.client.table("users")
            .upsert({"clerk_id": clerk_id}, on_conflict="clerk_id")
            .execute()
            .data
        )
        return rows[0]["id"]

    def list_users(self) -> List[Dict[str, Any]]:
        """仅供离线迁移脚本使用（scripts/migrate_courses.py）：列出所有用户行。"""
        return self.client.table("users").select("id, clerk_id, anon_id").execute().data

    def link_anon_user(self, anon_id: str, clerk_id: str) -> Tuple[str, Dict[str, str]]:
        """把 Phase 2 之前的匿名用户（插件生成的 anon_id）并入 Clerk 用户，只能认领一次。

        返回 (status, course_remap)：
          - "linked"         Clerk 用户还没有行：直接在匿名行上回填 clerk_id
          - "merged"         Clerk 用户已有行：课程 / 小抄 / ingest 记录迁过去，删除匿名行
          - "already_linked" 匿名行已属于该 Clerk 用户（重复调用）
          - "conflict"       匿名行已被其他 Clerk 用户认领
          - "not_found"      没有该 anon_id 的行（从未保存过数据，或已合并删除）
        course_remap：合并时被并入目标用户同名课程（或默认课程）的匿名课程 {旧 course_id: 新 course_id}，
        调用方据此改写 Qdrant chunk 的 metadata.course_id。
        """
        users = self.client.table("users")
        anon_rows = users.select("id, clerk_id").eq("anon_id", anon_id).limit(1).execute().data
        if not anon_rows:
            return "not_found", {}
        anon = anon_rows[0]
        if anon["clerk_id"] == clerk_id:
            return "already_linked", {}
        if anon["clerk_id"]:
            return "conflict", {}

        clerk_rows = users.select("id").eq("clerk_id", clerk_id).limit(1).execute().data
        if not clerk_rows:
            # is_("clerk_id", "null")：并发认领时只有一个请求能写入
            claimed = (
                users.update({"clerk_id": clerk_id})
                .eq("id", anon["id"])
                .is_("clerk_id", "null")
                .execute()
                .data
            )
            return ("linked" if claimed else "conflict"), {}

        target_id = clerk_rows[0]["id"]
        remap = self._merge_courses(anon["id"], target_id)
        for table in ("cheat_sheets", "ingest_batches"):
            self.client.table(table).update({"user_id": target_id}).eq(
                "user_id", anon["id"]
            ).execute()
        users.delete().eq("id", anon["id"]).is_("clerk_id", "null").execute()
        return "merged", remap

    def _merge_courses(self, from_user_id: str, to_user_id: str) -> Dict[str, str]:
        """匿名用户的课程并入目标用户：默认课程并入默认课程、同名课程合并，其余整门转移。"""
        courses = self.client.table("courses")
        source = courses.select("id, name, is_default").eq("user_id", from_user_id).execute().data
        if not source:
            return {}
        target = courses.select("id, name, is_default").eq("user_id", to_user_id).execute().data
        target_default = next((c["id"] for c in target if c["is_default"]), None)
        target_by_name = {c["name"].lower(): c["id"] for c in target}

        remap: Dict[str, str] = {}
        for course in source:
            match = (target_default if course["is_default"] else None) or target_by_name.get(
                course["name"].lower()
            )
            if match:
                for table in ("cheat_sheets", "ingest_batches"):
                    self.client.table(table).update({"course_id": match}).eq(
                        "course_id", course["id"]
                    ).execute()
                courses.delete().eq("id", course["id"]).execute()
                remap[course["id"]] = match
            else:
                courses.update({"user_id": to_user_id}).eq("id", course["id"]).execute()
                if course["is_default"]:
                    target_default = course["id"]
                target_by_name[course["name"].lower()] = course["id"]
        return remap

    # ── courses ──────────────────────────────────────────────────────────────

    def get_or_create_default_course(self, user_id: str) -> Dict[str, Any]:
        """每个用户一门默认课程（Uncategorized）：未指定课程时的兜底，也是旧数据的归属。"""
        courses = self.client.table("courses")
        rows = (
            courses.select(_COURSE_COLUMNS)
            .eq("user_id", user_id)
            .eq("is_default", True)
            .limit(1)
            .execute()
            .data
        )
        if rows:
            return rows[0]
        name = DEFAULT_COURSE_NAME
        for attempt in range(3):
            try:
                return (
                    courses.insert({"user_id": user_id, "name": name, "is_default": True})
                    .execute()
                    .data[0]
                )
            except APIError as exc:
                if not _is_unique_violation(exc):
                    raise
                # 并发请求已建好默认课程 → 重读；或用户自建了同名课程 → 换个名字
                rows = (
                    courses.select(_COURSE_COLUMNS)
                    .eq("user_id", user_id)
                    .eq("is_default", True)
                    .limit(1)
                    .execute()
                    .data
                )
                if rows:
                    return rows[0]
                name = f"{DEFAULT_COURSE_NAME} ({attempt + 2})"
        raise RuntimeError(f"could not create default course for user {user_id}")

    def list_courses(self, user_id: str) -> List[Dict[str, Any]]:
        """按最近使用倒序；sheet_count 来自 PostgREST 嵌入计数。"""
        rows = (
            self.client.table("courses")
            .select(f"{_COURSE_COLUMNS}, cheat_sheets(count)")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .execute()
            .data
        )
        for row in rows:
            embedded = row.pop("cheat_sheets", None) or [{}]
            row["sheet_count"] = int(embedded[0].get("count", 0))
        return rows

    def get_course(self, user_id: str, course_id: str) -> Optional[Dict[str, Any]]:
        """课程不存在或不属于该用户时返回 None。"""
        rows = (
            self.client.table("courses")
            .select(_COURSE_COLUMNS)
            .eq("id", course_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def create_course(
        self,
        user_id: str,
        name: str,
        archetype: Optional[str] = None,
        academic_level: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            return (
                self.client.table("courses")
                .insert(
                    {
                        "user_id": user_id,
                        "name": name,
                        "archetype": archetype,
                        "academic_level": academic_level,
                    }
                )
                .execute()
                .data[0]
            )
        except APIError as exc:
            if _is_unique_violation(exc):
                raise DuplicateCourseNameError(name) from exc
            raise

    def update_course(
        self, user_id: str, course_id: str, fields: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """只更新给出的字段（name / archetype / academic_level）。不存在或不属于该用户返回 None。"""
        try:
            rows = (
                self.client.table("courses")
                .update(fields)
                .eq("id", course_id)
                .eq("user_id", user_id)
                .execute()
                .data
            )
        except APIError as exc:
            if _is_unique_violation(exc):
                raise DuplicateCourseNameError(fields.get("name", "")) from exc
            raise
        return rows[0] if rows else None

    def touch_course(self, user_id: str, course_id: str) -> None:
        """刷新 updated_at（moddatetime 触发器写入 now()），让课程在列表里排到前面。"""
        self.client.table("courses").update({"updated_at": _now_iso()}).eq("id", course_id).eq(
            "user_id", user_id
        ).execute()

    def delete_course(self, user_id: str, course_id: str) -> bool:
        """连同小抄、ingest 记录一起删除（外键 on delete cascade）。返回是否删到了。"""
        rows = (
            self.client.table("courses")
            .delete()
            .eq("id", course_id)
            .eq("user_id", user_id)
            .execute()
            .data
        )
        return bool(rows)

    def list_course_sheets(self, user_id: str, course_id: str) -> List[Dict[str, Any]]:
        """课程内所有版本（不含 sections），按创建时间倒序。"""
        return (
            self.client.table("cheat_sheets")
            .select(_SHEET_SUMMARY_COLUMNS)
            .eq("user_id", user_id)
            .eq("course_id", course_id)
            .order("created_at", desc=True)
            .execute()
            .data
        )

    def assign_orphans_to_course(self, user_id: str, course_id: str) -> Dict[str, int]:
        """把该用户没有课程的小抄 / ingest 记录归入 course_id（迁移脚本用，可重复执行）。"""
        moved: Dict[str, int] = {}
        for table in ("cheat_sheets", "ingest_batches"):
            rows = (
                self.client.table(table)
                .update({"course_id": course_id})
                .eq("user_id", user_id)
                .is_("course_id", "null")
                .execute()
                .data
            )
            moved[table] = len(rows)
        return moved

    # ── cheat_sheets ─────────────────────────────────────────────────────────

    def create_cheat_sheet(
        self,
        user_id: str,
        course_id: str,
        title: str,
        sections: List[Dict[str, Any]],
        generation_params: Optional[Dict[str, Any]] = None,
        origin: str = "generate",
        parent_sheet_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """新建一个版本（version = 课程内最大版本号 + 1）。

        去重：课程内最新版本与本次的生成参数、内容都相同（同一请求命中生成缓存后再次打开编辑器）时，
        直接返回那一版，不再新建。
        """
        latest = (
            self.client.table("cheat_sheets")
            .select("id, version, title, sections, generation_params")
            .eq("user_id", user_id)
            .eq("course_id", course_id)
            .order("version", desc=True)
            .limit(1)
            .execute()
            .data
        )
        if latest:
            prev = latest[0]
            if (
                generation_params is not None
                and prev.get("generation_params") == generation_params
                and prev.get("sections") == sections
                and prev.get("title") == title
            ):
                full = self.get_cheat_sheet(user_id, prev["id"])
                if full is not None:
                    return full

        version = (latest[0]["version"] + 1) if latest else 1
        rows = (
            self.client.table("cheat_sheets")
            .insert(
                {
                    "user_id": user_id,
                    "course_id": course_id,
                    "title": title,
                    "sections": sections,
                    "version": version,
                    "generation_params": generation_params,
                    "origin": origin,
                    "parent_sheet_id": parent_sheet_id,
                }
            )
            .execute()
            .data
        )
        self.touch_course(user_id, course_id)
        return rows[0]

    def update_cheat_sheet(
        self, user_id: str, sheet_id: str, title: str, sections: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """手动编辑：修改当前版本，不新建版本。sheet 不存在或不属于该用户时返回 None。"""
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
            .select(_SHEET_COLUMNS)
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
        course_id: Optional[str] = None,
    ) -> None:
        self.client.table("ingest_batches").insert(
            {
                "user_id": user_id,
                "course_id": course_id,
                "ingest_batch_id": ingest_batch_id,
                "source": source,
                "chunk_count": chunk_count,
                "truncated": truncated,
            }
        ).execute()
        if course_id:
            self.touch_course(user_id, course_id)

    def delete_user_ingest_batches(self, user_id: str, course_id: Optional[str] = None) -> None:
        query = self.client.table("ingest_batches").delete().eq("user_id", user_id)
        if course_id:
            query = query.eq("course_id", course_id)
        query.execute()


_store: Optional[SupabaseStore] = None


def get_supabase_store() -> Optional[SupabaseStore]:
    """返回单例；未配置 SUPABASE_URL / SUPABASE_SECRET_KEY 时返回 None（本地开发可不接 Supabase）。"""
    global _store
    if _store is None:
        if not settings.SUPABASE_URL or not settings.SUPABASE_SECRET_KEY:
            return None
        _store = SupabaseStore(create_client(settings.SUPABASE_URL, settings.SUPABASE_SECRET_KEY))
    return _store
