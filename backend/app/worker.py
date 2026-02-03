"""
ARQ Worker 进程
监听 Redis 队列，执行耗时的 LLM 和 PDF 生成任务
"""
import traceback
import time
from typing import Dict, Any

from arq.connections import RedisSettings
from arq.worker import Worker

from app.application.services.cheat_sheet_service import CheatSheetService
from app.schemas import GenerateSheetRequest, ExamType
from app.core.config import settings


# ARQ 任务函数定义

async def generate_outline_task(
    ctx,
    raw_text: str,
    user_context: str = None,
    exam_type: str = "final",
    user_id: str = None  # 必需，用于 RAG 检索时的数据隔离
) -> Dict[str, Any]:
    """
    ARQ 任务：生成大纲（优化版：支持 RAG 检索）
    
    Args:
        ctx: ARQ 上下文
        raw_text: 原始文本（通常是大纲或课程描述）
        user_context: 用户背景信息（如课程名称）
        exam_type: 考试类型
        user_id: 用户 ID（必需，用于 RAG 检索时的数据隔离）
        
    Returns:
        任务结果
    """

    try:
        exam_type_enum = ExamType(exam_type)
        
        if not user_id:
            print(f"⚠️ [WARNING] generate_outline_task - user_id not provided, RAG retrieval will be skipped")
        
        service = CheatSheetService.default()
        result = await service.generate_outline(text=raw_text, context=user_context, exam_type=exam_type_enum, user_id=user_id)
        
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
    1. LLM 生成小抄内容（内部使用并行 MMR 检索 + 去重优化）
    2. 保存到数据库（如果包含 _metadata）
    3. 清洗数据（清洗公式格式）
    4. 生成 PDF（使用 React 前端渲染）
    5. 上传到 S3
    6. 返回包含 file_key 的结果
    
    注意：RAG 检索优化（并行 MMR + 去重）在 generate_cheat_sheet() 函数内部实现。
    
    Args:
        ctx: ARQ 上下文
        **kwargs: GenerateSheetRequest 的所有字段，可能包含 _metadata
        
    Returns:
        任务结果（包含 file_key 和 project_id）
    """

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
        
        service = CheatSheetService.default()
        result_data = await service.create_cheat_sheet_flow(generate_request, user_id=user_id, metadata=metadata)
        
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
    ARQ 任务：生成 PDF 并上传到 S3
    
    Args:
        ctx: ARQ 上下文
        cheat_sheet: 小抄数据字典
        
    Returns:
        任务结果（包含 file_key）
    """
    raise NotImplementedError("generate_pdf_task 已弃用：请使用 create_cheat_sheet_flow 统一流程。")


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
    ]
    
    # Worker 配置
    max_jobs = 10  # 最大并发任务数
    job_timeout = 600  # 任务超时时间（秒）
    keep_result = 86400  # 结果保留时间（24小时）


# 启动和关闭钩子（可选）

async def startup(ctx):
    """Worker 启动时执行"""

    print("🚀 ARQ Worker launching...")
    # 触发依赖初始化（如存储桶检查）
    _ = CheatSheetService.default()
    from app.infrastructure.storage.minio_client import get_minio_client
    get_minio_client()  # 这会自动调用 ensure_bucket()


async def shutdown(ctx):
    """Worker 关闭时执行"""
    print("👋 ARQ Worker closing...")


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
