import os
from typing import List

from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from openai import OpenAI

from app.core.config import settings
from app.infrastructure.llm.retry_utils import run_with_exponential_backoff

load_dotenv()


class OpenAIClient(Embeddings):
    """OpenAI Embedding 客户端，兼容 LangChain Embeddings 接口。"""

    def __init__(self, model: str = "text-embedding-3-small"):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        self.client = OpenAI(
            api_key=api_key,
            timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
        )
        self.model = model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        cleaned = [text.replace("\n", " ") for text in texts]
        response = run_with_exponential_backoff(
            "OpenAI embeddings.create (documents)",
            lambda: self.client.embeddings.create(input=cleaned, model=self.model),
        )
        return [item.embedding for item in response.data]

    def embed_query(self, text: str) -> List[float]:
        text = text.replace("\n", " ")
        response = run_with_exponential_backoff(
            "OpenAI embeddings.create (query)",
            lambda: self.client.embeddings.create(input=[text], model=self.model),
        )
        return response.data[0].embedding

    # 兼容旧接口
    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        return self.embed_documents(texts)
