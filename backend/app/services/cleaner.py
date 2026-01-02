import re
from json_repair import repair_json


def clean_raw_text(text: str) -> str:
    """
    清洗用户/插件输入的原始文本。
    
    功能：
    1. 去除不可见的零宽字符
    2. 将连续的空白字符（换行、空格、Tab）压缩为标准格式
    3. 简单剥离 HTML 标签（如 <div...>）
    
    Args:
        text: 原始输入文本
        
    Returns:
        清洗后的文本
    """
    if not text:
        return ""
    
    # 去除零宽字符（零宽空格、零宽非断字符、零宽断字符、左到右标记、右到左标记等）
    text = re.sub(r'[\u200B-\u200D\uFEFF\u200E\u200F]', '', text)
    
    # 压缩连续的空白字符（保留单个换行和空格）
    # 将多个连续的空格、Tab 压缩为单个空格
    text = re.sub(r'[ \t]+', ' ', text)
    # 将多个连续的换行压缩为最多两个换行（保留段落分隔）
    text = re.sub(r'\n{3,}', '\n\n', text)
    # 去除行首行尾的空白
    text = re.sub(r'[ \t]+(\n)', r'\1', text)
    text = re.sub(r'(\n)[ \t]+', r'\1', text)
    
    # 简单剥离 HTML 标签（不处理嵌套和属性中的内容）
    text = re.sub(r'<[^>]+>', '', text)
    
    # 去除首尾空白
    text = text.strip()
    
    return text


def repair_json_string(json_str: str) -> str:
    """
    修复 LLM 返回的"不规范 JSON"字符串。
    
    使用 json_repair 库来修复 JSON 字符串，提供更强的稳健性。
    
    功能：
    1. 去除 Markdown 代码块标记（如 ```json 和 ```）
    2. 使用 json_repair 库修复 JSON 字符串
    
    Args:
        json_str: LLM 返回的原始 JSON 字符串
        
    Returns:
        修复后的 JSON 字符串
    """
    if not json_str:
        return ""
    
    # 1. 简单的 Markdown 清洗（保留这个是个好习惯）
    json_str = json_str.strip()
    if json_str.startswith("```json"):
        json_str = json_str[7:]
    elif json_str.startswith("```"):
        json_str = json_str[3:]
    if json_str.endswith("```"):
        json_str = json_str[:-3]
    json_str = json_str.strip()
    
    # 2. 使用 json_repair 强力修复
    # return_objects=False 让它返回修复后的 JSON string
    repaired = repair_json(json_str, return_objects=False)
    return repaired

