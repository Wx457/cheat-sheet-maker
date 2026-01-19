"""
ARQ Worker 进程
监听 Redis 队列，执行耗时的 LLM 和 PDF 生成任务
"""
import traceback
import base64
import time
from typing import Dict, Any
from datetime import datetime

from arq.connections import RedisSettings
from arq.worker import Worker

from app.services.llm import generate_outline, generate_cheat_sheet
from app.services.pdf_service import generate_pdf_via_browser
from app.services.storage import get_storage_service
from app.schemas import (
    GenerateSheetRequest,
    CheatSheetSchema,
    ExamType
)
from app.core.config import settings


# 数据清洗函数

def normalize_equation(content: str) -> str:
    """强制给公式加上 $$ 包裹"""
    if not content: 
        return ""
    content = content.strip()
    
    # 移除可能存在的 \[ \]
    if content.startswith(r"\[") and content.endswith(r"\]"):
        content = content[2:-2].strip()
        
    # 如果已经是 $$ 包裹，直接返回
    if content.startswith("$$") and content.endswith("$$"):
        return content
        
    # 如果是行内 $ 包裹，改成 $$
    if content.startswith("$") and content.endswith("$"):
        return "$$" + content[1:-1] + "$$"
        
    # 裸奔的 LaTeX，加上 $$
    return f"$${content}$$"


def clean_equation_data(content_dict: Dict[str, Any]) -> None:
    """
    清洗 cheat sheet 数据中的公式内容
    
    Args:
        content_dict: CheatSheet 数据的字典（会被原地修改）
    """
    try:
        print("正在清洗公式数据...")
        for section in content_dict.get("sections", []):
            for item in section.get("items", []):
                if item.get("type") == "equation":
                    raw = item.get("content", "")
                    # 洗干净再放回去
                    item["content"] = normalize_equation(raw)
        print("✅ 公式数据清洗完成")
    except Exception as e:
        print(f"⚠️ 清洗数据时出错 (非致命): {e}")


# ARQ 任务函数定义

