import traceback
import time
from datetime import datetime
from bson import ObjectId
from pymongo import MongoClient
from fastapi import APIRouter, Body, HTTPException, Request, Header
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional

from app.schemas import (
    CheatSheetSchema,
    PluginAnalyzeRequest,
    PluginGenerateRequest,
    TopicInput,
    GenerateSheetRequest,
    AcademicLevel,
    ExamType,
    PageLimit,
)
from app.services.rag_service import get_rag_service
from app.services.cleaner import clean_raw_text
from app.services.pdf_service import generate_pdf_via_browser
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
    status_code: int = 500
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
        error=error_type,
        message=message,
        retry_after=retry_after,
        details=details
    )
    return HTTPException(
        status_code=status_code,
        detail=error_response.model_dump(exclude_none=True)
    )


class TaskResponse(BaseModel):
    """任务提交响应"""
    task_id: str
    status: str = "pending"
    message: str = "任务已提交，正在处理中"


@router.post("/api/plugin/analyze", response_model=TaskResponse)
async def plugin_analyze(
    request: Request,
    payload: PluginAnalyzeRequest = Body(...),
    x_user_id: str = Header(..., alias="X-User-ID", description="用户 ID（必需，用于数据隔离）")
) -> TaskResponse:
    """
    Chrome 插件：抓取 + 分析接口
    
    流程：
    1. 保存：将抓取的文本存入向量库
    2. 检索：根据 syllabus 检索相关上下文
    3. 生成：提取考试主题列表
    """
    # ========== [性能监控 - 可删除] ==========
    api_start_time = time.time()
    print(f"⏱️ [性能监控] plugin_analyze API 开始执行")
    # ========== [性能监控 - 可删除] ==========
    
    try:
        rag_service = get_rag_service()
        
        # ========== [性能监控 - 可删除] ==========
        ingest_start_time = time.time()
        # ========== [性能监控 - 可删除] ==========
        
        # Step 1: 保存内容到向量库（传递 user_id 用于数据隔离）
        source_name = payload.course_name or payload.url
        chunks_count = await rag_service.ingest_text(
            raw_text=payload.content,
            source_name=source_name,
            user_id=x_user_id
        )
        
        # ========== [性能监控 - 可删除] ==========
        ingest_elapsed = time.time() - ingest_start_time
        print(f"⏱️ [性能监控] plugin_analyze - Step 1 保存到向量库耗时: {ingest_elapsed:.2f} 秒，保存 {chunks_count} 个切片")
        # ========== [性能监控 - 可删除] ==========
        
        print(f"✅ 已保存 {chunks_count} 个切片到向量库")
        
        # ========== [性能监控 - 可删除] ==========
        search_start_time = time.time()
        # ========== [性能监控 - 可删除] ==========
        
        # Step 2: 检索相关上下文
        # 注意：刚保存的内容已经进入向量库，可以立即检索到
        rag_context_str = ""
        if payload.syllabus:
            # 如果提供了 syllabus，使用 syllabus 作为查询词进行精准检索（传递 user_id 用于数据隔离）
            query = clean_raw_text(payload.syllabus)
            results = await rag_service.search_context(query, user_id=x_user_id, k=10)
            
            if results:
                rag_context_str = "\n--- RAG Context from Knowledge Base (filtered by syllabus) ---\n"
                for result in results:
                    rag_context_str += f"Source: {result['source']}\n"
                    rag_context_str += f"Content: {result['content']}\n"
                    rag_context_str += "---------------------------------------\n"
        else:
            # 如果没有 syllabus，使用课程名称或内容摘要作为查询词
            # 优先使用课程名称，如果没有则使用内容摘要（传递 user_id 用于数据隔离）
            query = payload.course_name or payload.content[:300] if len(payload.content) > 300 else payload.content
            results = await rag_service.search_context(query, user_id=x_user_id, k=10)
            
            if results:
                rag_context_str = "\n--- General RAG Context from Knowledge Base ---\n"
                for result in results:
                    rag_context_str += f"Source: {result['source']}\n"
                    rag_context_str += f"Content: {result['content']}\n"
                    rag_context_str += "---------------------------------------\n"
        
        # ========== [性能监控 - 可删除] ==========
        search_elapsed = time.time() - search_start_time
        print(f"⏱️ [性能监控] plugin_analyze - Step 2 检索上下文耗时: {search_elapsed:.2f} 秒")
        # ========== [性能监控 - 可删除] ==========
        
        # Step 3: 生成主题列表（改为异步任务模式）
        # 基于检索到的 RAG 上下文生成主题列表
        # 如果 RAG 上下文为空，使用原始内容摘要作为后备
        if rag_context_str:
            # 使用 RAG 上下文作为主要输入
            analysis_text = rag_context_str
            if payload.syllabus:
                # 如果有 syllabus，在上下文中强调考纲要求
                analysis_text = f"考试大纲要求：\n{payload.syllabus}\n\n" + rag_context_str
        else:
            # 如果没有检索到上下文，使用原始内容摘要
            analysis_text = payload.content[:2000]
            print("⚠️ 未检索到 RAG 上下文，使用原始内容摘要")
        
        # 将生成大纲任务推送到 ARQ 队列（传递 user_id 用于数据隔离）
        arq_pool = request.app.state.arq_pool
        
        job = await arq_pool.enqueue_job(
            'generate_outline_task',
            raw_text=analysis_text,
            user_context=payload.course_name,
            exam_type=(payload.exam_type or ExamType.final).value,
            user_id=x_user_id
        )
        
        # ========== [性能监控 - 可删除] ==========
        total_elapsed = time.time() - api_start_time
        print(f"⏱️ [性能监控] plugin_analyze API 总耗时: {total_elapsed:.2f} 秒")
        # ========== [性能监控 - 可删除] ==========
        
        return TaskResponse(
            task_id=job.job_id,
            status="pending",
            message="分析任务已提交，正在生成主题列表"
        )
        
    except ValueError as e:
        # LLM 相关的错误（如 Rate Limit、超时等）
        error_msg = str(e)
        if "配额" in error_msg or "quota" in error_msg.lower() or "rate limit" in error_msg.lower():
            raise _create_error_response(
                error_type="QUOTA_EXCEEDED",
                message="API 配额已用尽，请稍后重试",
                retry_after=60,
                details=error_msg,
                status_code=429
            )
        elif "超时" in error_msg or "timeout" in error_msg.lower():
            raise _create_error_response(
                error_type="REQUEST_TIMEOUT",
                message="请求超时，请稍后重试",
                retry_after=30,
                details=error_msg,
                status_code=408
            )
        elif "服务" in error_msg or "service" in error_msg.lower() or "unavailable" in error_msg.lower():
            raise _create_error_response(
                error_type="SERVICE_UNAVAILABLE",
                message="服务暂时不可用，请稍后重试",
                retry_after=60,
                details=error_msg,
                status_code=503
            )
        else:
            raise _create_error_response(
                error_type="VALIDATION_ERROR",
                message="输入验证失败",
                details=error_msg,
                status_code=400
            )
    except Exception as e:
        traceback.print_exc()
        raise _create_error_response(
            error_type="INTERNAL_ERROR",
            message="分析过程中发生未知错误",
            details=str(e),
            status_code=500
        )


