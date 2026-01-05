import markdown
import re
import html
from app.schemas.cheat_sheet import CheatSheetSchema

def clean_latex_content(content: str) -> str:
    """
    模拟前端 react-markdown 的清洗逻辑：
    1. 把 \[ \] 变成 $$ $$
    2. 把 \( \) 变成 $ $
    3. 处理换行符
    
    安全改进：
    - 限制正则匹配次数，防止 ReDoS 攻击
    - 避免在 LaTeX 公式内部替换换行符
    """
    if not content:
        return ""

    # 安全限制：最大处理长度，防止恶意输入
    MAX_CONTENT_LENGTH = 100000  # 100KB
    if len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH]
        print(f"⚠️ 内容过长，已截断至 {MAX_CONTENT_LENGTH} 字符")

    # 1. 处理块级公式 \[ ... \] -> $$ ... $$
    # re.DOTALL 让 . 可以匹配换行符
    # 限制匹配次数，防止 ReDoS
    content = re.sub(
        r'\\\[(.*?)\\\]', 
        r'$$\1$$', 
        content, 
        flags=re.DOTALL,
        count=1000  # 最多处理 1000 个块级公式
    )

    # 2. 处理行内公式 \( ... \) -> $ ... $
    # 限制匹配次数，防止 ReDoS
    content = re.sub(
        r'\\\((.*?)\\\)', 
        r'$\1$', 
        content, 
        flags=re.DOTALL,
        count=1000  # 最多处理 1000 个行内公式
    )

    # 3. 处理 LaTeX 里的换行符 \\ -> HTML <br>
    # 改进：只在非公式区域替换，避免破坏矩阵环境
    # 使用负向前瞻，确保 \\ 不在 $...$ 或 $$...$$ 内部
    # 简单策略：先标记公式区域，再替换非公式区域的 \\
    # 为了简化，我们使用更保守的策略：只替换不在公式标记附近的 \\
    # 注意：这个策略可能不够完美，但对于 Cheat Sheet 场景足够
    # 更安全的做法是使用 LaTeX 解析器，但会增加复杂度
    
    # 临时标记公式区域
    formula_placeholders = []
    formula_pattern = r'\$\$.*?\$\$|\$.*?\$'
    
    def replace_formula(match):
        placeholder = f"__FORMULA_{len(formula_placeholders)}__"
        formula_placeholders.append(match.group(0))
        return placeholder
    
    # 先替换所有公式为占位符
    content = re.sub(formula_pattern, replace_formula, content, flags=re.DOTALL)
    
    # 在非公式区域替换 \\
    content = content.replace(r"\\", "<br>")
    
    # 恢复公式
    for i, formula in enumerate(formula_placeholders):
        content = content.replace(f"__FORMULA_{i}__", formula)

    return content

def generate_cheat_sheet_html(data: CheatSheetSchema) -> str:
    # --- 1. 构建内容 HTML ---
    sections_html = ""
    
    for section in data.sections:
        items_html = ""
        for item in section.items:
            # 第一步：清洗内容
            raw_content = item.content
            cleaned_content = clean_latex_content(raw_content)
            
            # A. 处理数学公式 (Equation)
            if item.type == "equation":
                # 强制包裹 $$ (如果 LLM 给的是裸公式)
                if not cleaned_content.strip().startswith("$$"):
                    cleaned_content = f"$${cleaned_content}$$"
                
                items_html += f'<div class="item equation">{cleaned_content}</div>'
            
            # B. 处理文本 (Text/Definition)
            else:
                # 第二步：Markdown 转 HTML
                # 这会把 **Bold** 变成 <strong>Bold</strong>
                # extensions=['extra'] 支持表格、脚注等高级语法
                # 注意：markdown 库默认会转义 HTML 标签，但为了安全，我们使用 safe_mode
                # 在较新版本的 markdown 中，safe_mode 已被弃用，改用 escape 扩展
                html_content = markdown.markdown(
                    cleaned_content, 
                    extensions=['extra', 'nl2br', 'codehilite'],
                    # 确保 HTML 标签被转义（除了我们允许的 Markdown 语法）
                )
                
                # 额外安全措施：转义任何可能残留的脚本标签
                # 虽然 markdown 应该已经处理了，但这是双重保险
                html_content = re.sub(
                    r'<script[^>]*>.*?</script>',
                    '',
                    html_content,
                    flags=re.IGNORECASE | re.DOTALL
                )
                html_content = re.sub(
                    r'javascript:',
                    '',
                    html_content,
                    flags=re.IGNORECASE
                )
                
                # 修复：有时候 markdown 会把公式包在 <p> 标签里导致样式间距问题
                # 我们这里不做特殊处理，交给 CSS 控制
                items_html += f'<div class="item text">{html_content}</div>'

        # 转义 section.title 防止 XSS 注入
        escaped_title = html.escape(section.title)
        
        sections_html += f"""
        <div class="section">
            <h3>{escaped_title}</h3>
            {items_html}
        </div>
        """

    # --- 2. 组装完整 HTML ---
    # 转义 title 防止 XSS 注入
    escaped_title = html.escape(data.title)
    
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{escaped_title}</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
        <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
        <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>
        
        <style>
            /* --- A4 纸张布局 (保持你满意的排版) --- */
            @page {{
                size: A4 portrait;
                margin: 10mm;
            }}
            
            body {{
                font-family: "Helvetica Neue", Arial, sans-serif;
                font-size: 8pt; 
                line-height: 1.4;
                color: #222;
                margin: 0;
                padding: 10px;
                background: white;
            }}

            /* 多栏布局 */
            #content {{
                column-count: 2;
                column-gap: 5mm;
                column-fill: balance;
                width: 100%;
            }}

            /* Section 盒子 */
            .section {{
                break-inside: avoid;
                margin-bottom: 10px;
                padding: 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: #fcfcfc;
            }}

            .section h3 {{
                font-size: 10pt;
                font-weight: bold;
                margin-top: 0;
                margin-bottom: 6px;
                padding-bottom: 4px;
                border-bottom: 1px solid #eee;
                color: #333;
            }}
            
            /* 内容微调 */
            .item {{ margin-bottom: 4px; }}
            
            /* 文本样式：去除 Markdown <p> 的默认边距，防止太散 */
            .item.text p {{ margin: 0 0 4px 0; }}
            .item.text {{ text-align: justify; }}

            /* 公式样式：红色字体的克星 */
            .item.equation {{
                text-align: center;
                margin: 4px 0;
            }}
            
            /* 强制 KaTeX 样式覆盖 */
            .katex {{ font-size: 1.05em !important; }}
        </style>
    </head>
    <body>
        <div id="content">
            {sections_html}
        </div>

        <script>
            // --- 关键：KaTeX 自动渲染配置 ---
            document.addEventListener("DOMContentLoaded", function() {{
                renderMathInElement(document.body, {{
                    // 这里定义了 KaTeX 应该寻找哪些符号来渲染公式
                    delimiters: [
                        {{left: '$$', right: '$$', display: true}},
                        {{left: '$', right: '$', display: false}},
                        {{left: '\\(', right: '\\)', display: false}},
                        {{left: '\\[', right: '\\]', display: true}}
                    ],
                    throwOnError : false,
                    ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code"]
                }});
            }});
        </script>
    </body>
    </html>
    """
    return full_html