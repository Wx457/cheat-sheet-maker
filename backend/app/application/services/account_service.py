from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, TypedDict

from app.infrastructure.db.supabase_store import SupabaseStore, get_supabase_store
from app.infrastructure.rag.qdrant_store import QdrantVectorStore, get_qdrant_store

logger = logging.getLogger(__name__)


class LinkResult(TypedDict):
    status: str
    chunks_moved: int


@dataclass
class AccountService:
    """
    Application Layer: 账号编排（Phase 2）。

    Clerk 接入前，插件用本地生成的匿名 anon_id 隔离数据（Qdrant payload metadata.user_id、
    Supabase users.anon_id）。用户首次登录后，插件调用一次 link_anon_data，把这些数据并入
    Clerk 用户，历史小抄与知识库得以保留。
    """

    vectors: QdrantVectorStore
    db: Optional[SupabaseStore] = None

    @classmethod
    def default(cls) -> "AccountService":
        return cls(vectors=get_qdrant_store(), db=get_supabase_store())

    async def link_anon_data(self, anon_id: str, clerk_id: str) -> LinkResult:
        """Supabase 先判定归属：匿名行已被其他 Clerk 用户认领（conflict）时不迁移 Qdrant chunk。

        第 8 点：匿名课程并入目标用户同名 / 默认课程时，chunk 的 course_id 跟着改写；
        没有课程的旧 chunk 归入目标用户的默认课程，否则按课程检索时就看不到它们。
        """
        status, remap = "not_found", {}
        if self.db is not None:
            status, remap = await asyncio.to_thread(self.db.link_anon_user, anon_id, clerk_id)
        if status == "conflict":
            return {"status": status, "chunks_moved": 0}

        # Qdrant 迁移后 anon_id 下不再有 chunk，重复调用 / 他人再认领只会迁移 0 条
        moved = await asyncio.to_thread(self.vectors.reassign_user, anon_id, clerk_id)
        for from_course, to_course in remap.items():
            await asyncio.to_thread(self.vectors.remap_course, clerk_id, from_course, to_course)
        if moved and self.db is not None:
            db_user_id = await asyncio.to_thread(self.db.get_or_create_user_id, clerk_id)
            default = await asyncio.to_thread(self.db.get_or_create_default_course, db_user_id)
            await asyncio.to_thread(self.vectors.assign_missing_course, clerk_id, default["id"])
        logger.info("Linked anon user: status=%s chunks_moved=%d", status, moved)
        return {"status": status, "chunks_moved": moved}
