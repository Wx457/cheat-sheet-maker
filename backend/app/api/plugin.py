import traceback
from typing import Optional
from bson import ObjectId
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from pymongo import MongoClient

from app.schemas import CheatSheetSchema
from app.infrastructure.pdf.renderer import generate_pdf_via_browser
from app.core.config import settings

router = APIRouter()


class ErrorResponse(BaseModel):
    """结构化错误响应模型"""

    error: str  # 错误类型代码
    message: str  # 人类可读的错误消息
    retry_after: Optional[int] = None  # 建议重试时间（秒）
    details: Optional[str] = None  # 详细错误信息（可选）


def _create_error_response(
    error_type: str,
    message: str,
    retry_after: Optional[int] = None,
    details: Optional[str] = None,
    status_code: int = 500,
) -> HTTPException:
    """
    创建结构化的错误响应

    Args:
        error_type: 错误类型代码（如 "QUOTA_EXCEEDED", "SERVICE_UNAVAILABLE"）
        message: 人类可读的错误消息
        retry_after: 建议重试时间（秒）
        details: 详细错误信息
        status_code: HTTP 状态码

    Returns:
        HTTPException 对象
    """
    error_response = ErrorResponse(
        error=error_type, message=message, retry_after=retry_after, details=details
    )
    return HTTPException(
        status_code=status_code, detail=error_response.model_dump(exclude_none=True)
    )


# TODO: DEPRECATED — 待删除
# 被替代方：webapp 流式端点直接在前端维护 sections 状态（Zustand），
#   不再需要通过 project_id 从数据库回捞数据。
# 确认 Chrome 插件完全停用后删除此端点及下方所有实现。
@router.get("/api/plugin/project/{project_id}", response_model=CheatSheetSchema)
async def get_project(project_id: str) -> CheatSheetSchema:
    """
    获取项目数据

    根据 project_id 从数据库获取项目的小抄数据
    """
    try:
        # 验证 project_id 格式
        if not ObjectId.is_valid(project_id):
            raise HTTPException(status_code=400, detail=f"无效的 project_id: {project_id}")

        # 从数据库获取项目数据
        client = MongoClient(settings.MONGODB_URI)
        db = client[settings.DB_NAME]
        projects_collection = db["projects"]

        # 查询项目
        project = projects_collection.find_one({"_id": ObjectId(project_id)})
        if not project:
            raise HTTPException(status_code=404, detail=f"未找到项目: {project_id}")

        client.close()

        # 返回小抄数据
        cheat_sheet_data = project.get("cheat_sheet", {})
        return CheatSheetSchema(**cheat_sheet_data)

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise _create_error_response(
            error_type="INTERNAL_ERROR",
            message="Failed to get project data",
            details=str(e),
            status_code=500,
        )


# TODO: DEPRECATED — 待删除
# 被替代方：webapp 客户端 PDF 导出（Phase 5，print CSS 或 @react-pdf/renderer）。
#   PDF 在浏览器端生成，无需后端 Playwright 渲染 + S3 存储这条链路。
# 确认 Chrome 插件完全停用后删除此端点及下方所有实现。
@router.get("/api/plugin/download-cheat-sheet/{project_id}")
async def download_cheat_sheet(project_id: str) -> Response:
    """
    Chrome 插件：下载生成的 PDF

    流程：
    1. 从数据库获取项目数据（确保数据已存库）
    2. 使用 React 前端渲染引擎生成 PDF（通过 pdf_service.generate_pdf_via_browser）
    3. 返回 PDF 文件流
    """
    try:
        # 1. 从数据库获取项目数据，确保数据已存库
        client = MongoClient(settings.MONGODB_URI)
        db = client[settings.DB_NAME]
        projects_collection = db["projects"]

        # 验证 project_id 格式
        if not ObjectId.is_valid(project_id):
            raise _create_error_response(
                error_type="INVALID_PROJECT_ID",
                message="无效的项目 ID 格式",
                details=f"project_id: {project_id}",
                status_code=400,
            )

        # 查询项目
        project = projects_collection.find_one({"_id": ObjectId(project_id)})
        if not project:
            raise _create_error_response(
                error_type="PROJECT_NOT_FOUND",
                message="未找到指定的项目",
                details=f"project_id: {project_id}",
                status_code=404,
            )

        # 获取 Cheat Sheet 数据
        cheat_sheet_data = project.get("cheat_sheet", {})
        if not cheat_sheet_data:
            raise _create_error_response(
                error_type="CHEAT_SHEET_NOT_FOUND",
                message="项目中未找到小抄数据",
                details=f"project_id: {project_id}",
                status_code=404,
            )

        client.close()

        # 2. 使用 React 前端渲染引擎生成 PDF
        # 直接将 CheatSheet 数据（字典格式）传给 PDF 服务
        # PDF 服务会访问 React 静态页面并注入数据
        pdf_bytes = await generate_pdf_via_browser(cheat_sheet_data)

        # 3. 返回 PDF 文件流
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="cheat-sheet-{project_id}.pdf"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise _create_error_response(
            error_type="PDF_GENERATION_ERROR",
            message="Failed to generate PDF",
            details=str(e),
            status_code=500,
        )


# ──────────────────────────────────────────────────────────────────────────────
# DEPRECATED & DISABLED — 已由 DELETE /api/rag/chunks 取代
# 新端点语义更清晰（用户级别删除），且归属于正确的 rag 路由模块。
# 此端点已注释停用；待确认全量切换后整体删除此段代码。
# ──────────────────────────────────────────────────────────────────────────────
# @router.delete("/api/plugin/reset")
# async def reset_knowledge_base(
#     x_user_id: str = Header(..., alias="X-User-ID")
# ) -> dict:
#     """Chrome 插件：重置当前用户的知识库（向量数据）。已废弃，请用 DELETE /api/rag/chunks。"""
#     try:
#         ingestion = IngestionService.default()
#         deleted_count = await asyncio.to_thread(ingestion.rag_service.delete_user_data, x_user_id)
#         return {"status": "success", "deleted_count": int(deleted_count)}
#     except Exception as e:
#         traceback.print_exc()
#         raise _create_error_response(
#             error_type="RESET_FAILED",
#             message="Failed to reset knowledge base",
#             details=str(e),
#             status_code=500,
#         )
