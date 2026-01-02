import traceback

from fastapi import APIRouter, Body, HTTPException

from app.schemas import (
    CheatSheetSchema,
    GenerateOutlineRequest,
    GenerateSheetRequest,
    OutlineResponse,
)
from app.services.llm import generate_cheat_sheet as llm_generate_cheat_sheet
from app.services.llm import generate_outline as llm_generate_outline

router = APIRouter()


@router.post("/api/outline", response_model=OutlineResponse)
async def generate_outline(payload: GenerateOutlineRequest = Body(...)) -> OutlineResponse:
    """
    生成复习大纲，分析对话记录并提取核心考试主题。
    """
    try:
        result = llm_generate_outline(payload.raw_text, payload.user_context, payload.exam_type)
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"生成大纲时发生错误: {str(e)}"
        )


@router.post("/api/generate", response_model=CheatSheetSchema)
async def generate_cheat_sheet(payload: GenerateSheetRequest = Body(...)) -> CheatSheetSchema:
    """
    生成备忘清单，使用 Google Gemini API 处理用户输入的文本。
    支持混合检索和领域自适应算法。
    """
    try:
        result = await llm_generate_cheat_sheet(payload)
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"生成小抄时发生错误: {str(e)}"
        )