@router.post("/api/plugin/generate-final", response_model=TaskResponse)
async def plugin_generate_final(
    request: Request,
    payload: PluginGenerateRequest = Body(...),
    x_user_id: str = Header(..., alias="X-User-ID", description="用户 ID（必需，用于数据隔离）")
) -> TaskResponse:
    """
    Chrome 插件：生成最终 PDF 内容
    
    现在改为异步任务模式：
    1. 将生成任务推送到 Redis 队列
    2. 立即返回 task_id
    3. Worker 会处理任务，生成小抄并保存到数据库
    4. 客户端可以通过 /api/task/{task_id} 查询任务状态和结果（包含 project_id）
    """
    try:
        arq_pool = request.app.state.arq_pool
        
        # 构造 GenerateSheetRequest 的负载数据（传递 user_id 用于数据隔离）
        task_kwargs = {
            "syllabus": payload.syllabus,
            "user_context": payload.course_name,
            "page_limit": (payload.page_limit or PageLimit.one_page).value,
            "academic_level": (payload.education_level or AcademicLevel.undergraduate).value,
            "selected_topics": [topic.model_dump() for topic in payload.selected_topics],
            "exam_type": (payload.exam_type or ExamType.final).value,
            "user_id": x_user_id,  # 传递 user_id 用于数据隔离
            # 添加额外的元数据，用于 Worker 保存到数据库
            "_metadata": {
                "course_name": payload.course_name,
                "syllabus": payload.syllabus,
                "education_level": payload.education_level.value if payload.education_level else None,
                "exam_type": payload.exam_type.value if payload.exam_type else None,
                "page_limit": payload.page_limit.value if payload.page_limit else None,
                "selected_topics": [topic.model_dump() for topic in payload.selected_topics],
            }
        }
        
        # 推送任务到 ARQ 队列
        job = await arq_pool.enqueue_job(
            'generate_cheat_sheet_task',
            **task_kwargs
        )
        
        return TaskResponse(
            task_id=job.job_id,
            status="pending",
            message="小抄生成任务已提交，正在处理中"
        )
        
    except ValueError as e:
        # LLM 相关的错误（如 Rate Limit、超时等）
        error_msg = str(e)
        if "配额" in error_msg or "quota" in error_msg.lower() or "rate limit" in error_msg.lower():
            raise _create_error_response(
                error_type="QUOTA_EXCEEDED",
                message="API 配额已用尽，请稍后重试",
                retry_after=60,
                details=error_msg,
                status_code=429
            )
        elif "超时" in error_msg or "timeout" in error_msg.lower():
            raise _create_error_response(
                error_type="REQUEST_TIMEOUT",
                message="请求超时，请稍后重试",
                retry_after=30,
                details=error_msg,
                status_code=408
            )
        elif "服务" in error_msg or "service" in error_msg.lower() or "unavailable" in error_msg.lower():
            raise _create_error_response(
                error_type="SERVICE_UNAVAILABLE",
                message="服务暂时不可用，请稍后重试",
                retry_after=60,
                details=error_msg,
                status_code=503
            )
        else:
            raise _create_error_response(
                error_type="VALIDATION_ERROR",
                message="输入验证失败",
                details=error_msg,
                status_code=400
            )
    except Exception as e:
        traceback.print_exc()
        raise _create_error_response(
            error_type="INTERNAL_ERROR",
            message="生成过程中发生未知错误",
            details=str(e),
            status_code=500
        )


