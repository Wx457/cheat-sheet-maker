import json
import traceback
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.schemas import (
    GenerateOutlineRequest,
    GenerateSheetRequest,
    OutlineResponse,
    RegenerateSectionsRequest,
)
from app.application.services.cheat_sheet_service import CheatSheetService
from app.application.services.course_service import CourseNotFoundError, resolve_course_id
from app.core.auth import CurrentUserId
from app.infrastructure.cache.redis_cache import get_cheat_sheet_cache, make_cache_key

router = APIRouter()


async def _resolve_course(user_id: str, course_id: Optional[UUID]) -> Optional[str]:
    """第 8 点：校验课程归属（不属于 → 404）；不传 → 默认课程；未接 Supabase → None（检索全部知识库）"""
    try:
        return await resolve_course_id(user_id, str(course_id) if course_id else None)
    except CourseNotFoundError:
        raise HTTPException(status_code=404, detail=f"课程不存在: {course_id}")


@router.post("/api/outline", response_model=OutlineResponse)
async def generate_outline(
    user_id: CurrentUserId,
    payload: GenerateOutlineRequest = Body(...),
) -> OutlineResponse:
    """
    生成复习大纲，分析对话记录并提取核心考试主题。

    直接在请求内执行（RAG 检索 + LLM），完成后返回大纲，不经过任务队列。
    """
    # raw_text is now optional; fall back to user_context then a generic query
    # so the service always receives a non-empty RAG search string
    query_text = payload.raw_text or payload.user_context or "key exam topics"
    course_id = await _resolve_course(user_id, payload.course_id)
    try:
        service = CheatSheetService.default()
        return await service.generate_outline(
            text=query_text,
            context=payload.user_context,
            exam_type=payload.exam_type,
            user_id=user_id,
            ingest_batch_id=payload.ingest_batch_id,
            course_id=course_id,
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"生成大纲时发生错误: {str(e)}")


@router.post("/api/generate/stream")
async def generate_cheat_sheet_stream(
    user_id: CurrentUserId,
    request: Request,
    payload: GenerateSheetRequest = Body(...),
):
    """
    流式版本：直接在 HTTP 请求内执行，不经过 ARQ 队列。
    返回 SSE（text/event-stream）。

    Phase 5：同一用户 + 同一知识库 + 同一请求参数命中 Redis 缓存时直接重放事件（响应头 X-Cache: HIT）。
    只缓存完整成功的生成（收到 [DONE] 且至少 1 个 section）；中途异常 / 客户端断开不缓存。
    第 8 点：只检索 course_id 对应课程的知识库；解析后的 course_id 写回 payload，因而也参与缓存键。
    """
    resolved = await _resolve_course(user_id, payload.course_id)
    payload = payload.model_copy(update={"course_id": UUID(resolved) if resolved else None})
    service = CheatSheetService.default()
    cache = get_cheat_sheet_cache()
    key = make_cache_key(
        user_id,
        payload.model_dump(mode="json", exclude={"no_cache"}),
        getattr(getattr(service, "gemini", None), "model_name", "unknown"),
    )
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # 关闭 nginx 缓冲，确保实时推送
    }

    cached = None if payload.no_cache else await cache.get(key)
    if cached is not None:

        async def replay():
            for data in cached:
                yield f"data: {data}\n\n"
            yield SSE_DONE

        return StreamingResponse(
            replay(), media_type="text/event-stream", headers={**headers, "X-Cache": "HIT"}
        )

    async def event_generator():
        events: list[str] = []
        completed = False
        async for sse_line in service.stream_cheat_sheet_sections(
            request_data=payload,
            user_id=user_id,
        ):
            if sse_line == SSE_DONE:
                completed = True
            elif sse_line.startswith("data: "):
                events.append(sse_line[len("data: ") :].rstrip("\n"))
            yield sse_line
        # 只有生成器自然跑完才会到这里（异常 / 客户端断开时不会执行）
        if completed and _has_section(events):
            await cache.set(user_id, key, events)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={**headers, "X-Cache": "BYPASS" if payload.no_cache else "MISS"},
    )


@router.post("/api/generate/regenerate")
async def regenerate_sections_stream(
    user_id: CurrentUserId,
    payload: RegenerateSectionsRequest = Body(...),
):
    """
    8-2 部分重新生成（SSE）：只重写选中的 section，事件里的 `_index` 是它要替换的位置。

    不读也不写生成缓存：重新生成本身就是为了换一版；结果由前端保存为新版本
    （origin = regenerate，parent_sheet_id = 当前版本），刷新后按 sheetId 加载即可。
    """
    resolved = await _resolve_course(user_id, payload.params.course_id)
    params = payload.params.model_copy(update={"course_id": UUID(resolved) if resolved else None})
    payload = payload.model_copy(update={"params": params})
    service = CheatSheetService.default()

    return StreamingResponse(
        service.stream_regenerated_sections(request_data=payload, user_id=user_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


SSE_DONE = "data: [DONE]\n\n"


def _has_section(events: list[str]) -> bool:
    """至少有一个非 meta 事件（section）才值得缓存，避免把空结果缓存 24 小时。"""
    for data in events:
        try:
            obj = json.loads(data)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("_type") != "meta":
            return True
    return False
