import json
import os
import time
from typing import Any, Callable, Optional

import google.generativeai as genai
from dotenv import load_dotenv
from google.api_core import exceptions

load_dotenv()

MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1
MAX_RETRY_DELAY = 60
REQUEST_TIMEOUT = 120


def _is_retryable_error(exception: Exception) -> bool:
    error_str = str(exception).lower()
    if any(k in error_str for k in ["resource exhausted", "rate limit", "quota exceeded", "429"]):
        return True
    if any(k in error_str for k in ["service unavailable", "503", "unavailable", "temporarily unavailable"]):
        return True
    if any(k in error_str for k in ["timeout", "deadline exceeded", "504"]):
        return True
    return False


def _exponential_backoff_retry(func: Callable[[], Any]) -> Any:
    last_exception: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            return func()
        except Exception as exc:  # noqa: PERF203
            last_exception = exc
            if not _is_retryable_error(exc) or attempt == MAX_RETRIES - 1:
                raise
            delay = min(INITIAL_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
            print(f"⚠️ Gemini 调用失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {exc}")
            print(f"⏳ 等待 {delay} 秒后重试...")
            time.sleep(delay)
    raise last_exception  # 理论上不会到达


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
                    raise TimeoutError(f"请求超时（超过 {REQUEST_TIMEOUT} 秒）") from exc
                raise

        return _exponential_backoff_retry(_wrapped)

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
        except exceptions.ResourceExhausted as exc:
            raise ValueError(f"API 配额已用尽，请稍后重试。错误详情: {exc}") from exc
        except exceptions.ServiceUnavailable as exc:
            raise ValueError(f"服务暂时不可用，请稍后重试。错误详情: {exc}") from exc

