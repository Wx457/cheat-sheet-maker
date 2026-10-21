import traceback
from datetime import datetime

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.application.services.ingestion_service import IngestionService
from app.core.auth import CurrentUserId, require_admin
from app.infrastructure.rag.qdrant_store import QuotaExceededError

router = APIRouter()


class IngestRequest(BaseModel):
    """文本摄入请求模型"""

    text: str
    source: str


class IngestResponse(BaseModel):
    """文本摄入响应模型"""

    status: str
    chunks_count: int
    ingest_batch_id: str
    ingest_at: datetime
    truncated: bool = False
    original_chunks_count: int = 0


class SearchRequest(BaseModel):
    """搜索请求模型"""

    query: str
    top_k: int = 3


class SearchResult(BaseModel):
    """搜索结果项模型"""

    content: str
    source: str
    score: float


class SearchResponse(BaseModel):
    """搜索响应模型"""

    status: str
    results: list[SearchResult]


class ClearResponse(BaseModel):
    """清理响应模型"""

    status: str
    deleted_count: int


class ChunkCountResponse(BaseModel):
    """Chunks 数量响应模型"""

    status: str
    chunks_count: int


@router.get("/chunks/count", response_model=ChunkCountResponse)
async def get_chunk_count(
    user_id: CurrentUserId,
) -> ChunkCountResponse:
    """
    获取当前用户的 chunks 数量

    用于前端同步显示最新的 chunks 数量。
    """
    try:
        ingestion = IngestionService.default()
        chunks_count = ingestion.rag_service.get_user_chunk_count(user_id)

        return ChunkCountResponse(status="success", chunks_count=chunks_count)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取 chunks 数量时发生错误: {str(e)}")


@router.post("/ingest", response_model=IngestResponse)
async def ingest_text(
    user_id: CurrentUserId,
    payload: IngestRequest = Body(...),
) -> IngestResponse:
    """
    将文本摄入到 RAG 知识库

    接收原始文本，切分后存入 Qdrant 向量库。
    """
    try:
        ingestion = IngestionService.default()
        ingest_result = await ingestion.process_text(
            text=payload.text,
            metadata={"source": payload.source},
            user_id=user_id,
        )

        return IngestResponse(
            status="truncated" if ingest_result["truncated"] else "success",
            chunks_count=ingest_result["chunks_count"],
            ingest_batch_id=ingest_result["ingest_batch_id"],
            ingest_at=ingest_result["ingest_at"],
            truncated=ingest_result["truncated"],
            original_chunks_count=ingest_result["original_chunks_count"],
        )
    except QuotaExceededError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"文本摄入时发生错误: {str(e)}")


@router.post("/search", response_model=SearchResponse)
async def search_context(
    user_id: CurrentUserId,
    payload: SearchRequest = Body(...),
) -> SearchResponse:
    """
    在 RAG 知识库中搜索相关内容

    根据查询文本，返回最相关的文档片段。
    """
    try:
        ingestion = IngestionService.default()
        results = await ingestion.rag_service.search_context(
            query=payload.query, user_id=user_id, k=payload.top_k
        )

        # 转换为 SearchResult 对象列表
        search_results = [SearchResult(**result) for result in results]

        return SearchResponse(status="success", results=search_results)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"搜索时发生错误: {str(e)}")


@router.post("/ingest/file", response_model=IngestResponse)
async def ingest_file(
    user_id: CurrentUserId,
    file: UploadFile = File(...),
) -> IngestResponse:
    """
    将 PDF 文件摄入到 RAG 知识库

    接收 PDF 文件，提取文本后切分并存入 Qdrant 向量库。
    """
    try:
        # 读取文件内容
        content = await file.read()

        # 验证文件类型（可选，但建议添加）
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="仅支持 PDF 文件格式")

        ingestion = IngestionService.default()
        ingest_result = await ingestion.process_file(
            file_content=content,
            filename=file.filename or "unknown.pdf",
            user_id=user_id,
        )

        return IngestResponse(
            status="truncated" if ingest_result["truncated"] else "success",
            chunks_count=ingest_result["chunks_count"],
            ingest_batch_id=ingest_result["ingest_batch_id"],
            ingest_at=ingest_result["ingest_at"],
            truncated=ingest_result["truncated"],
            original_chunks_count=ingest_result["original_chunks_count"],
        )
    except HTTPException:
        raise
    except QuotaExceededError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"文件摄入时发生错误: {str(e)}")


@router.delete("/chunks", response_model=ClearResponse)
async def delete_user_chunks(
    user_id: CurrentUserId,
) -> ClearResponse:
    """
    删除当前用户的知识库向量数据（用户级操作）。

    仅删除当前登录用户的 chunks（及其 Supabase ingest 批次记录），不影响其他用户数据。
    供 Chrome 插件的 "Clear KB" 按钮调用。
    """
    try:
        ingestion = IngestionService.default()
        deleted_count = await ingestion.delete_user_data(user_id)
        return ClearResponse(status="success", deleted_count=int(deleted_count))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"删除用户知识库时发生错误: {str(e)}")


@router.post("/clear", response_model=ClearResponse, dependencies=[Depends(require_admin)])
async def clear_vector_data() -> ClearResponse:
    """
    清理所有向量数据（重置 Qdrant collection）。

    注意：此操作会删除所有用户的向量数据，仅 ADMIN_USER_IDS 中的 Clerk 用户可调用（为空则一律 403）。
    """
    try:
        ingestion = IngestionService.default()
        deleted_count = ingestion.rag_service.clear_vector_data()

        return ClearResponse(status="success", deleted_count=deleted_count)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"清理向量数据时发生错误: {str(e)}")
