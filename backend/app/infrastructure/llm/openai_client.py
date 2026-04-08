import logging
import os
import time
from typing import List

from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from openai import OpenAI

from app.core.config import settings
from app.infrastructure.llm.retry_utils import run_with_exponential_backoff

load_dotenv()
logger = logging.getLogger(__name__)


class OpenAIClient(Embeddings):
    """OpenAI Embedding client, compatible with LangChain Embeddings interface.

    Large input lists are automatically split into sub-batches of size
    ``EMBEDDING_BATCH_SIZE`` with a configurable inter-batch delay to
    stay below the provider's rate limit.
    """

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
        self.batch_size = settings.EMBEDDING_BATCH_SIZE
        self.batch_delay = settings.EMBEDDING_BATCH_DELAY_SECONDS

    def _embed_batch(self, cleaned_texts: List[str]) -> List[List[float]]:
        """Call the OpenAI API for a single batch (with exponential-backoff retry)."""
        response = run_with_exponential_backoff(
            "OpenAI embeddings.create (documents)",
            lambda: self.client.embeddings.create(input=cleaned_texts, model=self.model),
        )
        return [item.embedding for item in response.data]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        cleaned = [text.replace("\n", " ") for text in texts]

        if len(cleaned) <= self.batch_size:
            return self._embed_batch(cleaned)

        all_embeddings: List[List[float]] = []
        total_batches = (len(cleaned) + self.batch_size - 1) // self.batch_size

        for i in range(0, len(cleaned), self.batch_size):
            batch = cleaned[i : i + self.batch_size]
            batch_idx = i // self.batch_size + 1
            logger.info(
                "Embedding sub-batch %d/%d (%d texts)", batch_idx, total_batches, len(batch)
            )
            all_embeddings.extend(self._embed_batch(batch))

            if i + self.batch_size < len(cleaned) and self.batch_delay > 0:
                time.sleep(self.batch_delay)

        return all_embeddings

    def embed_query(self, text: str) -> List[float]:
        text = text.replace("\n", " ")
        response = run_with_exponential_backoff(
            "OpenAI embeddings.create (query)",
            lambda: self.client.embeddings.create(input=[text], model=self.model),
        )
        return response.data[0].embedding

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        return self.embed_documents(texts)