async def generate_outline_task(
    ctx,
    raw_text: str,
    user_context: str = None,
    exam_type: str = "final",
    user_id: str = None  # 接受 user_id 参数以保持 API 一致性（虽然此任务不涉及 RAG，但 API 会传递）
) -> Dict[str, Any]:
    """
    ARQ 任务：生成大纲
    
    注意：此任务不涉及 RAG 检索，但接受 user_id 参数以保持 API 一致性。
    
    Args:
        ctx: ARQ 上下文
        raw_text: 原始文本
        user_context: 用户背景信息
        exam_type: 考试类型
        user_id: 用户 ID（可选，用于保持 API 一致性，此任务不使用）
        
    Returns:
        任务结果
    """
    # ========== [性能监控 - 可删除] ==========
    task_start_time = time.time()
    print(f"⏱️ [性能监控] generate_outline_task 开始执行")
    
    try:
        exam_type_enum = ExamType(exam_type)
        
        # ========== [性能监控 - 可删除] ==========
        llm_start_time = time.time()
        
        # 调用生成函数
        result = generate_outline(
            text=raw_text,
            context=user_context,
            exam_type=exam_type_enum
        )
        
        # ========== [性能监控 - 可删除] ==========
        llm_elapsed = time.time() - llm_start_time
        print(f"⏱️ [性能监控] LLM 生成大纲耗时: {llm_elapsed:.2f} 秒")
        total_elapsed = time.time() - task_start_time
        print(f"⏱️ [性能监控] generate_outline_task 总耗时: {total_elapsed:.2f} 秒")
        
        # 返回结果（ARQ 会自动存储）
        return {
            "success": True,
            "data": result.model_dump()
        }
    except Exception as e:
        # ========== [性能监控 - 可删除] ==========
        total_elapsed = time.time() - task_start_time
        print(f"⏱️ [性能监控] generate_outline_task 失败，总耗时: {total_elapsed:.2f} 秒")

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
    1. LLM 生成小抄内容（内部使用并行 MMR 检索 + 去重优化）
    2. 保存到数据库（如果包含 _metadata）
    3. 清洗数据（清洗公式格式）
    4. 生成 PDF（使用 React 前端渲染）
    5. 上传到 MinIO
    6. 返回包含 file_key 的结果
    
    注意：RAG 检索优化（并行 MMR + 去重）在 generate_cheat_sheet() 函数内部实现。
    
    Args:
        ctx: ARQ 上下文
        **kwargs: GenerateSheetRequest 的所有字段，可能包含 _metadata
        
    Returns:
        任务结果（包含 file_key 和 project_id）
    """
    # ========== [性能监控 - 可删除] ==========
    task_start_time = time.time()
    print(f"⏱️ [性能监控] generate_cheat_sheet_task 开始执行")
    
    try:
        # 提取元数据（如果存在）
        metadata = kwargs.pop("_metadata", None)
        
        # 提取 user_id（必需，用于数据隔离）
        # 如果没有提供 user_id，抛出错误（不允许 None）
        user_id = kwargs.pop("user_id", None)
        if not user_id:
            raise ValueError("user_id 是必需的，但未在任务参数中提供。请确保 API 请求包含 X-User-ID header。")
        
        # 构建请求参数
        generate_request = GenerateSheetRequest(**kwargs)
        
        # ========== [性能监控 - 可删除] ==========
        llm_start_time = time.time()
        
        # Step 1: 调用 LLM 生成函数（传递 user_id 用于数据隔离，必需参数）
        result = await generate_cheat_sheet(generate_request, user_id=user_id)
        
        # ========== [性能监控 - 可删除] ==========
        llm_elapsed = time.time() - llm_start_time
        print(f"⏱️ [性能监控] Step 1 - LLM 生成小抄内容耗时: {llm_elapsed:.2f} 秒")
        db_start_time = time.time()
        
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
        
        # ========== [性能监控 - 可删除] ==========
        db_elapsed = time.time() - db_start_time
        if metadata:
            print(f"⏱️ [性能监控] Step 2 - 保存到数据库耗时: {db_elapsed:.2f} 秒")

        clean_start_time = time.time()
        
        # Step 3: 清洗数据（清洗 LLM 返回的公式格式）
        cheat_sheet_dict = result.model_dump()
        clean_equation_data(cheat_sheet_dict)
        
        # ========== [性能监控 - 可删除] ==========
        clean_elapsed = time.time() - clean_start_time
        print(f"⏱️ [性能监控] Step 3 - 清洗数据耗时: {clean_elapsed:.2f} 秒")
        pdf_start_time = time.time()
        
        # Step 4: 生成 PDF（使用 React 前端渲染）
        # 直接将 CheatSheet 数据（字典格式）传给 PDF 服务
        # PDF 服务会访问 React 静态页面并注入数据
        pdf_bytes = await generate_pdf_via_browser(cheat_sheet_dict)
        
        # ========== [性能监控 - 可删除] ==========
        pdf_elapsed = time.time() - pdf_start_time
        print(f"⏱️ [性能监控] Step 4 - 生成 PDF 耗时: {pdf_elapsed:.2f} 秒")

        upload_start_time = time.time()
        
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
        
        # ========== [性能监控 - 可删除] ==========
        upload_elapsed = time.time() - upload_start_time
        print(f"⏱️ [性能监控] Step 5 - 上传到 MinIO 耗时: {upload_elapsed:.2f} 秒")
        
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
        
        # ========== [性能监控 - 可删除] ==========
        total_elapsed = time.time() - task_start_time
        print(f"⏱️ [性能监控] generate_cheat_sheet_task 总耗时: {total_elapsed:.2f} 秒")
        
        return result_data
    except Exception as e:
        # ========== [性能监控 - 可删除] ==========
        total_elapsed = time.time() - task_start_time
        print(f"⏱️ [性能监控] generate_cheat_sheet_task 失败，总耗时: {total_elapsed:.2f} 秒")
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
    # ========== [性能监控 - 可删除] ==========
    task_start_time = time.time()
    print(f"⏱️ [性能监控] generate_pdf_task 开始执行")
    
    try:
        if not cheat_sheet:
            raise ValueError("缺少 cheat_sheet 数据")
        
        # 验证数据格式（可选）
        cheat_sheet_obj = CheatSheetSchema(**cheat_sheet)
        
        # ========== [性能监控 - 可删除] ==========
        clean_start_time = time.time()
        
        # 清洗数据（清洗公式格式）
        clean_equation_data(cheat_sheet)
        
        # ========== [性能监控 - 可删除] ==========
        clean_elapsed = time.time() - clean_start_time
        print(f"⏱️ [性能监控] 清洗数据耗时: {clean_elapsed:.2f} 秒")
        pdf_start_time = time.time()
        
        # 生成 PDF（使用 React 前端渲染）
        # 直接将 CheatSheet 数据（字典格式）传给 PDF 服务
        pdf_bytes = await generate_pdf_via_browser(cheat_sheet)
        
        # ========== [性能监控 - 可删除] ==========
        pdf_elapsed = time.time() - pdf_start_time
        print(f"⏱️ [性能监控] 生成 PDF 耗时: {pdf_elapsed:.2f} 秒")
        upload_start_time = time.time()
        
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
        
        # ========== [性能监控 - 可删除] ==========
        upload_elapsed = time.time() - upload_start_time
        print(f"⏱️ [性能监控] 上传到 MinIO 耗时: {upload_elapsed:.2f} 秒")
        total_elapsed = time.time() - task_start_time
        print(f"⏱️ [性能监控] generate_pdf_task 总耗时: {total_elapsed:.2f} 秒")
        
        # 返回结果（包含 file_key）
        return {
            "status": "completed",
            "file_key": file_key,
            "size": len(pdf_bytes),
            "filename": filename
        }
    except Exception as e:
        # ========== [性能监控 - 可删除] ==========
        total_elapsed = time.time() - task_start_time
        print(f"⏱️ [性能监控] generate_pdf_task 失败，总耗时: {total_elapsed:.2f} 秒")
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
