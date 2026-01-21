def normalize_equation(content: str) -> str:
    """将公式内容规范为 $$...$$ 包裹的 LaTeX 字符串。"""
    if not content:
        return ""
    content = content.strip()

    if content.startswith(r"\[") and content.endswith(r"\]"):
        content = content[2:-2].strip()

    if content.startswith("$$") and content.endswith("$$"):
        return content

    if content.startswith("$") and content.endswith("$"):
        return "$$" + content[1:-1] + "$$"

    return f"$${content}$$"