@router.get("/api/plugin/project/{project_id}", response_model=CheatSheetSchema)
async def get_project(project_id: str) -> CheatSheetSchema:
    """
    获取项目数据
    
    根据 project_id 从数据库获取项目的小抄数据
    """
    try:
        # 验证 project_id 格式
        if not ObjectId.is_valid(project_id):
            raise HTTPException(
                status_code=400,
                detail=f"无效的 project_id: {project_id}"
            )
        
        # 从数据库获取项目数据
        client = MongoClient(settings.MONGODB_URI)
        db = client[settings.DB_NAME]
        projects_collection = db["projects"]
        
        # 查询项目
        project = projects_collection.find_one({"_id": ObjectId(project_id)})
        if not project:
            raise HTTPException(
                status_code=404,
                detail=f"未找到项目: {project_id}"
            )
        
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
            message="获取项目数据失败",
            details=str(e),
            status_code=500
        )


@router.get("/api/plugin/download-cheat-sheet/{project_id}")
async def download_cheat_sheet(project_id: str) -> Response:
    """
    Chrome 插件：下载生成的 PDF
    
    流程：
    1. 从数据库获取项目数据（确保数据已存库）
    2. 使用 React 前端渲染引擎生成 PDF（通过 pdf_service.generate_pdf_via_browser）
    3. 返回 PDF 文件流
    """
    # ========== [性能监控 - 可删除] ==========
    api_start_time = time.time()
    print(f"⏱️ [性能监控] download_cheat_sheet API 开始执行，project_id: {project_id}")
    # ========== [性能监控 - 可删除] ==========
    
    try:
        # ========== [性能监控 - 可删除] ==========
        db_start_time = time.time()
        # ========== [性能监控 - 可删除] ==========
        
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
                status_code=400
            )
        
        # 查询项目
        project = projects_collection.find_one({"_id": ObjectId(project_id)})
        if not project:
            raise _create_error_response(
                error_type="PROJECT_NOT_FOUND",
                message="未找到指定的项目",
                details=f"project_id: {project_id}",
                status_code=404
            )
        
        # 获取 Cheat Sheet 数据
        cheat_sheet_data = project.get("cheat_sheet", {})
        if not cheat_sheet_data:
            raise _create_error_response(
                error_type="CHEAT_SHEET_NOT_FOUND",
                message="项目中未找到小抄数据",
                details=f"project_id: {project_id}",
                status_code=404
            )
        
        client.close()
        
        # ========== [性能监控 - 可删除] ==========
        db_elapsed = time.time() - db_start_time
        print(f"⏱️ [性能监控] download_cheat_sheet - Step 1 从数据库获取项目数据耗时: {db_elapsed:.2f} 秒")
        # ========== [性能监控 - 可删除] ==========
        
        # 2. 使用 React 前端渲染引擎生成 PDF
        # 直接将 CheatSheet 数据（字典格式）传给 PDF 服务
        # PDF 服务会访问 React 静态页面并注入数据
        pdf_bytes = await generate_pdf_via_browser(cheat_sheet_data)
        
        # ========== [性能监控 - 可删除] ==========
        total_elapsed = time.time() - api_start_time
        print(f"⏱️ [性能监控] download_cheat_sheet API 总耗时: {total_elapsed:.2f} 秒")
        # ========== [性能监控 - 可删除] ==========
        
        # 3. 返回 PDF 文件流
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="cheat-sheet-{project_id}.pdf"'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise _create_error_response(
            error_type="PDF_GENERATION_ERROR",
            message="生成 PDF 失败",
            details=str(e),
            status_code=500
        )

