import traceback
from datetime import datetime

from fastapi import APIRouter, Body, File, HTTPException, UploadFile, Header
from pydantic import BaseModel

from app.application.services.ingestion_service import IngestionService


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
    x_user_id: str = Header(..., alias="X-User-ID", description="用户 ID（必需，用于数据隔离）")
) -> ChunkCountResponse:
    """
    获取当前用户的 chunks 数量
    
    用于前端同步显示最新的 chunks 数量。
    """
    try:
        ingestion = IngestionService.default()
        chunks_count = ingestion.rag_service.get_user_chunk_count(x_user_id)
        
        return ChunkCountResponse(
            status="success",
            chunks_count=chunks_count
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"获取 chunks 数量时发生错误: {str(e)}"
        )


@router.post("/ingest", response_model=IngestResponse)
async def ingest_text(
    payload: IngestRequest = Body(...),
    x_user_id: str = Header(..., alias="X-User-ID", description="用户 ID（必需，用于数据隔离）")
) -> IngestResponse:
    """
    将文本摄入到 RAG 知识库
    
    接收原始文本，切分后存入 MongoDB Atlas Vector Search。
    """
    try:
        ingestion = IngestionService.default()
        ingest_result = await ingestion.process_text(
            text=payload.text,
            metadata={"source": payload.source},
            user_id=x_user_id,
        )
        
        return IngestResponse(
            status="success",
            chunks_count=ingest_result["chunks_count"],
            ingest_batch_id=ingest_result["ingest_batch_id"],
            ingest_at=ingest_result["ingest_at"],
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"文本摄入时发生错误: {str(e)}"
        )


@router.post("/search", response_model=SearchResponse)
async def search_context(
    payload: SearchRequest = Body(...),
    x_user_id: str = Header(..., alias="X-User-ID", description="用户 ID（必需，用于数据隔离）")
) -> SearchResponse:
    """
    在 RAG 知识库中搜索相关内容
    
    根据查询文本，返回最相关的文档片段。
    """
    try:
        ingestion = IngestionService.default()
        results = await ingestion.rag_service.search_context(
            query=payload.query,
            user_id=x_user_id,
            k=payload.top_k
        )
        
        # 转换为 SearchResult 对象列表
        search_results = [
            SearchResult(**result) for result in results
        ]
        
        return SearchResponse(
            status="success",
            results=search_results
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"搜索时发生错误: {str(e)}"
        )


@router.post("/ingest/file", response_model=IngestResponse)
async def ingest_file(
    file: UploadFile = File(...),
    x_user_id: str = Header(..., alias="X-User-ID", description="用户 ID（必需，用于数据隔离）")
) -> IngestResponse:
    """
    将 PDF 文件摄入到 RAG 知识库
    
    接收 PDF 文件，提取文本后切分并存入 MongoDB Atlas Vector Search。
    """
    try:
        # 读取文件内容
        content = await file.read()
        
        # 验证文件类型（可选，但建议添加）
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            raise HTTPException(
                status_code=400,
                detail="仅支持 PDF 文件格式"
            )
        
        ingestion = IngestionService.default()
        ingest_result = await ingestion.process_file(
            file_content=content,
            filename=file.filename or "unknown.pdf",
            user_id=x_user_id,
        )
        
        return IngestResponse(
            status="success",
            chunks_count=ingest_result["chunks_count"],
            ingest_batch_id=ingest_result["ingest_batch_id"],
            ingest_at=ingest_result["ingest_at"],
        )
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"文件摄入时发生错误: {str(e)}"
        )


@router.post("/clear", response_model=ClearResponse)
async def clear_vector_data() -> ClearResponse:
    """
    清理 MongoDB 中的旧向量数据
    
    由于模型从 HuggingFace (768 维) 更换为 OpenAI (1536 维)，
    旧的向量数据必须清除，否则会报维度不匹配错误。
    
    注意：此操作会删除所有向量数据，请谨慎使用。
    """
    try:
        ingestion = IngestionService.default()
        deleted_count = ingestion.rag_service.clear_vector_data()
        
        return ClearResponse(
            status="success",
            deleted_count=deleted_count
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"清理向量数据时发生错误: {str(e)}"
        )

