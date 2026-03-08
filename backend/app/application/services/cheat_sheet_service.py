from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import MongoClient

from app.core.config import settings
from app.domain.prompts.templates import CheatSheetPrompts
from app.domain.rules.budget import BudgetRule
from app.domain.utils.math_formatter import normalize_equation
from app.infrastructure.llm.gemini_client import GeminiClient
from app.schemas import CheatSheetSchema, ExamType, GenerateSheetRequest, OutlineResponse, TopicInput
from app.domain.utils.cleaner import clean_raw_text, repair_json_string, densify_item_content
from app.infrastructure.pdf.renderer import generate_pdf_via_browser
from app.infrastructure.rag.vector_store import VectorStore, get_vector_store
from app.infrastructure.storage.minio_client import MinIOClient, get_minio_client

logger = logging.getLogger(__name__)


@dataclass
class CheatSheetService:
    """Application Layer: Cheat sheet/outline generation orchestration service (use case-level workflow)"""

    gemini: GeminiClient
    rag_service: VectorStore
    storage_client: MinIOClient

    @classmethod
    def default(cls) -> "CheatSheetService":
        return cls(
            gemini=GeminiClient(),
            rag_service=get_vector_store(),
            storage_client=get_minio_client(),
        )

    async def _search_context_with_retry(
        self,
        query: str,
        user_id: str,
        k: int = 10,
        required_batch_id: Optional[str] = None,
    ) -> List[dict]:
        """
        Polling retry for eventual consistency of Atlas vector index.
        If no chunks found, wait and retry without blocking event loop.
        """
        max_attempts = settings.RAG_RETRY_ATTEMPTS
        delay_seconds = settings.RAG_RETRY_DELAY_SECONDS

        for attempt in range(1, max_attempts + 1):
            logger.info("RAG retrieval attempt %d/%d for user_id=%s", attempt, max_attempts, user_id)

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
                        await asyncio.sleep(delay_seconds)
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

            if attempt < max_attempts:
                await asyncio.sleep(delay_seconds)

        logger.warning(
            "RAG retrieval exhausted retries after %d attempts, user_id=%s, required_batch_id=%s",
            max_attempts,
            user_id,
            required_batch_id,
        )
        return []

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
                k=10,
                required_batch_id=ingest_batch_id,
            )
            if ingest_batch_id and not results:
                degraded_reason = (
                    f"Batch {ingest_batch_id} was not searchable in retry window; "
                    "outline generated with currently searchable knowledge."
                )
                logger.warning("Outline generation degraded: %s", degraded_reason)
                # TODO(compat-remove-after-legacy-expiry):
                # 兼容线上“新旧混合数据”阶段：旧数据没有 metadata.ingest_batch_id。
                # 当 required_batch_id 未命中时，回退到不带 batch 约束的检索，确保旧数据仍可参与 outline。
                # 待旧数据全部 TTL 过期后，可移除此回退逻辑，仅保留 batch 约束路径。
                results = await self._search_context_with_retry(
                    query=query,
                    user_id=user_id,
                    k=10,
                    required_batch_id=None,
                )
            
            if results:
                rag_context_str = "\n--- RAG Context from Vector Database ---\n"
                for r in results:
                    rag_context_str += f"Source: {r['source']}\n"
                    rag_context_str += f"Content: {r['content']}...\n"
                    rag_context_str += "---------------------------------------\n"
        else:
            raise ValueError("user_id is required for RAG retrieval")

        combined_context = (cleaned_context or "") + ("\n\n" + rag_context_str if rag_context_str else "")

        
        prompt = CheatSheetPrompts.render_outline_prompt(cleaned_text, combined_context if combined_context else None, exam_type)

        response_text = self.gemini.generate_text(prompt)

        repaired = repair_json_string(response_text)
        data = json.loads(repaired)
        if degraded_reason:
            data["degraded_reason"] = degraded_reason
        return OutlineResponse(**data)

    @staticmethod
    def _clean_equations(cheat_sheet_dict: Dict[str, Any]) -> None:
        for section in cheat_sheet_dict.get("sections", []) or []:
            for item in section.get("items", []) or []:
                if item.get("type") == "equation":
                    item["content"] = normalize_equation(item.get("content", ""))

    @staticmethod
    def _save_project_if_needed(cheat_sheet: CheatSheetSchema, metadata: Optional[Dict[str, Any]]) -> Optional[str]:
        if not metadata:
            return None
        client = MongoClient(settings.MONGODB_URI)
        try:
            db = client[settings.DB_NAME]
            projects_collection = db["projects"]
            project_data = {
                "cheat_sheet": cheat_sheet.model_dump(),
                "course_name": metadata.get("course_name"),
                "syllabus": metadata.get("syllabus"),
                "education_level": metadata.get("education_level"),
                "exam_type": metadata.get("exam_type"),
                "page_limit": metadata.get("page_limit"),
                "selected_topics": metadata.get("selected_topics", []),
                "created_at": datetime.utcnow(),
            }
            insert_result = projects_collection.insert_one(project_data)
            return str(insert_result.inserted_id)
        finally:
            client.close()

    async def create_cheat_sheet_flow(self, request_data: GenerateSheetRequest, user_id: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Master Workflow:
        1) RAG 检索 2) 预算 3) Prompt 4) LLM 生成 5) 清洗 6) PDF 7) 上传 8) 入库
        """
        # 1) budget
        if not request_data.selected_topics:
            default_topics = [TopicInput(title="General Topics", relevance_score=1.0)]
            budget_map = BudgetRule.calculate(request_data.page_limit.value, default_topics)
            section_plan = "- General Topics (Target: ~{} items)".format(budget_map["General Topics"])
        else:
            budget_map = BudgetRule.calculate(request_data.page_limit.value, request_data.selected_topics)
            section_plan = "\n".join(
                [f"- {t.title} (Target: ~{budget_map.get(t.title, 3)} items)" for t in request_data.selected_topics]
            )

        total_items = sum(budget_map.values())

        # 2) RAG context
        rag_context_str = ""

        if request_data.selected_topics:
            import asyncio

            search_tasks = [
                self.rag_service.search_context_mmr(topic.title, user_id=user_id, k=3, fetch_k=10)
                for topic in request_data.selected_topics
            ]
            all_results = await asyncio.gather(*search_tasks)
            
            
            seen = set()
            for topic, results in zip(request_data.selected_topics, all_results):
                if results:
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
            
            results = await self.rag_service.search_context(query, user_id=user_id, k=10)
            
            
            if results:
                rag_context_str += "\n--- General Knowledge Base Context ---\n"
                for r in results:
                    rag_context_str += f"Source: {r['source']}\n"
                    rag_context_str += f"Content: {r['content']}\n"
                    rag_context_str += "---------------------------------------\n"

        # 3) prompt
        exam_type_context = {ExamType.quiz: "Quiz", ExamType.midterm: "Midterm", ExamType.final: "Final"}.get(
            request_data.exam_type, "Final"
        )
        syllabus_instruction = ""
        if request_data.syllabus:
            cleaned_syllabus = clean_raw_text(request_data.syllabus)
            syllabus_instruction = f"""
