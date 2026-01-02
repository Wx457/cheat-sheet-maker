import asyncio
import io
from typing import List
from pymongo import MongoClient
from pypdf import PdfReader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_mongodb import MongoDBAtlasVectorSearch

from app.core.config import settings


class RAGService:
    """RAG 服务类，负责文本摄入和向量化存储"""
    
    def __init__(self):
        """初始化 MongoDB 连接和 Embeddings"""
        # 验证 MongoDB 配置（不再需要 Google API Key）
        if not settings.MONGODB_URI:
            raise ValueError("MONGODB_URI 未在环境变量中设置")
        
        # 初始化 MongoDB 客户端
        self.client = MongoClient(settings.MONGODB_URI)
        self.db = self.client[settings.DB_NAME]
        self.collection = self.db[settings.COLLECTION_NAME]
        
        # 初始化 HuggingFace Embeddings（本地模型，768 维度，兼容 MongoDB 现有配置）
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-mpnet-base-v2",
            model_kwargs={'device': 'cuda'}
        )
        
        # 初始化文本分割器
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
    
    async def ingest_text(self, raw_text: str, source_name: str) -> int:
        """
        将原始文本摄入到 MongoDB Atlas Vector Search
        
        使用本地 HuggingFace 模型，无需限速。
        
        Args:
            raw_text: 原始文本内容
            source_name: 数据源名称（用于 metadata）
            
        Returns:
            摄入的文档块数量
        """
        # 1. 使用 RecursiveCharacterTextSplitter 切分文本
        chunks = self.text_splitter.split_text(raw_text)
        
        # 2. 转换为 Document 对象，添加 metadata
        documents = [
            Document(
                page_content=chunk,
                metadata={"source": source_name}
            )
            for chunk in chunks
        ]
        
        # 3. 初始化 vector_store
        vector_store = MongoDBAtlasVectorSearch(
            collection=self.collection,
            embedding=self.embeddings,
            index_name="default"
        )
        
        # 4. 一次性添加所有文档（本地模型，无需限速）
        await asyncio.to_thread(
            vector_store.add_documents,
            documents
        )
        
        return len(documents)
    
    async def ingest_pdf(self, file_content: bytes, filename: str) -> int:
        """
        将 PDF 文件摄入到 MongoDB Atlas Vector Search
        
        读取 PDF 文件内容，提取文本后调用 ingest_text 进行切片和存储。
        
        Args:
            file_content: PDF 文件的二进制内容
            filename: 文件名（用作数据源名称）
            
        Returns:
            摄入的文档块数量
        """
        # 使用 PdfReader 读取 PDF
        pdf_reader = PdfReader(io.BytesIO(file_content))
        
        # 遍历每一页提取文本，拼接成大的 raw_text
        raw_text = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                raw_text += page_text + "\n"
        
        # 复用现有的 ingest_text 逻辑完成切片和存储
        chunks_count = await self.ingest_text(raw_text, source_name=filename)
        
        return chunks_count
    
    def _get_vector_store(self) -> MongoDBAtlasVectorSearch:
        """获取 vector_store 实例（用于检索）"""
        return MongoDBAtlasVectorSearch(
            collection=self.collection,
            embedding=self.embeddings,
            index_name="default"
        )
    
    async def search_context(self, query: str, k: int = 5) -> List[dict]:
        """
        根据 query 在向量库中搜索最相关的 k 个片段。
        
        Args:
            query: 查询文本
            k: 返回最相关的 k 个结果（默认 5）
            
        Returns:
            List[dict]: 包含 content, source, score 的字典列表
        """
        # 获取 vector_store 实例
        vector_store = self._get_vector_store()
        
        # 使用 similarity_search_with_score 进行相似度搜索
        results = await asyncio.to_thread(
            vector_store.similarity_search_with_score,
            query,
            k=k
        )
        
        # 格式化返回结果
        return [
            {
                "content": doc.page_content,
                "source": doc.metadata.get("source", "unknown"),
                "score": float(score)  # 确保 score 是 float 类型
            }
            for doc, score in results
        ]
    
    def close(self):
        """关闭 MongoDB 连接"""
        if self.client:
            self.client.close()


# 创建全局 RAG 服务实例
_rag_service: RAGService | None = None


def get_rag_service() -> RAGService:
    """获取 RAG 服务实例（单例模式）"""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service

