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


def extract_json_objects(buffer: str) -> tuple[list[str], str]:
    """从流式缓冲区中切出所有已完整的顶层 JSON 对象文本。

    返回 (对象文本列表, 剩余未完成部分)。剩余部分从最后一个未闭合对象的 "{" 开始；
    没有未闭合对象时为空串。对象之间的任何内容（换行、逗号、[ ]、``` 围栏、杂散文字）都丢弃。

    不依赖换行：LLM 实际会输出单行 NDJSON、多行缩进的对象、首尾相连的对象，以及带
    代码块围栏的输出，按行切分无法覆盖。字符串内部的花括号（如 LaTeX \\frac{a}{b}）
    与反斜杠转义都会被跳过，不参与括号计数。
    """
    objects: list[str] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for i, ch in enumerate(buffer):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = depth > 0  # 对象外的引号视为杂散文字
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                objects.append(buffer[start : i + 1])
    rest = buffer[start:] if depth > 0 else ""
    return objects, rest


# 一个反斜杠 + 被转义的内容。优先匹配已双写的 "\\"，避免把正确转义拆开。
_BACKSLASH_ESCAPE = re.compile(r'\\(\\|"|/|u[0-9a-fA-F]{4}|.)')


def escape_latex_backslashes(json_line: str) -> str:
    """修复 LLM 在 JSON 字符串里写了单反斜杠的 LaTeX（流式 NDJSON 解析前调用）。

    LLM 经常不遵守 "LaTeX 反斜杠写两遍" 的要求，导致两类问题：
    - 非法转义（\\(、\\sigma、\\alpha …）→ json.loads 整行失败，section 被丢弃；
    - 恰好合法的转义（\\theta、\\frac、\\nabla、\\beta、\\rho 开头的 \\t \\f \\n \\b \\r）
      → 解析"成功"但被吞成制表符 / 换页 / 换行，公式静默损坏。json_repair 同样会这样处理。

    规则：
    - \\\\、\\"、\\/、\\uXXXX 保持不变（合法且无歧义）；
    - \\b \\f \\n \\r \\t 后面不是字母时保持为 JSON 转义（如 "line\\n next"）；
    - 其余情况视为 LaTeX，把反斜杠双写。

    取舍：真实换行后紧跟字母（"a\\nb"）会被当成 LaTeX 命令保留为字面 "\\nb"。
    对以 LaTeX 为主的小抄内容，宁可如此也不能吞掉 \\nabla / \\theta。
    """

    def _fix(m: re.Match) -> str:
        escaped = m.group(1)
        if escaped in ("\\", '"', "/") or len(escaped) == 5:  # len 5 = uXXXX
            return m.group(0)
        if escaped in "bfnrt" and not m.string[m.end() : m.end() + 1].isalpha():
            return m.group(0)
        return "\\\\" + escaped

    return _BACKSLASH_ESCAPE.sub(_fix, json_line)


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
