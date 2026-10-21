import traceback
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.schemas import (
    GenerateOutlineRequest,
    GenerateSheetRequest,
    OutlineResponse,
)
from app.application.services.cheat_sheet_service import CheatSheetService
from app.core.auth import CurrentUserId

router = APIRouter()


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
    try:
        service = CheatSheetService.default()
        return await service.generate_outline(
            text=query_text,
            context=payload.user_context,
            exam_type=payload.exam_type,
            user_id=user_id,
            ingest_batch_id=payload.ingest_batch_id,
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
    """
    service = CheatSheetService.default()

    async def event_generator():
        async for sse_line in service.stream_cheat_sheet_sections(
            request_data=payload,
            user_id=user_id,
        ):
            yield sse_line

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 关闭 nginx 缓冲，确保实时推送
        },
    )
