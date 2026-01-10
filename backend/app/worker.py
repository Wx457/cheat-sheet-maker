"""
ARQ Worker 进程
监听 Redis 队列，执行耗时的 LLM 和 PDF 生成任务
"""
import traceback
import base64
from typing import Dict, Any
from datetime import datetime

from arq.connections import RedisSettings
from arq.worker import Worker

from app.services.llm import generate_outline, generate_cheat_sheet
from app.services.pdf_service import generate_pdf_from_html
from app.services.storage import get_storage_service
from app.utils.html_generator import generate_cheat_sheet_html
from app.schemas import (
    GenerateSheetRequest,
    CheatSheetSchema,
    ExamType
)
from app.core.config import settings


# ARQ 任务函数定义

async def generate_outline_task(
    ctx,
    raw_text: str,
    user_context: str = None,
    exam_type: str = "final"
) -> Dict[str, Any]:
    """
    ARQ 任务：生成大纲
    
    Args:
        ctx: ARQ 上下文
        raw_text: 原始文本
        user_context: 用户背景信息
        exam_type: 考试类型
        
    Returns:
        任务结果
    """
    try:
        exam_type_enum = ExamType(exam_type)
        
        # 调用生成函数
        result = generate_outline(
            text=raw_text,
            context=user_context,
            exam_type=exam_type_enum
        )
        
        # 返回结果（ARQ 会自动存储）
        return {
            "success": True,
            "data": result.model_dump()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


async def generate_cheat_sheet_task(
    ctx,
    **kwargs
) -> Dict[str, Any]:
    """
    ARQ 任务：生成小抄（全流程）
    
    流程：
    1. LLM 生成小抄内容
    2. 保存到数据库（如果包含 _metadata）
    3. 生成 HTML
    4. 生成 PDF
    5. 上传到 MinIO
    6. 返回包含 file_key 的结果
    
    Args:
        ctx: ARQ 上下文
        **kwargs: GenerateSheetRequest 的所有字段，可能包含 _metadata
        
    Returns:
        任务结果（包含 file_key 和 project_id）
    """
    try:
        # 提取元数据（如果存在）
        metadata = kwargs.pop("_metadata", None)
        
        # 构建请求参数
        generate_request = GenerateSheetRequest(**kwargs)
        
        # Step 1: 调用 LLM 生成函数
        result = await generate_cheat_sheet(generate_request)
        
        # Step 2: 如果包含元数据，保存到数据库
        project_id = None
        if metadata:
            from pymongo import MongoClient
            from datetime import datetime
            
            client = MongoClient(settings.MONGODB_URI)
            db = client[settings.DB_NAME]
            projects_collection = db["projects"]
            
            # 构建项目数据
            project_data = {
                "cheat_sheet": result.model_dump(),
                "course_name": metadata.get("course_name"),
                "syllabus": metadata.get("syllabus"),
                "education_level": metadata.get("education_level"),
                "exam_type": metadata.get("exam_type"),
                "page_limit": metadata.get("page_limit"),
                "selected_topics": metadata.get("selected_topics", []),
                "created_at": datetime.utcnow(),
            }
            
            # 插入数据库
            insert_result = projects_collection.insert_one(project_data)
            project_id = str(insert_result.inserted_id)
            client.close()
        
        # Step 3: 生成 HTML
        html_content = generate_cheat_sheet_html(result)
        
        # Step 4: 生成 PDF
        pdf_bytes = await generate_pdf_from_html(html_content)
        
        # Step 5: 上传到 MinIO
        storage_service = get_storage_service()
        
        # 生成文件名（使用小抄标题和时间戳）
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c for c in result.title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_title = safe_title.replace(' ', '_')[:50]  # 限制长度
        filename = f"{safe_title}_{timestamp}.pdf"
        
        # 上传文件
        file_key = storage_service.upload_file(pdf_bytes, filename)
        
        if not file_key:
            raise ValueError("PDF 上传到 MinIO 失败")
        
        # Step 6: 返回结果（包含 file_key 和 project_id）
        result_data = {
            "status": "completed",
            "file_key": file_key,
            "size": len(pdf_bytes),
            "filename": filename,
            "data": result.model_dump()  # 保留原始数据用于兼容
        }
        
        if project_id:
            result_data["project_id"] = project_id
        
        return result_data
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
            "traceback": traceback.format_exc()
        }


async def generate_pdf_task(
    ctx,
    cheat_sheet: Dict[str, Any]
) -> Dict[str, Any]:
    """
    ARQ 任务：生成 PDF 并上传到 MinIO
    
    Args:
        ctx: ARQ 上下文
        cheat_sheet: 小抄数据字典
        
    Returns:
        任务结果（包含 file_key）
    """
    try:
        if not cheat_sheet:
            raise ValueError("缺少 cheat_sheet 数据")
        
        # 转换为 CheatSheetSchema
        cheat_sheet_obj = CheatSheetSchema(**cheat_sheet)
        
        # 生成 HTML
        html_content = generate_cheat_sheet_html(cheat_sheet_obj)
        
        # 生成 PDF
        pdf_bytes = await generate_pdf_from_html(html_content)
        
        # 上传到 MinIO
        storage_service = get_storage_service()
        
        # 生成文件名（使用小抄标题和时间戳）
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c for c in cheat_sheet_obj.title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_title = safe_title.replace(' ', '_')[:50]  # 限制长度
        filename = f"{safe_title}_{timestamp}.pdf"
        
        # 上传文件
        file_key = storage_service.upload_file(pdf_bytes, filename)
        
        if not file_key:
            raise ValueError("PDF 上传到 MinIO 失败")
        
        # 返回结果（包含 file_key）
        return {
            "status": "completed",
            "file_key": file_key,
            "size": len(pdf_bytes),
            "filename": filename
        }
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
            "traceback": traceback.format_exc()
        }


# ARQ Worker 配置

class WorkerSettings:
    """ARQ Worker 配置"""
    
    # Redis 连接设置
    redis_settings = RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        database=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None
    )
    
    # 注册任务函数
    functions = [
        generate_outline_task,
        generate_cheat_sheet_task,
        generate_pdf_task,
    ]
    
    # Worker 配置
    max_jobs = 10  # 最大并发任务数
    job_timeout = 600  # 任务超时时间（秒）
    keep_result = 86400  # 结果保留时间（24小时）


# 启动和关闭钩子（可选）

async def startup(ctx):
    """Worker 启动时执行"""
    print("🚀 ARQ Worker 启动...")
    # 确保 MinIO Bucket 存在
    storage_service = get_storage_service()
    storage_service.ensure_bucket()


async def shutdown(ctx):
    """Worker 关闭时执行"""
    print("👋 ARQ Worker 关闭...")


# 如果直接运行此文件，启动 Worker
if __name__ == "__main__":
    # 添加启动和关闭钩子
    WorkerSettings.on_startup = startup
    WorkerSettings.on_shutdown = shutdown
    
    # 创建并运行 Worker
    worker = Worker(
        functions=WorkerSettings.functions,
        redis_settings=WorkerSettings.redis_settings,
        max_jobs=WorkerSettings.max_jobs,
        job_timeout=WorkerSettings.job_timeout,
        keep_result=WorkerSettings.keep_result,
        on_startup=startup,
        on_shutdown=shutdown,
    )
    worker.run()
