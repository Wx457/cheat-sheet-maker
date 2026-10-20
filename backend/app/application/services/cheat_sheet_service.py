from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import List, Optional

import cohere as _cohere

from app.core.config import settings
from app.domain.prompts.templates import CheatSheetPrompts
from app.domain.rules.budget import BudgetRule
from app.infrastructure.llm.gemini_client import GeminiClient
from app.schemas import (
    ExamType,
    GenerateSheetRequest,
    OutlineResponse,
    TopicInput,
)
from app.domain.utils.cleaner import (
    clean_raw_text,
    escape_latex_backslashes,
    extract_json_objects,
    repair_json_string,
)
from app.infrastructure.rag.qdrant_store import QdrantVectorStore, get_qdrant_store

logger = logging.getLogger(__name__)

_cohere_client_instance: Optional[_cohere.ClientV2] = None


def _get_cohere_client() -> Optional[_cohere.ClientV2]:
    global _cohere_client_instance
    if _cohere_client_instance is None and settings.COHERE_API_KEY:
        _cohere_client_instance = _cohere.ClientV2(api_key=settings.COHERE_API_KEY)
    return _cohere_client_instance


@dataclass
class CheatSheetService:
    """Application Layer: Cheat sheet/outline generation orchestration service (use case-level workflow)"""

    gemini: GeminiClient
    rag_service: QdrantVectorStore

    @classmethod
    def default(cls) -> "CheatSheetService":
        return cls(
            gemini=GeminiClient(),
            rag_service=get_qdrant_store(),
        )

    async def _rerank_chunks(self, query: str, chunks: List[dict], top_n: int) -> List[dict]:
        """Rerank candidates with Cohere; falls back to original order if unavailable."""
        if not chunks or len(chunks) <= top_n:
            return chunks
        co = _get_cohere_client()
        if co is None:
            return chunks[:top_n]
        try:
            response = await asyncio.to_thread(
                lambda: co.rerank(
                    model="rerank-v3.5",
                    query=query,
                    documents=[c["content"] for c in chunks],
                    top_n=top_n,
                )
            )
            return [chunks[r.index] for r in response.results]
        except Exception as exc:
            logger.warning("Cohere rerank failed, using original order: %s", exc)
            return chunks[:top_n]

    # outline搜索：尽量保证最新batchid -> vector search+重试 -> fallback BM25查询
    async def _search_context_with_retry(
        self,
        query: str,
        user_id: str,
        k: int = 10,
        required_batch_id: Optional[str] = None,
    ) -> List[dict]:
        """Polling retry with exponential back-off for vector index consistency,
        plus a BM25 keyword fallback.

        Back-off schedule (base=RAG_RETRY_DELAY_SECONDS, default 2s):
            attempt 1 → 2s, attempt 2 → 4s, attempt 3 → 8s, …
        Capped at 30 s per wait.
        """
        max_attempts = settings.RAG_RETRY_ATTEMPTS
        base_delay = settings.RAG_RETRY_DELAY_SECONDS

        for attempt in range(1, max_attempts + 1):
            logger.info(
                "RAG retrieval attempt %d/%d for user_id=%s", attempt, max_attempts, user_id
            )

            if required_batch_id:
                batch_ready = await self.rag_service.is_batch_searchable(
                    query=query,
                    user_id=user_id,
                    ingest_batch_id=required_batch_id,
                )
                if not batch_ready:
                    logger.warning(
                        "Required batch not searchable on attempt %d/%d, user_id=%s, required_batch_id=%s",
                        attempt,
                        max_attempts,
                        user_id,
                        required_batch_id,
                    )
                    if attempt < max_attempts:
                        delay = min(base_delay * (2 ** (attempt - 1)), 30)
                        await asyncio.sleep(delay)
                    continue

            results = await self.rag_service.search_context(query, user_id=user_id, k=k)

            if results:
                logger.info(
                    "RAG retrieval succeeded on attempt %d/%d, chunks=%d, user_id=%s, required_batch_id=%s",
                    attempt,
                    max_attempts,
                    len(results),
                    user_id,
                    required_batch_id,
                )
                return results

            logger.warning(
                "RAG retrieval returned 0 chunks on attempt %d/%d for user_id=%s, required_batch_id=%s",
                attempt,
                max_attempts,
                user_id,
                required_batch_id,
            )
            # 仅当向量搜索返回0条时触发
            if attempt < max_attempts:
                delay = min(base_delay * (2 ** (attempt - 1)), 30)
                await asyncio.sleep(delay)

        # --- Fallback: BM25 keyword search (no vector index) ---
        logger.warning(
            "RAG vector search exhausted %d attempts; falling back to BM25 find for user_id=%s",
            max_attempts,
            user_id,
        )
        fallback = await asyncio.to_thread(self.rag_service.find_chunks_by_user, user_id, k, query)
        if fallback:
            logger.info("BM25 fallback returned %d chunks for user_id=%s", len(fallback), user_id)
        else:
            logger.warning("BM25 fallback also returned 0 chunks for user_id=%s", user_id)
        return fallback

    # outline生成：(区别处理outline搜索结果)扔给LLM生成大纲
    async def generate_outline(
        self,
        text: str,
        context: Optional[str] = None,
        exam_type: ExamType = ExamType.final,
        user_id: Optional[str] = None,
        ingest_batch_id: Optional[str] = None,
    ) -> OutlineResponse:
        """
        Generate outline (RAG retrieval supported)

        Args:
            text: User input text (e.g. syllabus)
            context: User background information (e.g. course name)
            exam_type: Exam type
            user_id: User ID (for data isolation during RAG retrieval)
        """
        cleaned_text = clean_raw_text(text)
        cleaned_context = clean_raw_text(context) if context else None
        degraded_reason: Optional[str] = None

        # RAG retrieval: retrieve relevant content from vector database
        rag_context_str = ""

        if user_id:
            query = cleaned_text
            results = await self._search_context_with_retry(
                query=query,
                user_id=user_id,
                k=15,
                required_batch_id=ingest_batch_id,
            )
            if ingest_batch_id and not results:
                degraded_reason = (
                    f"Batch {ingest_batch_id} was not searchable in retry window; "
                    "outline generated without batch-scoped RAG context."
                )
                logger.warning("Outline generation degraded: %s", degraded_reason)

            if results:
                results = await self._rerank_chunks(query, results, top_n=8)
                rag_context_str = "\n--- RAG Context from Vector Database ---\n"
                for r in results:
                    rag_context_str += f"Source: {r['source']}\n"
                    rag_context_str += f"Content: {r['content']}...\n"
                    rag_context_str += "---------------------------------------\n"
        else:
            raise ValueError("user_id is required for RAG retrieval")

        combined_context = (cleaned_context or "") + (
            "\n\n" + rag_context_str if rag_context_str else ""
        )

        prompt = CheatSheetPrompts.render_outline_prompt(
            cleaned_text, combined_context if combined_context else None, exam_type
        )

        # generate_text 是同步阻塞调用，放进线程避免卡住事件循环
        response_text = await asyncio.to_thread(self.gemini.generate_text, prompt)

        repaired = repair_json_string(response_text)
        data = json.loads(repaired)
        if degraded_reason:
            data["degraded_reason"] = degraded_reason
        return OutlineResponse(**data)

    async def stream_cheat_sheet_sections(
        self,
        request_data: "GenerateSheetRequest",
        user_id: str,
    ):
        """
        流式 Cheat Sheet 生成器，供 SSE 端点使用。
        Yields SSE 格式字符串（已含 "data: ...\n\n" 前缀）。

        """
        import asyncio
        import json as _json

        # 1) budget
        if not request_data.selected_topics:
            default_topics = [TopicInput(title="General Topics", relevance_score=1.0)]
            budget_map = BudgetRule.calculate(request_data.page_limit.value, default_topics)
            section_plan = "- General Topics (Target: ~{} items)".format(
                budget_map["General Topics"]
            )
        else:
            budget_map = BudgetRule.calculate(
                request_data.page_limit.value, request_data.selected_topics
            )
            section_plan = "\n".join(
                [
                    f"- {t.title} (Target: ~{budget_map.get(t.title, 3)} items)"
                    for t in request_data.selected_topics
                ]
            )

        total_items = sum(budget_map.values())

        # 2) RAG context
        rag_context_str = ""

        if request_data.selected_topics:
            search_tasks = [
                self.rag_service.search_context(topic.title, user_id=user_id, k=10)
                for topic in request_data.selected_topics
            ]
            all_results = await asyncio.gather(*search_tasks)

            seen = set()
            for topic, results in zip(request_data.selected_topics, all_results):
                if results:
                    results = await self._rerank_chunks(topic.title, results, top_n=3)
                    rag_context_str += f"\n--- Context for topic '{topic.title}' ---\n"
                    for r in results:
                        h = hash((r.get("content") or "").strip())
                        if h in seen:
                            continue
                        seen.add(h)
                        rag_context_str += f"Source: {r['source']}\n"
                        rag_context_str += f"Content: {r['content']}\n"
                        rag_context_str += "---------------------------------------\n"
        else:
            archetype = request_data.archetype.value if request_data.archetype else "general"
            query = request_data.user_context or archetype or "general knowledge"

            results = await self.rag_service.search_context(query, user_id=user_id, k=15)
            results = await self._rerank_chunks(query, results, top_n=8)

            if results:
                rag_context_str += "\n--- General Knowledge Base Context ---\n"
                for r in results:
                    rag_context_str += f"Source: {r['source']}\n"
                    rag_context_str += f"Content: {r['content']}\n"
                    rag_context_str += "---------------------------------------\n"

        # 3) prompt
        exam_type_context = {
            ExamType.quiz: "Quiz",
            ExamType.midterm: "Midterm",
            ExamType.final: "Final",
        }.get(request_data.exam_type, "Final")
        syllabus_instruction = ""
        if request_data.syllabus:
            cleaned_syllabus = clean_raw_text(request_data.syllabus)
            syllabus_instruction = f"""
            [Syllabus Filter Instruction]
            User provided the following syllabus as content filtering guide:
            {cleaned_syllabus}
            [End of Syllabus Filter Instruction]
            """
        topics_str = (
            "\n".join([f"- {t.title}" for t in request_data.selected_topics])
            if request_data.selected_topics
            else "未指定"
        )
        prompt = CheatSheetPrompts.render_cheatsheet_prompt(
            exam_type_context=exam_type_context,
            rag_context_str=rag_context_str,
            syllabus_instruction=syllabus_instruction,
            section_plan=section_plan,
            total_items=total_items,
            page_limit=request_data.page_limit.value,
            academic_level=request_data.academic_level.value,
            archetype=(request_data.archetype.value if request_data.archetype else "general"),
            selected_topics_str=topics_str,
        )

        # --- 步骤 4：流式 LLM 调用 + NDJSON 解析 ---
        buffer = ""

        # generate_text_stream 是同步生成器：生产者在线程池里跑，
        # 每拿到一个 chunk 就通过 call_soon_threadsafe 推入 asyncio.Queue，
        # 主协程边取边解析边 yield，不等整份生成结束。
        import threading

        loop = asyncio.get_running_loop()
        chunk_queue: asyncio.Queue = asyncio.Queue()
        stop_event = threading.Event()  # 客户端断开时通知生产者提前退出
        _SENTINEL = object()

        def _produce():
            try:
                for text in self.gemini.generate_text_stream(prompt):
                    if stop_event.is_set():
                        break
                    loop.call_soon_threadsafe(chunk_queue.put_nowait, text)
            except Exception as exc:  # 异常转交给主协程抛出
                loop.call_soon_threadsafe(chunk_queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(chunk_queue.put_nowait, _SENTINEL)

        # 不 await：队列创建后立即进入消费循环
        producer = loop.run_in_executor(None, _produce)

        # 从队列取 chunk，在缓冲区里按花括号配平切出完整的顶层 JSON 对象（不按换行切分）。
        # prompt 要求 NDJSON（每行一个完整 section），但 Gemini 实际输出并不稳定，观察到过：
        #   - 单行 NDJSON；多行缩进的对象；多个对象首尾相连；```json 围栏（结尾 ``` 可能粘在对象后）
        #   - 「扁平格式」：section header 和每条 item 各自是一个对象
        #       {"title": "EM Algorithm"}
        #       {"type": "text", "content": "..."}
        #   - LaTeX 单反斜杠（\(、\theta）
        # 解析器需将扁平格式的 items 归并到所属 section 后再 yield，同时兼容完整格式。
        current_section: dict | None = None

        def _try_yield_current():
            """将当前 section（已收集好 items）序列化为 SSE 行并返回，供 caller yield。"""
            if current_section is not None:
                return f"data: {_json.dumps(current_section)}\n\n"
            return None

        def _drain_buffer():
            """切出缓冲区中所有已完整的对象并处理，返回需要立即 yield 的 SSE 字符串列表。"""
            nonlocal buffer
            texts, buffer = extract_json_objects(buffer)
            to_yield = []
            for text in texts:
                try:
                    # 先修复 LaTeX 单反斜杠：否则整个 section 解析失败被丢弃，或公式被吞成制表符/换行。
                    # strict=False 容忍字符串内的原始换行。
                    obj = _json.loads(escape_latex_backslashes(text), strict=False)
                except _json.JSONDecodeError:
                    logger.warning("Dropped unparseable JSON object from LLM: %.200s", text)
                    continue
                to_yield.extend(_handle_object(obj))
            return to_yield

        def _handle_object(obj: dict):
            """
            根据结构分类：
              - meta          → 直接 yield
              - 完整格式（title + items）→ 先 yield 前一个 section，再 yield 本对象
              - section header（有 title，无 type）→ 先 yield 前一个 section，开始新 section
              - item（有 type + content）→ 追加到当前 section 的 items
              - {"sections": [...]} 包裹对象（prompt 禁止但可能出现）→ 逐个处理
            """
            nonlocal current_section
            to_yield = []

            if isinstance(obj.get("sections"), list):
                for section in obj["sections"]:
                    if isinstance(section, dict):
                        to_yield.extend(_handle_object(section))
                return to_yield

            # ── meta 行 ────────────────────────────────────────────────
            if obj.get("_type") == "meta":
                to_yield.append(f"data: {_json.dumps(obj)}\n\n")
                return to_yield

            # ── 完整格式：title + items 在同一行 ────────────────────────
            if "title" in obj and "items" in obj:
                ev = _try_yield_current()
                if ev:
                    to_yield.append(ev)
                current_section = None
                to_yield.append(f"data: {_json.dumps(obj)}\n\n")
                return to_yield

            # ── section header（扁平格式）：有 title，无 type ────────────
            if "title" in obj and "type" not in obj:
                ev = _try_yield_current()
                if ev:
                    to_yield.append(ev)
                current_section = {"title": obj["title"], "items": []}
                return to_yield

            # ── item（扁平格式）：有 type + content ─────────────────────
            if "type" in obj and "content" in obj:
                if current_section is not None:
                    current_section["items"].append(obj)
                # 若没有当前 section，作为孤儿 item 忽略
                return to_yield

            return to_yield

        try:
            while True:
                chunk_text = await chunk_queue.get()
                if chunk_text is _SENTINEL:
                    break
                if isinstance(chunk_text, Exception):
                    raise chunk_text
                buffer += chunk_text
                for sse in _drain_buffer():
                    yield sse
        finally:
            # 正常结束 / 客户端断开（GeneratorExit）/ 异常，都让生产者线程尽快停止
            stop_event.set()
        await producer

        if buffer.strip():
            # 流结束时仍有未闭合的对象（输出被截断，如超出 max tokens）
            logger.warning("LLM stream ended with an incomplete JSON object: %.200s", buffer)

        # 最后 flush 尚未 yield 的 section
        ev = _try_yield_current()
        if ev:
            yield ev

        yield "data: [DONE]\n\n"
