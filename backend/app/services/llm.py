import os
import json
import time
import google.generativeai as genai
from google.api_core import retry, exceptions
from dotenv import load_dotenv
from typing import Optional, Dict, List

from app.schemas import (
    GenerateSheetRequest, 
    OutlineResponse,
    CheatSheetSchema,
    PageLimit,
    CourseArchetype,
    ExamType,
    TopicInput
)
from app.services.cleaner import clean_raw_text, repair_json_string
from app.services.rag_service import get_rag_service

# 确保加载环境变量
load_dotenv()

# 重试配置：指数退避策略
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1  # 初始延迟 1 秒
MAX_RETRY_DELAY = 60  # 最大延迟 60 秒
REQUEST_TIMEOUT = 120  # 请求超时 120 秒


def _get_gemini_model():
    """获取配置好的 Gemini 模型实例"""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found in environment variables")
    
    genai.configure(api_key=api_key)
    
    return genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        generation_config={"response_mime_type": "application/json"}
    )


def _is_retryable_error(exception: Exception) -> bool:
    """
    判断错误是否可重试
    
    Returns:
        True 如果错误是可重试的（如 Rate Limit、Service Unavailable）
    """
    # 检查是否是 Google API 的特定错误
    error_str = str(exception).lower()
    
    # Rate limit 相关错误
    if any(keyword in error_str for keyword in [
        "resource exhausted", 
        "rate limit", 
        "quota exceeded",
        "429"
    ]):
        return True
    
    # 服务不可用错误
    if any(keyword in error_str for keyword in [
        "service unavailable",
        "503",
        "unavailable",
        "temporarily unavailable"
    ]):
        return True
    
    # 网络超时错误
    if any(keyword in error_str for keyword in [
        "timeout",
        "deadline exceeded",
        "504"
    ]):
        return True
    
    return False


