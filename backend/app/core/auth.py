"""Clerk 鉴权（Phase 2 / UPGRADE_PLAN 2-4）。

插件（后台 service worker 里的 Clerk 客户端）和 webapp（@clerk/nextjs）都以
`Authorization: Bearer <session token>` 调用后端。这里验签并取出 Clerk user id（`sub`），
作为所有数据隔离的用户标识：Qdrant payload `metadata.user_id`、Supabase `users.clerk_id`。

用法：
    async def endpoint(user_id: CurrentUserId): ...

- 未配置 CLERK_SECRET_KEY / CLERK_JWT_KEY → 503（不降级为匿名，避免生产漏配时数据裸奔）
- token 缺失 / 过期 / 签名不对 / azp 不在白名单 → 401
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Annotated

from clerk_backend_api.security import authenticate_request_async
from clerk_backend_api.security.types import AuthenticateRequestOptions
from fastapi import Depends, HTTPException, Request

from app.core.config import settings

logger = logging.getLogger(__name__)


def _unverified_claims(request: Request) -> dict:
    """仅用于日志：不验签地解出 token 的 azp / iat / nbf / exp，帮助定位 401 原因。"""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return {"token": "missing"}
    try:
        payload = auth.split(" ", 1)[1].split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except Exception:  # noqa: BLE001 - 日志辅助，解析失败不影响鉴权结果
        return {"token": "unparseable"}
    now = int(time.time())
    return {
        "azp": claims.get("azp"),
        "sid": str(claims.get("sid", ""))[-6:],
        "iat-now": (claims["iat"] - now) if "iat" in claims else None,
        "nbf-now": (claims["nbf"] - now) if "nbf" in claims else None,
        "exp-now": (claims["exp"] - now) if "exp" in claims else None,
    }


async def get_current_user_id(request: Request) -> str:
    """验证 Clerk session token，返回 Clerk user id（`user_...`）。"""
    if not settings.CLERK_SECRET_KEY and not settings.CLERK_JWT_KEY:
        raise HTTPException(
            status_code=503,
            detail="鉴权未配置（缺少 CLERK_SECRET_KEY）",
        )

    state = await authenticate_request_async(
        request,
        AuthenticateRequestOptions(
            secret_key=settings.CLERK_SECRET_KEY or None,
            jwt_key=settings.CLERK_JWT_KEY or None,
            authorized_parties=settings.CLERK_AUTHORIZED_PARTIES or None,
            accepts_token=["session_token"],
        ),
    )
    user_id = (state.payload or {}).get("sub") if state.is_signed_in else None
    if not user_id:
        logger.warning(
            "auth rejected %s %s: reason=%s message=%s claims=%s",
            request.method, request.url.path, state.reason, state.message, _unverified_claims(request),
        )
        raise HTTPException(
            status_code=401,
            detail=f"未登录或登录已失效: {state.message or 'invalid session token'}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id


CurrentUserId = Annotated[str, Depends(get_current_user_id)]


async def require_admin(user_id: CurrentUserId) -> str:
    """仅 ADMIN_USER_IDS 中的用户可调用（全局破坏性操作）。"""
    if user_id not in settings.ADMIN_USER_IDS:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user_id
