import markdown
import re
from app.schemas.cheat_sheet import CheatSheetSchema

# TODO: 优化清洗逻辑，考虑使用更高级的清洗库
def clean_latex_content(content: str) -> str:
    """
    模拟前端 react-markdown 的清洗逻辑：
    1. 把 \[ \] 变成 $$ $$
    2. 把 \( \) 变成 $ $
    3. 处理换行符
    """
    if not content:
        return ""

    # 1. 处理块级公式 \[ ... \] -> $$ ... $$
    # re.DOTALL 让 . 可以匹配换行符
    content = re.sub(r'\\\[(.*?)\\\]', r'$$\1$$', content, flags=re.DOTALL)

    # 2. 处理行内公式 \( ... \) -> $ ... $
    # 这一步修复了你截图里的红色 \(\hat{\Theta}\) 问题
    content = re.sub(r'\\\((.*?)\\\)', r'$\1$', content, flags=re.DOTALL)

    # 3. 处理 LaTeX 里的换行符 \\ -> HTML <br>
    # 这一步修复了截图里到处是 \ 的问题
    # 注意：我们要小心不要破坏矩阵环境里的 \\，所以简单粗暴替换可能会有副作用，
    # 但对于 Cheat Sheet 里的普通文本换行，这是最有效的。
    content = content.replace(r"\\", "<br>")

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
                html_content = markdown.markdown(cleaned_content, extensions=['extra', 'nl2br'])
                
                # 修复：有时候 markdown 会把公式包在 <p> 标签里导致样式间距问题
                # 我们这里不做特殊处理，交给 CSS 控制
                items_html += f'<div class="item text">{html_content}</div>'

        sections_html += f"""
        <div class="section">
            <h3>{section.title}</h3>
            {items_html}
        </div>
        """

    # --- 2. 组装完整 HTML ---
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{data.title}</title>
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