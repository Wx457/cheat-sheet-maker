"""
任务状态查询 API
使用 ARQ Job 来查询任务状态和结果
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any
from arq.jobs import Job

from app.infrastructure.storage.minio_client import get_minio_client

router = APIRouter()


class TaskStatusResponse(BaseModel):
    """任务状态响应"""

    task_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    download_url: Optional[str] = None  # 预签名下载链接（如果任务完成且包含 file_key）


@router.get("/api/task/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(request: Request, task_id: str) -> TaskStatusResponse:
    """
    查询任务状态和结果

    Args:
        task_id: 任务 ID (ARQ job_id)

    Returns:
        任务状态信息
    """
    try:
        # 从应用状态获取 ARQ 连接池
        arq_pool = request.app.state.arq_pool

        # 创建 Job 对象
        job = Job(job_id=task_id, redis=arq_pool)

        # 获取任务状态
        status = await job.status()

        # ARQ 状态映射到我们的状态
        status_map = {
            "queued": "pending",
            "in_progress": "processing",
            "complete": "completed",
            "deferred": "pending",
            "not_found": "not_found",
        }

        mapped_status = status_map.get(status, status)

        # 如果任务完成，获取结果
        result = None
        error = None
        download_url = None

        if status == "complete":
            try:
                job_result = await job.result()
                result = job_result

                # 如果结果包含 file_key，生成预签名 URL
                if isinstance(result, dict) and result.get("file_key"):
                    file_key = result.get("file_key")
                    storage_client = get_minio_client()
                    download_url = storage_client.get_presigned_url(file_key)

                    # 将 download_url 添加到结果中
                    if download_url:
                        result["download_url"] = download_url
            except Exception as e:
                error = str(e)
        elif status == "not_found":
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

        return TaskStatusResponse(
            task_id=task_id,
            status=mapped_status,
            result=result,
            error=error,
            download_url=download_url,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询任务状态时发生错误: {str(e)}")
