"""SSE 生成结果缓存（Phase 5 / UPGRADE_PLAN 第 5 点）。

同一用户、同一知识库、同一请求参数的生成结果直接重放，跳过 RAG 检索 + Gemini（5~30 秒）。

键设计：
- 结果键  `cheatsheet:v{VERSION}:{user_id}:{sha256(请求)}` → 完整 SSE 事件列表（JSON）
- 索引集合 `cheatsheet:v{VERSION}:idx:{user_id}` → 该用户所有结果键，知识库变化时整组删除

失效：
- 用户知识库变化（ingest / 删除 chunk / link-anon）→ invalidate_user()
- 管理员清空全部向量 → invalidate_all()
- 生成逻辑 / prompt 变化 → 改 CACHE_VERSION（旧键自然过期）

可用性：Redis 不可用时所有方法静默降级（get 返回 None、set / invalidate 什么都不做），只记警告，
绝不影响生成本身。
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

# 生成逻辑（prompt 模板、解析器、模型）变化时 +1，让旧结果全部失效
CACHE_VERSION = 1
_PREFIX = f"cheatsheet:v{CACHE_VERSION}"


def make_cache_key(user_id: str, request: dict[str, Any], model_name: str) -> str:
    """请求参数（已去掉 no_cache 等非内容字段）+ 模型名 → 确定性哈希。"""
    content = json.dumps(
        {"request": request, "model": model_name},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]
    return f"{_PREFIX}:{user_id}:{digest}"


def _index_key(user_id: str) -> str:
    return f"{_PREFIX}:idx:{user_id}"


class CheatSheetCache:
    def __init__(self, client: Optional[aioredis.Redis], ttl_seconds: int):
        self.client = client
        self.ttl = ttl_seconds

    @property
    def enabled(self) -> bool:
        return self.client is not None and self.ttl > 0

    async def get(self, key: str) -> Optional[list[str]]:
        """返回缓存的 SSE 事件 payload 列表（不含 "data: " 前缀和 [DONE]）。"""
        if not self.enabled:
            return None
        try:
            raw = await self.client.get(key)
        except Exception as exc:  # noqa: BLE001 - 缓存故障不能影响生成
            logger.warning("cache get failed (%s): %s", key, exc)
            return None
        if not raw:
            return None
        try:
            events = json.loads(raw)
        except ValueError:
            logger.warning("cache entry is not valid JSON, ignoring: %s", key)
            return None
        return events if isinstance(events, list) else None

    async def set(self, user_id: str, key: str, events: list[str]) -> None:
        if not self.enabled:
            return
        try:
            async with self.client.pipeline(transaction=True) as pipe:
                pipe.set(key, json.dumps(events, ensure_ascii=False), ex=self.ttl)
                pipe.sadd(_index_key(user_id), key)
                pipe.expire(_index_key(user_id), self.ttl)
                await pipe.execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache set failed (%s): %s", key, exc)

    async def invalidate_user(self, user_id: str) -> int:
        """删除该用户的全部缓存结果，返回删除的结果键数量。"""
        if self.client is None:
            return 0
        try:
            idx = _index_key(user_id)
            keys = await self.client.smembers(idx)
            if keys:
                await self.client.delete(*keys, idx)
            else:
                await self.client.delete(idx)
            return len(keys)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache invalidate failed (user=%s): %s", user_id, exc)
            return 0

    async def invalidate_all(self) -> int:
        """删除全部缓存（管理员清空所有用户向量时调用）。"""
        if self.client is None:
            return 0
        deleted = 0
        try:
            batch: list[Any] = []
            async for key in self.client.scan_iter(match=f"{_PREFIX}:*", count=500):
                batch.append(key)
                if len(batch) >= 500:
                    deleted += await self.client.delete(*batch)
                    batch = []
            if batch:
                deleted += await self.client.delete(*batch)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache invalidate_all failed: %s", exc)
        return deleted


_cache: Optional[CheatSheetCache] = None


def get_cheat_sheet_cache() -> CheatSheetCache:
    """进程内单例。Redis 连接是惰性的：这里不发网络请求，Redis 没起也能正常构造。"""
    global _cache
    if _cache is None:
        client = aioredis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD or None,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=2,
        )
        _cache = CheatSheetCache(client, settings.CHEATSHEET_CACHE_TTL_SECONDS)
    return _cache
