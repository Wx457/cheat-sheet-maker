import traceback
from datetime import datetime
from bson import ObjectId
from pymongo import MongoClient
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional

from app.schemas import (
    OutlineResponse,
    CheatSheetSchema,
    PluginAnalyzeRequest,
    PluginGenerateRequest,
    GenerateFinalResponse,
    TopicInput,
    GenerateSheetRequest,
    AcademicLevel,
    ExamType,
    PageLimit,
)
from app.services.rag_service import get_rag_service
from app.services.llm import generate_outline, generate_cheat_sheet
from app.services.cleaner import clean_raw_text
from app.services.pdf_service import generate_pdf_from_html
from app.utils.html_generator import generate_cheat_sheet_html
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


@router.post("/api/plugin/analyze", response_model=OutlineResponse)
async def plugin_analyze(payload: PluginAnalyzeRequest = Body(...)) -> OutlineResponse:
    """
    Chrome 插件：抓取 + 分析接口
    
    流程：
    1. 保存：将抓取的文本存入向量库
    2. 检索：根据 syllabus 检索相关上下文
    3. 生成：提取考试主题列表
    """
    try:
        rag_service = get_rag_service()
        
        # Step 1: 保存内容到向量库
        source_name = payload.course_name or payload.url
        chunks_count = await rag_service.ingest_text(
            raw_text=payload.content,
            source_name=source_name
        )
        print(f"✅ 已保存 {chunks_count} 个切片到向量库")
        
        # Step 2: 检索相关上下文
        # 注意：刚保存的内容已经进入向量库，可以立即检索到
        rag_context_str = ""
        if payload.syllabus:
            # 如果提供了 syllabus，使用 syllabus 作为查询词进行精准检索
            query = clean_raw_text(payload.syllabus)
            results = await rag_service.search_context(query, k=10)
            
            if results:
                rag_context_str = "\n--- RAG Context from Knowledge Base (filtered by syllabus) ---\n"
                for result in results:
                    rag_context_str += f"Source: {result['source']}\n"
                    rag_context_str += f"Content: {result['content']}\n"
                    rag_context_str += "---------------------------------------\n"
        else:
            # 如果没有 syllabus，使用课程名称或内容摘要作为查询词
            # 优先使用课程名称，如果没有则使用内容摘要
            query = payload.course_name or payload.content[:300] if len(payload.content) > 300 else payload.content
            results = await rag_service.search_context(query, k=10)
            
            if results:
                rag_context_str = "\n--- General RAG Context from Knowledge Base ---\n"
                for result in results:
                    rag_context_str += f"Source: {result['source']}\n"
                    rag_context_str += f"Content: {result['content']}\n"
                    rag_context_str += "---------------------------------------\n"
        
        # Step 3: 生成主题列表
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
        
        # 调用 generate_outline 生成主题列表
        # 复用现有的 generate_outline 函数
        outline_result = generate_outline(
            text=analysis_text,
            context=payload.course_name,
            exam_type=payload.exam_type or ExamType.final
        )
        
        return outline_result
        
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


@router.post("/api/plugin/generate-final", response_model=GenerateFinalResponse)
async def plugin_generate_final(payload: PluginGenerateRequest = Body(...)) -> GenerateFinalResponse:
    """
    Chrome 插件：生成最终 PDF 内容
    
    流程：
    1. 构造 GenerateSheetRequest，复用现有的生成逻辑
    2. 调用 generate_cheat_sheet，它会自动从向量数据库检索上下文并生成内容
    3. 将生成的结果保存到数据库，返回 project_id
    """
    try:
        # 构造 GenerateSheetRequest，复用现有的生成逻辑
        # generate_cheat_sheet 内部会自动根据 selected_topics 从向量数据库检索上下文
        generate_request = GenerateSheetRequest(
            syllabus=payload.syllabus,
            user_context=payload.course_name,
            page_limit=payload.page_limit or PageLimit.one_page,
            academic_level=payload.education_level or AcademicLevel.undergraduate,
            selected_topics=payload.selected_topics,
            exam_type=payload.exam_type or ExamType.final
        )
        
        # 调用现有的 generate_cheat_sheet 函数
        # 该函数内部会：
        # 1. 根据 selected_topics 从向量数据库检索上下文
        # 2. 使用 syllabus 作为过滤指令
        # 3. 生成最终的 Cheat Sheet
        result = await generate_cheat_sheet(generate_request)
        
        # 保存项目到数据库
        client = MongoClient(settings.MONGODB_URI)
        db = client[settings.DB_NAME]
        projects_collection = db["projects"]
        
        # 将 CheatSheetSchema 转换为字典
        project_data = {
            "cheat_sheet": result.model_dump(),
            "course_name": payload.course_name,
            "syllabus": payload.syllabus,
            "education_level": payload.education_level.value if payload.education_level else None,
            "exam_type": payload.exam_type.value if payload.exam_type else None,
            "page_limit": payload.page_limit.value if payload.page_limit else None,
            "selected_topics": [topic.model_dump() for topic in payload.selected_topics],
            "created_at": datetime.utcnow(),
        }
        
        # 插入数据库
        insert_result = projects_collection.insert_one(project_data)
        project_id = str(insert_result.inserted_id)
        
        client.close()
        
        return GenerateFinalResponse(
            project_id=project_id,
            cheat_sheet=result
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
    2. 生成 HTML 内容（包含 Markdown 和 LaTeX 渲染）
    3. 使用 Playwright 直接渲染 HTML 并生成 PDF
    4. 返回 PDF 文件流
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
        
        # 2. 将字典转换为 CheatSheetSchema 对象
        cheat_sheet = CheatSheetSchema(**cheat_sheet_data)
        
        # 3. 生成 HTML (这一步解决了格式乱码和 Markdown 渲染)
        html_content = generate_cheat_sheet_html(cheat_sheet)
        
        # 4. 生成 PDF (这一步解决了 Localhost 连接被拒问题)
        pdf_bytes = await generate_pdf_from_html(html_content)
        
        # 5. 返回 PDF 文件流
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

