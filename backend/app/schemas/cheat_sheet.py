from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ContentType(str, Enum):
    text = "text"
    equation = "equation"
    definition = "definition"


class PageLimit(str, Enum):
    one_side = "1_side"
    one_page = "1_page"
    two_pages = "2_pages"
    unlimited = "unlimited"


class AcademicLevel(str, Enum):
    high_school = "high_school"
    undergraduate = "undergraduate"
    graduate = "graduate"


class CourseArchetype(str, Enum):
    stem_computational = "stem_computational"  # 计算类 STEM (微积分、线性代数等 - 侧重计算步骤、例题)
    stem_theoretical = "stem_theoretical"  # 理论类 STEM (高阶物理、ML理论等 - 侧重公式推导、证明)
    coding = "coding"  # 编程类 (Java, Python等 - 侧重代码片段、语法、伪代码)
    humanities = "humanities"  # 文史哲 (历史、心理学等 - 侧重时间线、定义、论点)
    general = "general"  # 通用 (默认)


class ExamType(str, Enum):
    quiz = "quiz"  # Quiz (3-5 topics)
    midterm = "midterm"  # Midterm (5-8 topics)
    final = "final"  # Final (8-12+ topics)


class ContentItem(BaseModel):
    type: ContentType
    content: str


class Section(BaseModel):
    title: str
    items: List[ContentItem]


class CheatSheetSchema(BaseModel):
    title: str
    sections: List[Section]


class TopicNode(BaseModel):
    title: str
    relevance_score: float


class TopicInput(BaseModel):
    title: str
    relevance_score: float = 0.8  # 默认值


class OutlineResponse(BaseModel):
    topics: List[TopicNode]


class GenerateOutlineRequest(BaseModel):
    raw_text: str
    user_context: Optional[str] = None
    exam_type: ExamType = ExamType.final


class GenerateSheetRequest(BaseModel):
    # 考试大纲（可选，最高优先级，最多 600 字）
    syllabus: Optional[str] = Field(None, max_length=600, description="考试大纲，AI 将以此为最高优先级生成小抄")
    # 保留 raw_text 以向后兼容，但改为可选
    raw_text: Optional[str] = Field(None, description="原始文本/对话记录（向后兼容字段，建议使用 syllabus）")
    user_context: Optional[str] = None
    page_limit: PageLimit = PageLimit.one_page
    academic_level: AcademicLevel = AcademicLevel.undergraduate
    selected_topics: Optional[List[TopicInput]] = None
    archetype: Optional[CourseArchetype] = None
    exam_type: ExamType = ExamType.final


class PluginAnalyzeRequest(BaseModel):
    """Chrome 插件分析请求模型"""
    content: str  # 抓取的长文本
    syllabus: Optional[str] = Field(None, max_length=600, description="考试大纲（可选）")
    url: str  # 网页 URL
    course_name: Optional[str] = Field(None, description="课程名称")
    education_level: Optional[AcademicLevel] = Field(None, description="学习层次")
    exam_type: Optional[ExamType] = Field(ExamType.final, description="考试类型")


class PluginGenerateRequest(BaseModel):
    """Chrome 插件生成请求模型"""
    selected_topics: List[TopicInput]  # 用户选定的主题列表
    syllabus: Optional[str] = Field(None, max_length=600, description="考试大纲（可选）")
    course_name: Optional[str] = Field(None, description="课程名称")
    education_level: Optional[AcademicLevel] = Field(AcademicLevel.undergraduate, description="学习层次")
    exam_type: Optional[ExamType] = Field(ExamType.final, description="考试类型")
    page_limit: Optional[PageLimit] = Field(PageLimit.one_page, description="页面限制")


class GenerateFinalResponse(BaseModel):
    """生成最终结果的响应模型"""
    project_id: str
    cheat_sheet: CheatSheetSchema


__all__ = [
    "ContentType",
    "PageLimit",
    "AcademicLevel",
    "CourseArchetype",
    "ExamType",
    "ContentItem",
    "Section",
    "CheatSheetSchema",
    "TopicNode",
    "TopicInput",
    "OutlineResponse",
    "GenerateOutlineRequest",
    "GenerateSheetRequest",
    "PluginAnalyzeRequest",
    "PluginGenerateRequest",
    "GenerateFinalResponse",
]

