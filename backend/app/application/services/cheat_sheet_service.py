from __future__ import annotations

import asyncio
import json
import logging
import threading
from contextlib import aclosing
from dataclasses import dataclass
from typing import AsyncIterator, List, Optional

import cohere as _cohere

from app.core.config import settings
from app.domain.prompts.templates import CheatSheetPrompts
from app.domain.rules.budget import BudgetRule
from app.infrastructure.llm.gemini_client import GeminiClient
from app.schemas import (
    ExamType,
    GenerateSheetRequest,
    OutlineResponse,
    RegenerateSectionsRequest,
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
        course_id: Optional[str] = None,
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

            results = await self.rag_service.search_context(
                query, user_id=user_id, k=k, course_id=course_id
            )

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
        fallback = await asyncio.to_thread(
            self.rag_service.find_chunks_by_user, user_id, k, query, course_id
        )
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
        course_id: Optional[str] = None,
    ) -> OutlineResponse:
        """
        Generate outline (RAG retrieval supported)

        Args:
            text: User input text (e.g. syllabus)
            context: User background information (e.g. course name)
            exam_type: Exam type
            user_id: User ID (for data isolation during RAG retrieval)
            course_id: Only retrieve this course's chunks (None = all of the user's chunks)
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
                course_id=course_id,
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

        # 2) RAG context（第 8 点：只检索该课程的知识库；None = 该用户全部）
        rag_context_str = ""
        course_id = str(request_data.course_id) if request_data.course_id else None

        if request_data.selected_topics:
            rag_context_str = await self._topic_context(
                [t.title for t in request_data.selected_topics], user_id, course_id
            )
        else:
            archetype = request_data.archetype.value if request_data.archetype else "general"
            query = request_data.user_context or archetype or "general knowledge"

            results = await self.rag_service.search_context(
                query, user_id=user_id, k=15, course_id=course_id
            )
            results = await self._rerank_chunks(query, results, top_n=8)

            if results:
                rag_context_str += "\n--- General Knowledge Base Context ---\n"
                for r in results:
                    rag_context_str += f"Source: {r['source']}\n"
                    rag_context_str += f"Content: {r['content']}\n"
                    rag_context_str += "---------------------------------------\n"

        # 3) prompt
        exam_type_context = _exam_type_context(request_data.exam_type)
        syllabus_instruction = _syllabus_instruction(request_data.syllabus)
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

        # 4) 流式 LLM 调用 + 解析：每拿到一个完整 meta / section 就推送
        async with aclosing(self._stream_llm_objects(prompt)) as objects:
            async for obj in objects:
                yield f"data: {json.dumps(obj)}\n\n"

        yield "data: [DONE]\n\n"

    async def stream_regenerated_sections(
        self,
        request_data: RegenerateSectionsRequest,
        user_id: str,
    ):
        """
        8-2 部分重新生成：只重写 selected_indices 指向的 section，其余 section 作为上下文。
        Yields SSE 字符串；每个 section 事件带 `_index`（它要替换的原位置，即请求里 sections 的下标），
        前端按位置替换，不按标题归并（重写后标题可能变化）。不推送 meta。
        """
        params = request_data.params
        sections = request_data.sections
        selected = request_data.selected_indices
        course_id = str(params.course_id) if params.course_id else None

        # 1) 预算：按整份小抄的 section 分配（沿用 BudgetRule），取被选中的那几节
        relevance = {
            t.title.strip().lower(): t.relevance_score for t in (params.selected_topics or [])
        }
        all_topics = [
            TopicInput(
                title=s.title or f"Section {i + 1}",
                relevance_score=relevance.get(s.title.strip().lower(), 0.8),
            )
            for i, s in enumerate(sections)
        ]
        budget_map = BudgetRule.calculate(params.page_limit.value, all_topics)
        targets = [budget_map.get(all_topics[i].title, 3) for i in selected]

        # 2) RAG：只为被选中的 section 检索 + rerank
        rag_context_str = await self._topic_context(
            [all_topics[i].title for i in selected], user_id, course_id
        )

        # 3) prompt
        prompt = CheatSheetPrompts.render_regenerate_prompt(
            exam_type_context=_exam_type_context(params.exam_type),
            rag_context_str=rag_context_str,
            syllabus_instruction=_syllabus_instruction(params.syllabus),
            sheet_title=request_data.title or "",
            kept_sections_str=_format_kept_sections(sections, set(selected)),
            rewrite_plan=_format_rewrite_plan(sections, selected, targets),
            section_count=len(selected),
            total_items=sum(targets),
            page_limit=params.page_limit.value,
            academic_level=params.academic_level.value,
            archetype=params.archetype.value if params.archetype else "general",
            instruction=request_data.instruction,
        )

        # 4) 第 n 个输出的 section 替换第 n 个被选中的位置；多出的丢弃
        produced = 0
        async with aclosing(self._stream_llm_objects(prompt)) as objects:
            async for obj in objects:
                if obj.get("_type") == "meta":
                    continue
                if produced >= len(selected):
                    logger.warning("Regenerate: LLM returned more sections than requested; dropped")
                    break
                event = {
                    "_index": selected[produced],
                    "title": obj.get("title", ""),
                    "items": obj.get("items", []),
                }
                produced += 1
                yield f"data: {json.dumps(event)}\n\n"

        if produced < len(selected):
            logger.warning(
                "Regenerate: LLM returned %d of %d requested sections", produced, len(selected)
            )
        yield "data: [DONE]\n\n"

    async def _topic_context(
        self, titles: List[str], user_id: str, course_id: Optional[str]
    ) -> str:
        """每个 topic 检索 k=10 → rerank 取 3，跨 topic 去重，拼成 prompt 里的 RAG 上下文。"""
        all_results = await asyncio.gather(
            *[
                self.rag_service.search_context(title, user_id=user_id, k=10, course_id=course_id)
                for title in titles
            ]
        )
        context = ""
        seen = set()
        for title, results in zip(titles, all_results):
            if not results:
                continue
            results = await self._rerank_chunks(title, results, top_n=3)
            context += f"\n--- Context for topic '{title}' ---\n"
            for r in results:
                h = hash((r.get("content") or "").strip())
                if h in seen:
                    continue
                seen.add(h)
                context += f"Source: {r['source']}\n"
                context += f"Content: {r['content']}\n"
                context += "---------------------------------------\n"
        return context

    async def _stream_llm_objects(self, prompt: str) -> AsyncIterator[dict]:
        """
        流式调用 Gemini，逐个产出解析好的对象：meta（{"_type": "meta", ...}）或完整 section（title + items）。

        generate_text_stream 是同步生成器：生产者在线程池里跑，
        每拿到一个 chunk 就通过 call_soon_threadsafe 推入 asyncio.Queue，
        主协程边取边解析边产出，不等整份生成结束。

        从缓冲区里按花括号配平切出完整的顶层 JSON 对象（不按换行切分）。
        prompt 要求 NDJSON（每行一个完整 section），但 Gemini 实际输出并不稳定，观察到过：
          - 单行 NDJSON；多行缩进的对象；多个对象首尾相连；```json 围栏（结尾 ``` 可能粘在对象后）
          - 「扁平格式」：section header 和每条 item 各自是一个对象
              {"title": "EM Algorithm"}
              {"type": "text", "content": "..."}
          - LaTeX 单反斜杠（\\(、\\theta）
        解析器将扁平格式的 items 归并到所属 section 后再产出，同时兼容完整格式（见 REPO.md §1）。
        调用方用 contextlib.aclosing 包裹，保证客户端断开时 finally 立即执行、生产者线程停止。
        """
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

        buffer = ""
        current_section: dict | None = None

        def _handle_object(obj: dict) -> List[dict]:
            """
            根据结构分类：
              - meta          → 直接产出
              - 完整格式（title + items）→ 先产出前一个 section，再产出本对象
              - section header（有 title，无 type）→ 先产出前一个 section，开始新 section
              - item（有 type + content）→ 追加到当前 section 的 items
              - {"sections": [...]} 包裹对象（prompt 禁止但可能出现）→ 逐个处理
            """
            nonlocal current_section
            out: List[dict] = []

            if isinstance(obj.get("sections"), list):
                for section in obj["sections"]:
                    if isinstance(section, dict):
                        out.extend(_handle_object(section))
                return out

            if obj.get("_type") == "meta":
                out.append(obj)
                return out

            if "title" in obj and "items" in obj:
                if current_section is not None:
                    out.append(current_section)
                current_section = None
                out.append(obj)
                return out

            if "title" in obj and "type" not in obj:
                if current_section is not None:
                    out.append(current_section)
                current_section = {"title": obj["title"], "items": []}
                return out

            if "type" in obj and "content" in obj:
                # 若没有当前 section，作为孤儿 item 忽略
                if current_section is not None:
                    current_section["items"].append(obj)
                return out

            return out

        def _drain_buffer() -> List[dict]:
            """切出缓冲区中所有已完整的对象并处理，返回需要立即产出的对象。"""
            nonlocal buffer
            texts, buffer = extract_json_objects(buffer)
            out: List[dict] = []
            for text in texts:
                try:
                    # 先修复 LaTeX 单反斜杠：否则整个 section 解析失败被丢弃，或公式被吞成制表符/换行。
                    # strict=False 容忍字符串内的原始换行。
                    obj = json.loads(escape_latex_backslashes(text), strict=False)
                except json.JSONDecodeError:
                    logger.warning("Dropped unparseable JSON object from LLM: %.200s", text)
                    continue
                if isinstance(obj, dict):
                    out.extend(_handle_object(obj))
            return out

        try:
            while True:
                chunk_text = await chunk_queue.get()
                if chunk_text is _SENTINEL:
                    break
                if isinstance(chunk_text, Exception):
                    raise chunk_text
                buffer += chunk_text
                for obj in _drain_buffer():
                    yield obj
        finally:
            # 正常结束 / 客户端断开（GeneratorExit）/ 异常，都让生产者线程尽快停止
            stop_event.set()
        await producer

        if buffer.strip():
            # 流结束时仍有未闭合的对象（输出被截断，如超出 max tokens）
            logger.warning("LLM stream ended with an incomplete JSON object: %.200s", buffer)

        # 最后 flush 尚未产出的 section（扁平格式）
        if current_section is not None:
            yield current_section


# ── prompt 片段（整份生成与部分重新生成共用） ─────────────────────────────────

# 未被选中的 section 作为上下文时的长度上限（防止 prompt 过长）
_KEPT_ITEM_CHARS = 200
_KEPT_TOTAL_CHARS = 6000
# 被选中 section 的旧内容（供参考）每条的长度上限
_OLD_ITEM_CHARS = 300


def _exam_type_context(exam_type: ExamType) -> str:
    return {
        ExamType.quiz: "Quiz",
        ExamType.midterm: "Midterm",
        ExamType.final: "Final",
    }.get(exam_type, "Final")


def _syllabus_instruction(syllabus: Optional[str]) -> str:
    if not syllabus:
        return ""
    cleaned_syllabus = clean_raw_text(syllabus)
    return f"""
            [Syllabus Filter Instruction]
            User provided the following syllabus as content filtering guide:
            {cleaned_syllabus}
            [End of Syllabus Filter Instruction]
            """


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _section_label(section, index: int) -> str:
    return section.title or f"Section {index + 1}"


def _format_kept_sections(sections, selected: set) -> str:
    """未被选中的 section：标题 + 截断后的条目，只供模型对齐风格、避免重复。"""
    parts: List[str] = []
    used = 0
    for i, s in enumerate(sections):
        if i in selected:
            continue
        lines = [f"## {_section_label(s, i)}"]
        lines += [f"- ({it.type}) {_clip(it.content, _KEPT_ITEM_CHARS)}" for it in s.items]
        block = "\n".join(lines)
        if used + len(block) > _KEPT_TOTAL_CHARS:
            parts.append(f"## {_section_label(s, i)} (items omitted)")
            continue
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts) if parts else "(none — every section is being rewritten)"


def _format_rewrite_plan(sections, selected: List[int], targets: List[int]) -> str:
    """被选中的 section：输出顺序、目标条目数，以及旧内容（只作参考，不要照抄）。"""
    parts: List[str] = []
    for n, (i, target) in enumerate(zip(selected, targets), start=1):
        s = sections[i]
        lines = [f"{n}. {_section_label(s, i)} (Target: ~{target} items)"]
        if s.items:
            lines.append("   Previous version (to be replaced):")
            lines += [f"   - ({it.type}) {_clip(it.content, _OLD_ITEM_CHARS)}" for it in s.items]
        parts.append("\n".join(lines))
    return "\n\n".join(parts)
