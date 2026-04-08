import json
import os

import google.generativeai as genai
from dotenv import load_dotenv

from app.core.config import settings
from app.infrastructure.llm.retry_utils import run_with_exponential_backoff

load_dotenv()


class GeminiClient:
    """Gemini 文本/JSON 生成客户端，封装模型配置与重试。"""

    def __init__(self, model_name: str = "gemini-2.5-flash"):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment variables")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={"response_mime_type": "application/json"},
        )

    def _call(self, prompt: str):
        def _wrapped():
            try:
                return self.model.generate_content(prompt)
            except Exception as exc:  # noqa: PERF203
                if "timeout" in str(exc).lower() or "deadline" in str(exc).lower():
                    raise TimeoutError(
                        f"请求超时（超过 {settings.LLM_REQUEST_TIMEOUT_SECONDS} 秒）"
                    ) from exc
                raise

        return run_with_exponential_backoff("Gemini generate_content", _wrapped)

    def generate_text(self, prompt: str) -> str:
        response = self._call(prompt)
        return response.text

    def generate_json(self, prompt: str) -> dict:
        response_text = self.generate_text(prompt)
        try:
            return json.loads(response_text)
        except json.JSONDecodeError as exc:
            print(f"❌ JSON Decode Error in GeminiClient: {exc}")
            raise
