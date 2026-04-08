import traceback
from pydantic import BaseModel
from fastapi import APIRouter, Body, HTTPException, Request, Header

from app.schemas import (
    GenerateOutlineRequest,
    GenerateSheetRequest,
)

router = APIRouter()


class TaskResponse(BaseModel):
    """任务提交响应"""

    task_id: str
    status: str = "pending"
    message: str = "任务已提交，正在处理中"


@router.post("/api/outline", response_model=TaskResponse)
async def generate_outline(
    request: Request,
    payload: GenerateOutlineRequest = Body(...),
    x_user_id: str = Header(..., alias="X-User-ID", description="用户 ID（必需，用于数据隔离）"),
) -> TaskResponse:
    """
    生成复习大纲，分析对话记录并提取核心考试主题。

    现在改为异步任务模式：
    1. 将任务推送到 ARQ 队列
    2. 立即返回 task_id
    3. 客户端可以通过 /api/task/{task_id} 查询任务状态和结果
    """
    try:
        # 从应用状态获取 ARQ 连接池
        arq_pool = request.app.state.arq_pool

        # 提交任务到 ARQ 队列（传递 user_id 用于数据隔离）
        job = await arq_pool.enqueue_job(
            "generate_outline_task",
            raw_text=payload.raw_text,
            user_context=payload.user_context,
            exam_type=payload.exam_type.value if payload.exam_type else "final",
            user_id=x_user_id,
            ingest_batch_id=payload.ingest_batch_id,
        )

        return TaskResponse(
            task_id=job.job_id, status="pending", message="大纲生成任务已提交，正在处理中"
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"提交任务时发生错误: {str(e)}")


@router.post("/api/generate", response_model=TaskResponse)
async def generate_cheat_sheet(
    request: Request,
    payload: GenerateSheetRequest = Body(...),
    x_user_id: str = Header(..., alias="X-User-ID", description="用户 ID（必需，用于数据隔离）"),
) -> TaskResponse:
    """
    生成备忘清单，使用 Google Gemini API 处理用户输入的文本。
    支持混合检索和领域自适应算法。

    现在改为异步任务模式：
    1. 将任务推送到 ARQ 队列
    2. 立即返回 task_id
    3. 客户端可以通过 /api/task/{task_id} 查询任务状态和结果
    """
    try:
        # 从应用状态获取 ARQ 连接池
        arq_pool = request.app.state.arq_pool

        # 构建任务参数（将 Pydantic 模型转换为字典）
        task_kwargs = payload.model_dump(exclude_none=True)

        # 处理枚举类型
        if payload.page_limit:
            task_kwargs["page_limit"] = payload.page_limit.value
        if payload.academic_level:
            task_kwargs["academic_level"] = payload.academic_level.value
        if payload.exam_type:
            task_kwargs["exam_type"] = payload.exam_type.value
        if payload.archetype:
            task_kwargs["archetype"] = payload.archetype.value
        if payload.selected_topics:
            task_kwargs["selected_topics"] = [
                topic.model_dump() for topic in payload.selected_topics
            ]

        # 添加 user_id（必需，用于数据隔离）
        task_kwargs["user_id"] = x_user_id

        # 提交任务到 ARQ 队列
        job = await arq_pool.enqueue_job("generate_cheat_sheet_task", **task_kwargs)

        return TaskResponse(
            task_id=job.job_id, status="pending", message="小抄生成任务已提交，正在处理中"
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"提交任务时发生错误: {str(e)}")
