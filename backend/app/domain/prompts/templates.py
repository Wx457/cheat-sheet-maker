from typing import Optional

from app.schemas import ExamType


class CheatSheetPrompts:
    """集中管理与渲染 LLM 提示词。"""

    @staticmethod
    def render_outline_prompt(
        cleaned_text: str,
        cleaned_context: Optional[str],
        exam_type: ExamType,
    ) -> str:
        if exam_type == ExamType.quiz:
            min_t, max_t = 3, 5
            scope_desc = "Specific, narrow concepts suitable for a short quiz."
        elif exam_type == ExamType.midterm:
            min_t, max_t = 5, 8
            scope_desc = "Core concepts covering the first half of the course."
        else:
            min_t, max_t = 8, 15
            scope_desc = "Comprehensive coverage of the entire course material."

        system_prompt = f"""You are a strict Exam Syllabus Analyzer. Your task is to extract exam topics from the provided text.

            GLOBAL CONSTRAINTS:
            1. **Relevance**: Ignore chitchat. Focus ONLY on academic concepts, formulas, theorems, and proofs.
            2. **Scoring**: Assign a relevance_score (0.0-1.0) to each topic based on frequency and importance.
            3. **Sorting**: Sort topics by relevance_score descending.
            4. **Language**: Use English.

            STRICT QUANTITY CONTROL (CRITICAL):
            You MUST output a JSON list containing **between {min_t} and {max_t} topics**.

            **STRATEGY TO MEET QUOTA:**
            - **IF you find > {max_t} topics**: You MUST **MERGE** specific sub-topics into broader "Parent Topics". (e.g., merge "Dot Product" and "Cross Product" into "Vector Operations").
            - **IF you find < {min_t} topics**: You MUST **SPLIT** broad topics into specific sub-components.
            - **VIOLATION**: Returning more than {max_t} or fewer than {min_t} topics is considered a SYSTEM FAILURE.

            SCOPE: {scope_desc}

            【OUTPUT FORMAT】
            Return ONLY raw JSON. No Markdown. No comments.
            Structure:
            {{
                "topics": [
                    {{"title": "Broad Concept A", "relevance_score": 0.95}},
                    {{"title": "Broad Concept B", "relevance_score": 0.88}}
                ]
            }}

            IMPORTANT: Double-escape backslashes in LaTeX strings (e.g., \\\\sigma).
            """

        user_input = f"Conversation Record:\n{cleaned_text}\n\n"
        if cleaned_context:
            # 如果包含 RAG 上下文，明确标注
            if "--- RAG Context from Vector Database ---" in cleaned_context:
                user_input += (
                    f"[RAG Context - Primary Source]\n{cleaned_context}\n[End of RAG Context]\n\n"
                )
                user_input += "Prioritize extracting topics from the above RAG Context, which comes from the vector database and is the actual content of the course.\n\n"
            else:
                user_input += f"User Background Information:\n{cleaned_context}\n\n"
        return f"{system_prompt}\n\n{user_input}"

    @staticmethod
    def render_cheatsheet_prompt(
        exam_type_context: str,
        rag_context_str: str,
        syllabus_instruction: str,
        section_plan: str,
        total_items: int,
        page_limit: str,
        academic_level: str,
        archetype: str,
        selected_topics_str: str,
    ) -> str:
        return f"""Context: This cheat sheet is for a {exam_type_context}.
You are an intelligent cheat sheet generation engine. Your task is to generate a high-density Cheat Sheet based on the content in the vector database and the [selected topics] provided by the user.

[RAG Context - Primary Source]
The following content comes from the vector database, which is the primary source of content for generating the cheat sheet. Please prioritize using this content:
{rag_context_str if rag_context_str else "(No relevant content in the vector database)"}
[End of RAG Context]
{syllabus_instruction}

STRICT CONTENT CONTROL: You must generate a total of approximately {total_items} items. Spread them across the sections according to the following plan:

Section Plan (Item Budget per Topic):
{section_plan}

Do not stop until you meet this depth for each section.

Core Instruction Matrix:
1. Source & Scope Strategy (Source Hierarchy):
- Primary Source (RAG): You must prioritize the [RAG Context]. Extract topics and key definitions strictly from here.
- Secondary Source (Internal Knowledge - ONLY for Expansion): 
  IF [RAG Context] mentions a theorem/algorithm but lacks the mathematical proof/derivation, **YOU MUST use your Internal Knowledge to generate the step-by-step mathematical derivation.**
  IF [RAG Context] is empty/insufficient, fallback to Internal Knowledge to generate the entire section.
- Scope Control: Only generate topics in 'selected_topics'. If 'selected_topics' is empty, extract topics from [RAG Context] (or Internal Knowledge if RAG is empty).
- Important: Do not use raw user text as a *content source* to generate facts. Use it ONLY as a *filter/instruction* (Syllabus) to select topics.

2. Density & Expansion Control (Based on page_limit):
MANDATORY DISTRIBUTION: For every single section, **'equation' type items MUST constitute at least 50% of the total allocated Item Budget** (e.g., if a section has 10 items, at least 5 items must be formulas).
Prioritize listing core formulas first, derivation/proof steps second, then use the remaining budget for explanations.
- "1_side" (Survival Mode):
    * CONTENT: Series of core formulas + core derivations/proofs of each formula. No text padding.
    * DEPTH: 1 item = 1 formula + 2-3 derivation or proof steps.
- "1_page" (Compact Derivation Mode):
    * CONTENT: Series of important formulas + **Critical Derivation Steps (3-5 steps)** of each formula.
    * EXPANSION: Do not just list the equation. Show the starting point and the key transformation steps.
    * LENGTH: Fill the whitespace. Use concise text to connect derivation steps. Include complexity analysis in big O for math algorithms.
    * DEPTH: 
        1 item = 1 formula + 3-4 derivation or proof steps, or
        1 item = 1 brief explanation/application scenarios text, or
        1 item = 1 big O complexity result for 1 algorithm
- "2_pages" (Comprehensive Mode):
    * CONTENT: Series of formulas + **Full Mathematical Proofs/Derivation Steps(4-6 steps)** of each formula + complexity analysis in big O notation. 
    * EXPANSION: Include "Physical Meaning of Variables" and "Complexity Analysis" as separate items. 
    * LENGTH: Maximize information density. Do not leave large empty spaces.
    * DEPTH: 
        1 item = 1 formula + 4-6 derivation or proof steps, or
        1 item = 1 explanation/application scenarios text, or
        1 item = 1 big O complexity analysis for 1 algorithm
- "unlimited": Detailed mode with examples and code.

3. Level Adjustment (Based on academic_level):
- "graduate":
    * For STEM: Prioritize rigorous **proofs, derivations, and complexity analysis**. Skip basic calculation steps.
    * For Non-STEM: Focus on **critical theory, methodology, and historiography**. Analyze nuances rather than just listing facts.
- "undergraduate":
    * For STEM: Focus on **application and calculation**. Show standard algorithms and solving procedures.
    * For Non-STEM: Focus on **core arguments, key definitions, and cause-effect relationships**.

4. Output Format: You must return pure JSON conforming to the following Schema:
{{
"title": "Cheat Sheet Title",
"sections": [
    {{
    "title": "Section Title (corresponds to one selected_topic)",
    "items": [
        {{
        "type": "text|equation|definition",
        "content": "..."
        }}
    ]
    }}
]
}}

For mathematical formulas, you must use LaTeX format (e.g. \\\\int x dx).

IMPORTANT: JSON String Escaping. You must double-escape all backslashes in LaTeX. For example, output \\\\sigma instead of \\sigma, and \\\\( instead of \\(. Ensure the output is valid parsable JSON.

Do not return any Markdown tags, return pure JSON objects. All content must be in English.

[User Metadata]
Selected Topics List:
{selected_topics_str}
Page Limit: {page_limit}
Academic Level: {academic_level}
Course Type: {archetype}
[End of User Metadata]
"""
