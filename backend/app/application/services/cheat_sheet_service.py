from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from pymongo import MongoClient

from app.core.config import settings
from app.domain.prompts.templates import CheatSheetPrompts
from app.domain.rules.budget import BudgetRule
from app.domain.utils.math_formatter import normalize_equation
from app.infrastructure.llm.gemini_client import GeminiClient
from app.schemas import CheatSheetSchema, ExamType, GenerateSheetRequest, OutlineResponse, TopicInput
from app.domain.utils.cleaner import clean_raw_text, repair_json_string
from app.infrastructure.pdf.renderer import generate_pdf_via_browser
from app.infrastructure.rag.vector_store import VectorStore, get_vector_store
from app.infrastructure.storage.minio_client import MinIOClient, get_minio_client


@dataclass
class CheatSheetService:
    """Application Layer: 小抄/大纲生成编排服务（用例级工作流）。"""

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

    def generate_outline(self, text: str, context: Optional[str] = None, exam_type: ExamType = ExamType.final) -> OutlineResponse:
        cleaned_text = clean_raw_text(text)
        cleaned_context = clean_raw_text(context) if context else None
        prompt = CheatSheetPrompts.render_outline_prompt(cleaned_text, cleaned_context, exam_type)

        api_start = time.time()
        response_text = self.gemini.generate_text(prompt)
        print(f"⏱️ [性能监控] generate_outline(app) - Gemini API 调用耗时: {time.time() - api_start:.2f} 秒")

        repaired = repair_json_string(response_text)
        data = json.loads(repaired)
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
        rag_start = time.time()
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
        print(f"⏱️ [性能监控] create_cheat_sheet_flow - RAG 检索耗时: {time.time() - rag_start:.2f} 秒")

        # 3) prompt
        exam_type_context = {ExamType.quiz: "Quiz", ExamType.midterm: "Midterm", ExamType.final: "Final"}.get(
            request_data.exam_type, "Final"
        )
        syllabus_instruction = ""
        if request_data.syllabus:
            cleaned_syllabus = clean_raw_text(request_data.syllabus)
            syllabus_instruction = f"""
[Syllabus Filter Instruction]
用户提供了以下考试大纲作为内容过滤指南：
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
        api_start = time.time()
        response_text = self.gemini.generate_text(prompt)
        print(f"⏱️ [性能监控] create_cheat_sheet_flow - Gemini API 调用耗时: {time.time() - api_start:.2f} 秒")
        repaired = repair_json_string(response_text)
        data = json.loads(repaired)

        # 5) normalize/clean
        cheat_sheet = CheatSheetSchema(**data)
        cheat_sheet_dict = cheat_sheet.model_dump()
        self._clean_equations(cheat_sheet_dict)

        # 6) pdf
        pdf_start = time.time()
        pdf_bytes = await generate_pdf_via_browser(cheat_sheet_dict)
        print(f"⏱️ [性能监控] create_cheat_sheet_flow - PDF 生成耗时: {time.time() - pdf_start:.2f} 秒")

        # 7) upload
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c for c in cheat_sheet.title if c.isalnum() or c in (" ", "-", "_")).rstrip()
        safe_title = safe_title.replace(" ", "_")[:50]
        filename = f"{safe_title}_{timestamp}.pdf"
        file_key = self.storage_client.upload_file(pdf_bytes, filename)
        if not file_key:
            raise ValueError("PDF 上传到 MinIO 失败")

        # 8) save record
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


