import re

from json_repair import repair_json


def clean_raw_text(text: str) -> str:
    """清洗用户/插件输入的原始文本。"""
    if not text:
        return ""

    text = re.sub(r"[\u200B-\u200D\uFEFF\u200E\u200F]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+(\n)", r"\1", text)
    text = re.sub(r"(\n)[ \t]+", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def repair_json_string(json_str: str) -> str:
    """修复 LLM 返回的非标准 JSON 字符串。"""
    if not json_str:
        return ""

    json_str = json_str.strip()
    if json_str.startswith("```json"):
        json_str = json_str[7:]
    elif json_str.startswith("```"):
        json_str = json_str[3:]
    if json_str.endswith("```"):
        json_str = json_str[:-3]
    json_str = json_str.strip()

    return repair_json(json_str, return_objects=False)


