def normalize_equation(content: str) -> str:
    if not content:
        return ""

    # 1. 先做统一的预处理（剥离所有已知的包裹符）
    content = content.strip()

    if content.startswith(r"\[") and content.endswith(r"\]"):
        content = content[2:-2]
    elif content.startswith("$$") and content.endswith("$$"):
        content = content[2:-2]
    elif content.startswith("$") and content.endswith("$"):
        content = content[1:-1]

    # 2. 在统一的出口处进行清洗（现在没有任何分支能逃掉这一步了）
    # 这一行代码能杀掉 99.9% 的换行隐患
    content = " ".join(content.splitlines()).strip()

    # 3. 统一加上你想要的包裹符
    return f"$${content}$$"
