import json
import os
from typing import Optional

import google.generativeai as genai
from dotenv import load_dotenv

from app.core.config import settings
from app.infrastructure.llm.retry_utils import run_with_exponential_backoff

load_dotenv()

# TODO: re-enable response_schema enforcement after upgrading to google-genai (new SDK).
# google-generativeai==0.8.6 rejects Pydantic v2 schemas that contain "default" fields
# (generated for Optional / default-valued fields). The conversion helpers below were
# written to strip those unsupported fields, but the SDK's internal proto conversion
# path still surfaces the error. Disabled until SDK migration.
#
# import copy
# from typing import Type
#
# _STRIP_KEYS = {"default", "title", "$schema", "$defs"}
#
# def _resolve_refs(obj, defs):
#     if "$ref" in obj:
#         ref_name = obj["$ref"].split("/")[-1]
#         return _resolve_refs(copy.deepcopy(defs.get(ref_name, {})), defs)
#     result = {}
#     for k, v in obj.items():
#         if k == "$defs":
#             continue
#         result[k] = _resolve_refs_in(v, defs)
#     return result
#
# def _resolve_refs_in(v, defs):
#     if isinstance(v, dict):  return _resolve_refs(v, defs)
#     if isinstance(v, list):  return [_resolve_refs_in(i, defs) for i in v]
#     return v
#
# def _convert_any_of(obj):
#     """anyOf: [{type: X}, {type: null}]  →  {type: X, nullable: true}"""
#     if "anyOf" not in obj:  return obj
#     parts = obj["anyOf"]
#     non_null = [p for p in parts if p.get("type") != "null"]
#     has_null  = any(p.get("type") == "null" for p in parts)
#     if has_null and len(non_null) == 1:
#         result = {**non_null[0], "nullable": True}
#         for k, v in obj.items():
#             if k != "anyOf":  result[k] = v
#         return result
#     return obj
#
# def _clean(obj):
#     if isinstance(obj, dict):
#         obj = _convert_any_of(obj)
#         return {k: _clean(v) for k, v in obj.items() if k not in _STRIP_KEYS}
#     if isinstance(obj, list):  return [_clean(i) for i in obj]
#     return obj
#
# def _pydantic_to_gemini_schema(model_cls: Type) -> dict:
#     raw  = model_cls.model_json_schema()
#     defs = raw.get("$defs", {})
#     return _clean(_resolve_refs(raw, defs))


class GeminiClient:
    """Gemini 文本/JSON 生成客户端，封装模型配置与重试。"""

    def __init__(self, model_name: str = "gemini-2.5-flash"):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment variables")
        genai.configure(api_key=api_key)
        self.model_name = model_name
        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={"response_mime_type": "application/json"},
        )

    def _call(self, prompt: str):
        def _wrapped():
            try:
                # TODO: restore response_schema support after SDK migration to google-genai.
                # generation_config = {
                #     "response_mime_type": "application/json",
                #     "response_schema": _pydantic_to_gemini_schema(response_schema),
                # }
                # return self.model.generate_content(prompt, generation_config=generation_config)
                return self.model.generate_content(prompt)
            except Exception as exc:  # noqa: PERF203
                if "timeout" in str(exc).lower() or "deadline" in str(exc).lower():
                    raise TimeoutError(
                        f"请求超时（超过 {settings.LLM_REQUEST_TIMEOUT_SECONDS} 秒）"
                    ) from exc
                raise

        return run_with_exponential_backoff("Gemini generate_content", _wrapped)

    def generate_text(self, prompt: str, response_schema: Optional[object] = None) -> str:
        """Generate text. response_schema is accepted but ignored until SDK migration.

        TODO: re-enable schema enforcement after upgrading to google-genai.
        """
        # TODO: pass response_schema to _call once _pydantic_to_gemini_schema is re-enabled.
        _ = response_schema
        response = self._call(prompt)
        return response.text

    def generate_text_stream(self, prompt: str):
        """同步流式生成器，逐 chunk 返回文本片段。

        注意：
        - 不支持 response_schema（与流式 API 不兼容），格式约束改由 prompt 工程承担。
        - 显式覆盖 response_mime_type 为 text/plain，避免模型在 JSON 模式下
          缓冲完整响应再一次性吐出（会破坏流式效果）。
        - google-generativeai 0.8.x 移除了 generate_content_stream()，
          改为 generate_content(stream=True) 实现流式输出。
        """
        stream = self.model.generate_content(
            prompt,
            stream=True,
            generation_config={"response_mime_type": "text/plain"},
        )
        for chunk in stream:
            # 流末尾常有只带 finish_reason、没有 Part 的 chunk；此时 .text 会抛 ValueError
            # （hasattr 只吞 AttributeError，拦不住），直接跳过，避免整个流在结尾崩掉。
            try:
                text = chunk.text
            except ValueError:
                continue
            if text:
                yield text

    def generate_json(self, prompt: str) -> dict:
        response_text = self.generate_text(prompt)
        try:
            return json.loads(response_text)
        except json.JSONDecodeError as exc:
            print(f"❌ JSON Decode Error in GeminiClient: {exc}")
            raise
