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


def densify_item_content(text: str) -> str:
    """
    压缩单个 item 内部的换行，减少 PDF 版面浪费。

    规则：
    - 若包含代码块标记 ``` ，不做任何处理（避免破坏格式）
    - 将换行后的 Markdown 列表项（- / *）合并为 bullet：`\\n- xxx` -> `  • xxx`
    - 其余换行折叠为双空格，避免 end\\nstart 变成 endstart（至少保留空格）

    说明：对 LaTeX 安全——LaTeX 通常将空白/换行视为等价空白。
    """
    if not text:
        return ""

    if "```" in text:
        return text

    # Step 1: Replace Markdown list markers (newline + dash/star) with a bullet point
    text = re.sub(r"\n\s*[-*]\s+", "  • ", text)

    # Step 2: Replace remaining newlines with double spaces
    text = re.sub(r"\s*\n\s*", "  ", text)

    return text.strip()