[Syllabus Filter Instruction]
User provided the following syllabus as content filtering guide:
{cleaned_syllabus}
[End of Syllabus Filter Instruction]
"""
        topics_str = "\n".join([f"- {t.title}" for t in request_data.selected_topics]) if request_data.selected_topics else "未指定"
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

        # 4) llm
        response_text = self.gemini.generate_text(prompt)
        repaired = repair_json_string(response_text)
        data = json.loads(repaired)

        # 5) densify item content (BEFORE schema / PDF / MongoDB)
        # - Replace internal newlines with spaces
        # - Convert markdown list newlines to bullet points
        # NOTE: Only process "text" type, NOT "equation" type (equations should preserve their format)
        for section in data.get("sections", []) or []:
            for item in section.get("items", []) or []:
                if item.get("type") == "text":
                    item["content"] = densify_item_content(item.get("content", ""))

        # 6) normalize/clean
        cheat_sheet = CheatSheetSchema(**data)
        cheat_sheet_dict = cheat_sheet.model_dump()
        self._clean_equations(cheat_sheet_dict)

        # 7) pdf
        pdf_bytes = await generate_pdf_via_browser(cheat_sheet_dict)

        # 8) upload
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c for c in cheat_sheet.title if c.isalnum() or c in (" ", "-", "_")).rstrip()
        safe_title = safe_title.replace(" ", "_")[:50]
        filename = f"{safe_title}_{timestamp}.pdf"
        file_key = self.storage_client.upload_file(pdf_bytes, filename)
        if not file_key:
            raise ValueError("Failed to upload PDF to AWS S3")

        # 9) save record
        project_id = self._save_project_if_needed(cheat_sheet, metadata)

        result: Dict[str, Any] = {
            "status": "completed",
            "file_key": file_key,
            "size": len(pdf_bytes),
            "filename": filename,
            "data": cheat_sheet_dict,
        }
        if project_id:
            result["project_id"] = project_id
        return result


