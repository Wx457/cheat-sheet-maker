"""
小抄持久化 API（Supabase，Phase 3 / UPGRADE_PLAN 3-4-b）

- POST /api/cheat-sheets         SSE onDone 时保存，返回含 id 的记录
- PUT  /api/cheat-sheets/{id}    用户编辑 / 拖拽 / 删除后覆盖保存（前端 debounce）
- GET  /api/cheat-sheets/{id}    刷新页面时恢复

身份来自 Clerk session token（app.core.auth），映射到 users.clerk_id → users.id。
secret key 绕过 RLS，归属校验由 SupabaseStore 按 user_id 过滤完成：
不属于当前用户的小抄一律返回 404（不区分"不存在"与"无权限"）。
"""

import asyncio
import traceback
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException

from app.core.auth import CurrentUserId
from app.infrastructure.db.supabase_store import SupabaseStore, get_supabase_store
from app.schemas import CheatSheetRecord, CheatSheetSaveRequest

router = APIRouter()


def _require_store() -> SupabaseStore:
    store = get_supabase_store()
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="小抄持久化未配置（缺少 SUPABASE_URL / SUPABASE_SECRET_KEY）",
        )
    return store


@router.post("/api/cheat-sheets", response_model=CheatSheetRecord, status_code=201)
async def create_cheat_sheet(
    user_id: CurrentUserId,
    payload: CheatSheetSaveRequest = Body(...),
) -> CheatSheetRecord:
    store = _require_store()
    try:
        db_user_id = await asyncio.to_thread(store.get_or_create_user_id, user_id)
        row = await asyncio.to_thread(
            store.create_cheat_sheet,
            db_user_id,
            payload.title,
            [s.model_dump() for s in payload.sections],
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"保存小抄时发生错误: {str(e)}")
    return CheatSheetRecord(**row)


@router.put("/api/cheat-sheets/{sheet_id}", response_model=CheatSheetRecord)
async def update_cheat_sheet(
    user_id: CurrentUserId,
    sheet_id: UUID,
    payload: CheatSheetSaveRequest = Body(...),
) -> CheatSheetRecord:
    store = _require_store()
    try:
        db_user_id = await asyncio.to_thread(store.get_or_create_user_id, user_id)
        row = await asyncio.to_thread(
            store.update_cheat_sheet,
            db_user_id,
            str(sheet_id),
            payload.title,
            [s.model_dump() for s in payload.sections],
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"更新小抄时发生错误: {str(e)}")
    if row is None:
        raise HTTPException(status_code=404, detail=f"小抄不存在: {sheet_id}")
    return CheatSheetRecord(**row)


@router.get("/api/cheat-sheets/{sheet_id}", response_model=CheatSheetRecord)
async def get_cheat_sheet(
    user_id: CurrentUserId,
    sheet_id: UUID,
) -> CheatSheetRecord:
    store = _require_store()
    try:
        db_user_id = await asyncio.to_thread(store.get_or_create_user_id, user_id)
        row = await asyncio.to_thread(store.get_cheat_sheet, db_user_id, str(sheet_id))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"读取小抄时发生错误: {str(e)}")
    if row is None:
        raise HTTPException(status_code=404, detail=f"小抄不存在: {sheet_id}")
    return CheatSheetRecord(**row)
