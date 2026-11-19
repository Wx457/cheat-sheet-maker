"""
Application Layer: 课程（UPGRADE_PLAN 第 8 点 · 8-1）。

课程存在 Supabase（courses 表）；知识库按 Qdrant payload metadata.course_id 分课程。
- 请求带 course_id：校验课程属于当前用户，不属于 → CourseNotFoundError（API 层转 404）
- 请求不带 course_id（旧插件 / webapp Dev 面板）：归入该用户的默认课程「Uncategorized」
- 未配置 Supabase（本地开发）：没有课程概念，course 解析为 None，检索覆盖该用户全部 chunk
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.infrastructure.db.supabase_store import SupabaseStore, get_supabase_store
from app.infrastructure.rag.qdrant_store import QdrantVectorStore, get_qdrant_store

logger = logging.getLogger(__name__)


class CourseNotFoundError(Exception):
    """课程不存在或不属于当前用户（不区分两者，避免探测他人课程 id）。"""


async def resolve_course(
    clerk_id: str, course_id: Optional[str], use_default: bool = True
) -> Optional[Dict[str, Any]]:
    """把请求里的 course_id 解析为当前用户的课程行（含 id / name / …）。

    use_default=False 时，未给 course_id 返回 None（调用方据此按「该用户全部数据」处理，
    如插件旧版的 chunk 计数 / 清空知识库）。
    """
    store = get_supabase_store()
    if store is None:
        return None
    db_user_id = await asyncio.to_thread(store.get_or_create_user_id, clerk_id)
    if course_id:
        course = await asyncio.to_thread(store.get_course, db_user_id, course_id)
        if course is None:
            raise CourseNotFoundError(course_id)
        return course
    if not use_default:
        return None
    return await asyncio.to_thread(store.get_or_create_default_course, db_user_id)


async def resolve_course_id(
    clerk_id: str, course_id: Optional[str], use_default: bool = True
) -> Optional[str]:
    course = await resolve_course(clerk_id, course_id, use_default)
    return course["id"] if course else None


@dataclass
class CourseService:
    """课程的增删改查；删除课程时连同 Qdrant 中该课程的 chunk 一起删。"""

    db: SupabaseStore
    vectors: Optional[QdrantVectorStore] = None

    @classmethod
    def default(cls) -> Optional["CourseService"]:
        store = get_supabase_store()
        if store is None:
            return None
        return cls(db=store, vectors=None)

    def _vectors(self) -> QdrantVectorStore:
        # Qdrant 客户端只在删除课程时需要，懒加载避免列表 / 改名请求连带初始化 Qdrant
        if self.vectors is None:
            self.vectors = get_qdrant_store()
        return self.vectors

    async def _db_user_id(self, clerk_id: str) -> str:
        return await asyncio.to_thread(self.db.get_or_create_user_id, clerk_id)

    async def list_courses(self, clerk_id: str) -> list:
        user_id = await self._db_user_id(clerk_id)
        # 默认课程总是存在：插件的课程下拉永远有可选项
        await asyncio.to_thread(self.db.get_or_create_default_course, user_id)
        return await asyncio.to_thread(self.db.list_courses, user_id)

    async def create_course(
        self,
        clerk_id: str,
        name: str,
        archetype: Optional[str],
        academic_level: Optional[str],
    ) -> Dict[str, Any]:
        user_id = await self._db_user_id(clerk_id)
        row = await asyncio.to_thread(
            self.db.create_course, user_id, name, archetype, academic_level
        )
        return {**row, "sheet_count": 0}

    async def get_course_detail(self, clerk_id: str, course_id: str) -> Dict[str, Any]:
        user_id = await self._db_user_id(clerk_id)
        course = await asyncio.to_thread(self.db.get_course, user_id, course_id)
        if course is None:
            raise CourseNotFoundError(course_id)
        sheets = await asyncio.to_thread(self.db.list_course_sheets, user_id, course_id)
        return {"course": {**course, "sheet_count": len(sheets)}, "sheets": sheets}

    async def update_course(
        self, clerk_id: str, course_id: str, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        user_id = await self._db_user_id(clerk_id)
        if not fields:
            course = await asyncio.to_thread(self.db.get_course, user_id, course_id)
        else:
            course = await asyncio.to_thread(self.db.update_course, user_id, course_id, fields)
        if course is None:
            raise CourseNotFoundError(course_id)
        return course

    async def delete_course(self, clerk_id: str, course_id: str) -> Dict[str, int]:
        """先确认归属，再删 Qdrant chunk，最后删 Supabase 课程（小抄 / ingest 记录级联删除）。"""
        user_id = await self._db_user_id(clerk_id)
        course = await asyncio.to_thread(self.db.get_course, user_id, course_id)
        if course is None:
            raise CourseNotFoundError(course_id)
        sheets = await asyncio.to_thread(self.db.list_course_sheets, user_id, course_id)
        deleted_chunks = await asyncio.to_thread(
            self._vectors().delete_user_data, clerk_id, course_id
        )
        await asyncio.to_thread(self.db.delete_course, user_id, course_id)
        logger.info(
            "Deleted course %s: sheets=%d chunks=%d", course_id, len(sheets), deleted_chunks
        )
        return {"deleted_sheets": len(sheets), "deleted_chunks": int(deleted_chunks)}