def _exponential_backoff_retry(func, *args, **kwargs):
    """
    带指数退避的重试装饰器
    
    Args:
        func: 要重试的函数
        *args, **kwargs: 函数参数
        
    Returns:
        函数返回值
        
    Raises:
        最后一次尝试的异常
    """
    last_exception = None
    delay = INITIAL_RETRY_DELAY
    
    for attempt in range(MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            
            # 如果不是可重试的错误，直接抛出
            if not _is_retryable_error(e):
                raise e
            
            # 如果是最后一次尝试，直接抛出
            if attempt == MAX_RETRIES - 1:
                raise e
            
            # 计算延迟时间（指数退避）
            delay = min(INITIAL_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
            
            print(f"⚠️ API 调用失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {str(e)}")
            print(f"⏳ 等待 {delay} 秒后重试...")
            time.sleep(delay)
    
    # 理论上不会到达这里，但为了类型检查
    raise last_exception


def generate_outline(text: str, context: Optional[str] = None, exam_type: ExamType = ExamType.final) -> OutlineResponse:
    """
    分析文本和用户上下文，提取核心考试主题。
    """
    model = _get_gemini_model()
    
    # 清洗输入文本
    cleaned_text = clean_raw_text(text)
    cleaned_context = clean_raw_text(context) if context else None
    
    # 根据考试类型动态调整数量约束
    if exam_type == ExamType.quiz:
        topic_range = "3-5"
        topic_instruction = "Extract exactly 3-5 core topics. Focus on specific, narrow concepts."
    elif exam_type == ExamType.midterm:
        topic_range = "5-8"
        topic_instruction = "Extract 5-8 core topics. Cover the first half of the course material."
    else:  # final
        topic_range = "8-15"
        topic_instruction = "Extract 8-15 core topics. Ensure comprehensive coverage of the entire course."
    
    system_prompt = f"""你是一个专业的复习资料分析助手。你的主要任务是分析用户提供的对话记录，提取出 {topic_range} 个核心考试主题。

        【任务：提取核心主题】
        1. 忽略闲聊内容，只关注与学习、考试、知识点相关的主题。
        2. 每个主题应该是一个大块的知识点，包含与之相关的多方面的内容，例如公式、定理、例题、证明等。
        3. 为每个主题计算相关性分数 (0.0-1.0)，基于其在对话中出现的频率和重要性。
        4. 按相关性从高到低排序。
        5. {topic_instruction}

        【输出格式要求】
        必须返回符合以下结构的纯 JSON，不要包含 Markdown 标记：
        {{
        "topics": [
            {{"title": "主题A", "relevance_score": 0.95}},
            {{"title": "主题B", "relevance_score": 0.88}}
        ]
        }}

        IMPORTANT: 
        1. JSON String Escaping: Double-escape all backslashes in LaTeX (e.g., \\\\sigma).
        2. Constraint Check: Ensure the "topics" list has between {topic_range} items. Do not output too many small topics.
        """

    user_input = f"对话记录：\n{cleaned_text}\n\n"
    if cleaned_context:
        user_input += f"用户背景信息：\n{cleaned_context}\n\n"
    
    # 再次在 User Input 结尾强调一次，防止模型"忘事"
    user_input += f"请提取 {topic_range} 个核心主题。"

    print(f"----- [DEBUG] Calling generate_outline with text length: {len(cleaned_text)} -----")

    response = None
    try:
        # 使用重试机制调用 API
        # 注意：Google Generative AI 的超时需要通过环境变量或客户端配置设置
        # 这里我们依赖重试机制来处理超时
        def _call_api():
            try:
                return model.generate_content(f"{system_prompt}\n\n{user_input}")
            except Exception as e:
                # 检查是否是超时错误
                error_str = str(e).lower()
                if "timeout" in error_str or "deadline" in error_str:
                    raise TimeoutError(f"请求超时（超过 {REQUEST_TIMEOUT} 秒）") from e
                raise
        
        response = _exponential_backoff_retry(_call_api)
        raw_json = response.text
        
        print("----- [DEBUG] Outline Response Received -----")
        print(f"Preview: {raw_json[:100]}...")

        # 修复 JSON 字符串
        repaired_json = repair_json_string(raw_json)
        
        data = json.loads(repaired_json)
        
        # 确保 topics 数量在合理范围内（虽然 Prompt 限制了，但为了保险可以做个截断，或者就这样留着）
        return OutlineResponse(**data)

    except exceptions.ResourceExhausted as e:
        print(f"❌ Rate Limit Error in generate_outline: {e}")
        raise ValueError(
            f"API 配额已用尽，请稍后重试。错误详情: {str(e)}"
        ) from e
    except exceptions.ServiceUnavailable as e:
        print(f"❌ Service Unavailable Error in generate_outline: {e}")
        raise ValueError(
            f"服务暂时不可用，请稍后重试。错误详情: {str(e)}"
        ) from e
    except TimeoutError as e:
        print(f"❌ Timeout Error in generate_outline: {e}")
        raise ValueError(
            f"请求超时（超过 {REQUEST_TIMEOUT} 秒），请稍后重试。"
        ) from e
    except json.JSONDecodeError as e:
        print(f"❌ JSON Decode Error in generate_outline: {e}")
        if response:
            print(f"Faulty Response Content: {response.text[:500]}")
        raise ValueError(
            f"LLM 返回的 JSON 格式无效。错误详情: {str(e)}"
        ) from e
    except Exception as e:
        print(f"❌ Unexpected Error in generate_outline: {e}")
        if response:
            try:
                print(f"Faulty Response Content: {response.text[:500]}")
            except:
                pass
        raise ValueError(
            f"生成大纲时发生未知错误: {str(e)}"
        ) from e


def _calculate_budget(page_limit: str, topics: List[TopicInput]) -> Dict[str, int]:
    """
    根据篇幅限制和主题相关性，计算每个主题的条目预算。
    返回: { "Topic Name": item_count }
    """
    # 1. 确定总预算 (Total Pool)
    if page_limit == "1_side":
        total_items = 25
    elif page_limit == "1_page":
        total_items = 45
    elif page_limit == "2_pages":
        total_items = 80
    else:  # unlimited
        total_items = 160
    
    # 2. 计算总权重分母
    total_score = sum(t.relevance_score for t in topics)
    if total_score == 0:
        total_score = 1  # 防止除以零
    
    # 3. 分配预算
    budget_map = {}
    current_allocated = 0
    # 我们需要一个按分数排序的列表，用于稍后分发“余数”
    # 按照分数从高到低排序
    sorted_topics = sorted(topics, key=lambda x: x.relevance_score, reverse=True)

    for topic in topics:
        # 核心公式: (该题分数 / 总分) * 总条目数
        raw_count = (topic.relevance_score / total_score) * total_items
        
        # 约束: 无论多不重要，至少给 3 个条目；无论多重要，稍微留点余地
        count = max(3, int(raw_count))
        budget_map[topic.title] = count
        current_allocated += count

    # 4. 第二轮分配 (吃掉余数)
    # 如果因为取整导致实际分配(current_allocated) 少于 目标预算(total_items)
    remainder = total_items - current_allocated
    if remainder > 0:
        # 循环给高分主题“发糖”，直到余数发完
        for i in range(remainder):
            # 每个幸运儿多发一个预算（分数最高的第 i 个）
            lucky_topic = sorted_topics[i % len(sorted_topics)]
            budget_map[lucky_topic.title] += 1
            
    return budget_map


async def generate_cheat_sheet(request: GenerateSheetRequest) -> CheatSheetSchema:
    """
    根据用户请求生成高密度的 Cheat Sheet。
    实现混合检索、领域自适应和预算控制算法。
    现在支持 RAG 上下文注入。
    """
    model = _get_gemini_model()
    
    # 清洗用户背景信息（syllabus 不再作为内容来源，仅作为过滤指令）
    cleaned_user_context = clean_raw_text(request.user_context) if request.user_context else None
    
    # 确定使用的 archetype（优先使用请求中的，否则默认为 general）
    archetype = request.archetype.value if request.archetype else "general"
    
    # 计算预算（基于相关性权重）
    if not request.selected_topics:
        # 如果没有选定主题，创建一个默认主题
        default_topics = [TopicInput(title="General Topics", relevance_score=1.0)]
        budget_map = _calculate_budget(request.page_limit.value, default_topics)
        section_plan = "- General Topics (Target: ~{} items)".format(budget_map["General Topics"])
    else:
        budget_map = _calculate_budget(request.page_limit.value, request.selected_topics)
        # 构建 Section Plan
        section_plan_lines = []
        for topic in request.selected_topics:
            item_count = budget_map.get(topic.title, 3)
            section_plan_lines.append(f"- {topic.title} (Target: ~{item_count} items)")
        section_plan = "\n".join(section_plan_lines)
    
    total_items = sum(budget_map.values())
    
    # RAG 上下文注入逻辑：必须从向量数据库检索
    rag_service = get_rag_service()
    rag_context_str = ""
    
    if request.selected_topics:
        # 如果有选定主题，对每个主题进行 RAG 检索
        for topic in request.selected_topics:
            results = await rag_service.search_context(topic.title, k=5)
            
            if results:
                # 拼接该主题的 RAG 上下文
                rag_context_str += f"\n--- Context for topic '{topic.title}' ---\n"
                for result in results:
                    rag_context_str += f"Source: {result['source']}\n"
                    rag_context_str += f"Content: {result['content']}\n"
                    rag_context_str += "---------------------------------------\n"
    else:
        # 如果没有选定主题，使用通用查询获取知识库内容
        # 使用用户背景或课程类型作为查询词
        query = request.user_context or archetype or "general knowledge"
        results = await rag_service.search_context(query, k=10)
        
        if results:
            rag_context_str += "\n--- General Knowledge Base Context ---\n"
            for result in results:
                rag_context_str += f"Source: {result['source']}\n"
                rag_context_str += f"Content: {result['content']}\n"
                rag_context_str += "---------------------------------------\n"
    
    # 获取考试类型上下文
    exam_type_context = {
        ExamType.quiz: "Quiz",
        ExamType.midterm: "Midterm",
        ExamType.final: "Final"
    }.get(request.exam_type, "Final")
    
    # 构建 System Prompt（注入 RAG 上下文和 Syllabus 过滤指令）
    syllabus_instruction = ""
    if request.syllabus:
        cleaned_syllabus = clean_raw_text(request.syllabus)
        syllabus_instruction = f"""
            [Syllabus Filter Instruction]
            用户提供了以下考试大纲作为内容过滤指南：
            {cleaned_syllabus}

            **重要：这不是内容来源，而是过滤指令。**
            - 请根据此大纲，从 [RAG Context] 中筛选出与大纲相关的知识点。
            - 如果大纲中提到的主题在 [RAG Context] 中存在，优先保留这些内容。
            - 如果大纲中未提及的主题，可以减少或省略相关内容。
            - 确保生成的小抄内容与考试大纲高度相关。
            [End of Syllabus Filter Instruction]
            """
    
    system_prompt = f"""Context: This cheat sheet is for a {exam_type_context}.
        你是一个智能复习资料生成引擎。你的任务是根据向量数据库中的内容和用户提供的[选定主题]，生成一份高密度的 Cheat Sheet。

        [RAG Context - 唯一内容来源]
        以下内容来自向量数据库，这是生成小抄的唯一内容来源。请优先使用这些内容：
        {rag_context_str if rag_context_str else "（向量数据库中暂无相关内容）"}
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

        4. Level Adjustment (Based on academic_level):
        - "graduate":
            * For STEM: Prioritize rigorous **proofs, derivations, and complexity analysis**. Skip basic calculation steps.
            * For Non-STEM: Focus on **critical theory, methodology, and historiography**. Analyze nuances rather than just listing facts.
        - "undergraduate":
            * For STEM: Focus on **application and calculation**. Show standard algorithms and solving procedures.
            * For Non-STEM: Focus on **core arguments, key definitions, and cause-effect relationships**.
        - "high_school":
            * General: Focus on **foundational concepts and step-by-step simplification**. Use analogies and mnemonics to explain basic terms.

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

        对于数学公式，必须使用 LaTeX 格式（例如 \\\\int x dx）。

        IMPORTANT: JSON String Escaping. You must double-escape all backslashes in LaTeX. For example, output \\\\sigma instead of \\sigma, and \\\\( instead of \\(. Ensure the output is valid parsable JSON.

        不要返回任何 Markdown 标记，直接返回纯 JSON 对象。"""

    # 构建用户输入（不再包含 syllabus 作为内容，只包含元数据）
    user_input_parts = []
    
    if cleaned_user_context:
        user_input_parts.append(f"用户背景信息：\n{cleaned_user_context}\n")
    
    if request.selected_topics:
        topics_str = "\n".join([f"- {topic.title}" for topic in request.selected_topics])
        user_input_parts.append(f"选定主题列表：\n{topics_str}\n")
        user_input_parts.append(
            f"STRICT REQUIREMENT: Only generate content for these specific topics: {topics_str}. "
            "Use your internal knowledge to supplement if the RAG Context is missing details for these topics.\n"
        )
    else:
        user_input_parts.append("选定主题列表：未指定（请从 RAG Context 中提取相关主题）\n")
    
    user_input_parts.append(f"页面限制：{request.page_limit.value}\n")
    user_input_parts.append(f"学术水平：{request.academic_level.value}\n")
    user_input_parts.append(f"课程类型：{archetype}\n")
    
    user_input = "\n".join(user_input_parts)
    user_input += "\n请根据以上信息生成 Cheat Sheet。"

    print(f"----- [DEBUG] Calling generate_cheat_sheet -----")
    print(f"Page Limit: {request.page_limit.value}")
    print(f"Academic Level: {request.academic_level.value}")
    print(f"Archetype: {archetype}")
    print(f"Selected Topics Count: {len(request.selected_topics) if request.selected_topics else 0}")
    print(f"Total Items Budget: {total_items}")
    print(f"Budget Map: {budget_map}")
    print(f"RAG Context Length: {len(rag_context_str)}")
    print(f"Syllabus provided: {bool(request.syllabus)}")
    print(f"Syllabus value: {repr(request.syllabus)}")
    print(f"Raw text value: {repr(request.raw_text)}")

    response = None
    try:
        # 使用重试机制调用 API
        # 注意：Google Generative AI 的超时需要通过环境变量或客户端配置设置
        # 这里我们依赖重试机制来处理超时
        def _call_api():
            try:
                return model.generate_content(f"{system_prompt}\n\n{user_input}")
            except Exception as e:
                # 检查是否是超时错误
                error_str = str(e).lower()
                if "timeout" in error_str or "deadline" in error_str:
                    raise TimeoutError(f"请求超时（超过 {REQUEST_TIMEOUT} 秒）") from e
                raise
        
        response = _exponential_backoff_retry(_call_api)
        raw_json = response.text
        
        print("----- [DEBUG] Cheat Sheet Response Received -----")
        print(f"Preview: {raw_json[:100]}...")

        # 修复 JSON 字符串
        repaired_json = repair_json_string(raw_json)
        
        data = json.loads(repaired_json)

        # 类型清洗逻辑 (Type Sanitizer)
        # 目的：将 LLM 自创的 type (如 "exam_question", "concept") 
        # 强制映射回合法的 ContentType (text, equation, definition)
        # valid_types = ["text", "equation", "definition"]
        
        # for section in data.get("sections", []):
        #     for item in section.get("items", []):
        #         original_type = str(item.get("type", "text")).lower().strip()
                
        #         # 如果已经是合法的，跳过
        #         if original_type in valid_types:
        #             continue 
                
        #         # 智能映射
        #         if original_type in ["concept", "term", "vocabulary", "key_point"]:
        #             item["type"] = "definition"
        #         elif original_type in ["formula", "math", "derivation", "proof"]:
        #             item["type"] = "equation"
        #         else:
        #             # 兜底策略：所有其他奇怪的类型 (exam_question, comparison, difference, code, step...) 
        #             # 全部归为 "text"
        #             item["type"] = "text"

        return CheatSheetSchema(**data)

    except exceptions.ResourceExhausted as e:
        print(f"❌ Rate Limit Error in generate_cheat_sheet: {e}")
        raise ValueError(
            f"API 配额已用尽，请稍后重试。错误详情: {str(e)}"
        ) from e
    except exceptions.ServiceUnavailable as e:
        print(f"❌ Service Unavailable Error in generate_cheat_sheet: {e}")
        raise ValueError(
            f"服务暂时不可用，请稍后重试。错误详情: {str(e)}"
        ) from e
    except TimeoutError as e:
        print(f"❌ Timeout Error in generate_cheat_sheet: {e}")
        raise ValueError(
            f"请求超时（超过 {REQUEST_TIMEOUT} 秒），请稍后重试。"
        ) from e
    except json.JSONDecodeError as e:
        print(f"❌ JSON Decode Error in generate_cheat_sheet: {e}")
        if response:
            print(f"Faulty Response Content: {response.text[:500]}")
        raise ValueError(
            f"LLM 返回的 JSON 格式无效。错误详情: {str(e)}"
        ) from e
    except Exception as e:
        print(f"❌ Unexpected Error in generate_cheat_sheet: {e}")
        if response:
            try:
                print(f"Faulty Response Content: {response.text[:500]}")
            except:
                pass
        raise ValueError(
            f"生成 Cheat Sheet 时发生未知错误: {str(e)}"
        ) from e
