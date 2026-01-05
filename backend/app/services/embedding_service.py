import os
import numpy as np
from typing import List
from openai import OpenAI
from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings

# 加载环境变量
load_dotenv()

# 初始化客户端
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_embedding(text: str) -> list[float]:
    """
    调用 OpenAI API 将文本转换为向量。
    使用 'text-embedding-3-small' 模型 (性价比最高，维度 1536)。
    """
    # 简单的清洗，去除换行符，防止 API 报错
    text = text.replace("\n", " ")
    
    try:
        response = client.embeddings.create(
            input=[text],
            model="text-embedding-3-small" 
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"OpenAI Embedding Error: {e}")
        # 出错时返回空列表或抛出异常，视你业务逻辑而定
        return []


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """
    批量调用 OpenAI API 将多个文本转换为向量。
    使用 'text-embedding-3-small' 模型 (性价比最高，维度 1536)。
    
    Args:
        texts: 文本列表
        
    Returns:
        向量列表，每个元素是一个 1536 维的向量
    """
    if not texts:
        return []
    
    # 清洗文本，去除换行符
    cleaned_texts = [text.replace("\n", " ") for text in texts]
    
    try:
        response = client.embeddings.create(
            input=cleaned_texts,
            model="text-embedding-3-small"
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        print(f"OpenAI Embedding Error: {e}")
        # 出错时返回空列表
        return []

def compute_similarity(embedding1: list[float], embedding2: list[float]) -> float:
    """
    计算两个向量的余弦相似度
    """
    if not embedding1 or not embedding2:
        return 0.0
        
    # 转为 numpy 数组进行计算
    vec1 = np.array(embedding1)
    vec2 = np.array(embedding2)
    
    # 计算余弦相似度: (A . B) / (|A| * |B|)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
        
    return float(np.dot(vec1, vec2) / (norm1 * norm2))


class OpenAIEmbeddings(Embeddings):
    """
    LangChain Embeddings 适配器，包装 OpenAI embedding 服务。
    用于与 LangChain 的向量存储（如 MongoDBAtlasVectorSearch）集成。
    """
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        批量嵌入文档文本
        
        Args:
            texts: 文本列表
            
        Returns:
            向量列表，每个元素是一个 1536 维的向量
        """
        return get_embeddings(texts)
    
    def embed_query(self, text: str) -> List[float]:
        """
        嵌入单个查询文本
        
        Args:
            text: 查询文本
            
        Returns:
            1536 维的向量
        """
        return get_embedding(text)