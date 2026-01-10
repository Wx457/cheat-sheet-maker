import markdown
import re
import html
from app.schemas.cheat_sheet import CheatSheetSchema

class LatexProtector:
    """
    【围栏策略核心类】
    用于在 Markdown 渲染前保护 LaTeX 公式，防止反斜杠被吞或下划线被误转义。
    """
    def __init__(self):
        self.map = {}
        self.counter = 0

    def protect(self, content: str) -> str:
        # 1. 保护块级公式 $$...$$ 和 \[...\]
        # re.DOTALL 允许 . 匹配换行符
        # non-greedy 匹配 .*?
        def replace_block(match):
            key = f"__LATEX_BLOCK_{self.counter}__"
            self.map[key] = match.group(0) # 原样保存，一个字符都不动
            self.counter += 1
            return key
        
        content = re.sub(r'(\$\$.*?\$\$|\\\[.*?\\\])', replace_block, content, flags=re.DOTALL)

        # 2. 保护行内公式 $...$ 和 \(...\)
        def replace_inline(match):
            key = f"__LATEX_INLINE_{self.counter}__"
            self.map[key] = match.group(0)
            self.counter += 1
            return key

        # 注意：这里要小心不匹配到 \$ (转义的美元符号)
        # 匹配 \(...\) OR $...$
        content = re.sub(r'(\\\(.*?\ উন্ন\)|\$[^\$]+?\$)', replace_inline, content, flags=re.DOTALL)
        
        return content

    def restore(self, content: str) -> str:
        # 还原所有占位符
        for key, value in self.map.items():
            content = content.replace(key, value)
        return content

def clean_content_with_protection(content: str) -> str:
    """
    通用清洗函数：适用于 Text 和 Equation 类型
    """
    if not content:
        return ""
    
    # 0. 初始化保护器
    protector = LatexProtector()
    
    # 1. 【关键】先把所有 LaTeX 公式挖走！
    # 此时 content 里的公式变成了 __LATEX_INLINE_0__
    protected_content = protector.protect(content)
    
    # 2. 处理普通文本的换行
    # 只有不在公式里的 \\ 才会变成 <br>。
    # 因为公式已经被换成了占位符，这里怎么 replace 都不怕坏事。
    protected_content = protected_content.replace(r"\\", "<br>")
    
    # 3. Markdown 渲染
    # 处理 **Bold**, *Italic*, List 等
    html_content = markdown.markdown(
        protected_content, 
        extensions=['extra', 'nl2br', 'codehilite']
    )
    
    # 4. 【关键】把公式填回去
    final_content = protector.restore(html_content)
    
    return final_content

def generate_cheat_sheet_html(data: CheatSheetSchema) -> str:
    sections_html = ""
    
    for section in data.sections:
        items_html = ""
        for item in section.items:
            raw_content = item.content
            
            # 统一使用“围栏策略”清洗
            # 不再区分 equation/text 的清洗逻辑，因为 protector 会自动识别公式
            cleaned_html = clean_content_with_protection(raw_content)
            
            if item.type == "equation":
                # Equation 类型：居中显示
                items_html += f'<div class="item equation">{cleaned_html}</div>'
            else:
                # Text 类型：正常显示
                items_html += f'<div class="item text">{cleaned_html}</div>'

        escaped_title = html.escape(section.title)
        
        sections_html += f"""
        <div class="section">
            <h3>{escaped_title}</h3>
            {items_html}
        </div>
        """

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
            @page {{ size: A4 portrait; margin: 10mm; }}
            body {{
                font-family: "Helvetica Neue", Arial, sans-serif;
                font-size: 8pt; 
                line-height: 1.4;
                color: #222;
                margin: 0;
                padding: 10px;
                background: white;
            }}
            #content {{
                column-count: 2;
                column-gap: 5mm;
                column-fill: balance;
                width: 100%;
            }}
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
            .item {{ margin-bottom: 4px; }}
            .item.text p {{ margin: 0 0 4px 0; }}
            .item.text {{ text-align: justify; }}
            
            .item.equation {{
                text-align: center;
                margin: 4px 0;
                overflow-x: auto;
            }}
            /* 确保公式和文本混排时对齐 */
            .item p {{ display: inline; }}
            
            .katex {{ font-size: 1.05em !important; }}
        </style>
    </head>
    <body>
        <div id="content">
            {sections_html}
        </div>

        <script>
            document.addEventListener("DOMContentLoaded", function() {{
                renderMathInElement(document.body, {{
                    // 这里定义了所有可能的定界符
                    delimiters: [
                        {{left: '$$', right: '$$', display: true}},
                        {{left: '$', right: '$', display: false}},
                        {{left: '\\(', right: '\\)', display: false}},
                        {{left: '\\[', right: '\\]', display: true}}
                    ],
                    throwOnError : false
                }});
            }});
        </script>
    </body>
    </html>
    """
    return full_html