"""
账号相关 API（Clerk，Phase 2 / UPGRADE_PLAN 2-4）

- POST /api/auth/link-anon   插件首次登录后调用一次：把匿名 anon_id 下的数据并入当前 Clerk 用户
"""

import traceback

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from app.application.services.account_service import AccountService
from app.core.auth import CurrentUserId
from app.infrastructure.cache.redis_cache import get_cheat_sheet_cache

router = APIRouter()


class LinkAnonRequest(BaseModel):
    anon_id: str = Field(..., min_length=1, max_length=128)


class LinkAnonResponse(BaseModel):
    status: str
    chunks_moved: int


@router.post("/api/auth/link-anon", response_model=LinkAnonResponse)
async def link_anon(
    user_id: CurrentUserId,
    payload: LinkAnonRequest = Body(...),
) -> LinkAnonResponse:
    """status 见 SupabaseStore.link_anon_user；已被其他账号认领时返回 409。"""
    try:
        result = await AccountService.default().link_anon_data(payload.anon_id, user_id)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"关联匿名数据时发生错误: {str(e)}")
    if result["status"] == "conflict":
        raise HTTPException(status_code=409, detail="该匿名数据已关联到其他账号")
    if result["chunks_moved"] > 0:
        # 知识库多了迁移进来的 chunk → 该用户的生成结果缓存作废（Phase 5）
        await get_cheat_sheet_cache().invalidate_user(user_id)
    return LinkAnonResponse(**result)
