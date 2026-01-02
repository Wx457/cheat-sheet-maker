import Latex from 'react-latex-next'
import 'katex/dist/katex.min.css'

import type { CheatSheet, ContentItem } from '../types'

interface PreviewProps {
  data: CheatSheet | null
}

/**
 * 格式化内容，将 LaTeX 定界符标准化为 KaTeX 支持的格式
 * 用于处理行内公式（text 和 definition 类型）
 */
const formatContent = (text: string): string => {
  if (!text) return ''
  
  return text
    // 修复 LaTeX 定界符: 将 \( 和 \) 替换为 $ (行内公式)
    // 在正则中，需要转义反斜杠和括号：\\\( 匹配字面量 \(
    .replace(/\\\(/g, '$')
    .replace(/\\\)/g, '$')
    // 修复 LaTeX 定界符: 将 \[ 和 \] 替换为 $$ (块级公式)
    // 在正则中，需要转义反斜杠和方括号：\\\[ 匹配字面量 \[
    .replace(/\\\[/g, '$$')
    .replace(/\\\]/g, '$$')
}

/**
 * 处理项目内容，根据类型强制包裹公式
 */
const processItemContent = (content: string, type: string): string => {
  if (!content) return ''

  // 预处理：去掉首尾空白
  let trimmed = content.trim()

  // 1. 检查是否包含 LaTeX 文本标记或已有定界符
  // 如果包含 \textbf, \text 等，或者已经有 $$, \[, \( 等定界符，说明它不需要我们要强制包裹
  // 正则解释：
  // /\\(textbf|text|section|item)/i  -> 匹配 \textbf, \text 等命令
  // /(\$\$|\\\[|\\\()/               -> 匹配 $$, \[, \( 等定界符
  const hasLatexText = /\\(textbf|text|section|item)/i.test(trimmed)
  const hasDelimiters = /(\$\$|\\\[|\\\()/.test(trimmed)

  if (type === 'equation') {
    // 如果看起来像是混合文本，或者已经自带了定界符，就当作普通内容处理（只做替换，不加壳）
    // 这样可以避免把 "\textbf{Title}: formula" 整个包在 $$ 里导致渲染失败
    if (hasLatexText || hasDelimiters) {
      return formatContent(trimmed)
    }
    
    // 只有纯裸公式（例如 "x = y"），才强制包裹块级定界符
    return `$$${trimmed}$$`
  }

  // definition 和 text 类型：统一使用 formatContent
  return formatContent(trimmed)
}

const renderItem = (item: ContentItem) => {
  const processedContent = processItemContent(item.content, item.type)
  
  return (
    <div className={`cheat-item cheat-item-${item.type}`}>
      <Latex>{processedContent}</Latex>
    </div>
  )
}

const Preview = ({ data }: PreviewProps) => {
  if (!data) {
    return (
      <div className="preview-card">
        <div className="placeholder">等待生成结果...</div>
      </div>
    )
  }

  // Preview.tsx 的 return 部分
  return (
    <>
      <style>{`
        @media print {
          /* 关键步骤 A: 消除浏览器默认的页边距、页眉页脚 */
          @page {
            margin: 0;
            size: A4 portrait;
          }

          /* 关键步骤B：强制解锁所有父容器的高度和溢出限制 */
          html, body, #root, .page, .layout, .left-pane, .right-pane, .preview-viewport {
            height: auto !important;
            min-height: 0 !important;
            overflow: visible !important;
            display: block !important;
            position: static !important;
            background: white !important; /* 去除所有深色背景 */
          }

          /* 隐藏所有不相关元素 */
          body * {
            visibility: hidden;
          }

          /* 唯独显示我们的小抄，并将其提至最顶层 */
          #cheat-sheet-content, #cheat-sheet-content * {
            visibility: visible;
          }

          #cheat-sheet-content {
            position: absolute !important;
            left: 0 !important;
            top: 0 !important;
            
            /* 强制 A4 宽度，不要用 100% */
            width: 210mm !important;
            
            /* 边距清零 (贴着浏览器边缘) */
            margin: 0 !important;
            
            /* 保留 .paper-sheet 的 10mm padding */
            /* padding: 0 !important;  <-- 这一行删掉了 */
            
            box-shadow: none !important;
            background: white !important;
            z-index: 9999 !important;
            
            /* 允许高度自动延伸 */
            height: auto !important; 
            min-height: 297mm !important;
            
            /* 强制黑色文字 */
            color: black !important;
          }

          /* 强制保留背景色 (Chrome/Edge) */
          * {
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
          }
        }

        /* --- 2. 预览窗口 (屏幕显示) --- */
        .preview-viewport {
          width: 100%;
          height: 100%;
          background-color: #525659;
          overflow-y: auto;
          display: flex;
          justify-content: center;
          padding: 40px 0; /* 增加一点上下边距，视觉更好 */
        }

        /* --- 3. 物理纸张模拟 --- */
        .paper-sheet {
          width: 210mm;
          /* 屏幕上由内容撑开高度，但至少是A4 */
          min-height: 297mm; 
          padding: 10mm;
          background-color: white;
          box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
          position: relative;
          box-sizing: border-box;
          
          /* 核心布局 */
          column-count: 2;
          column-gap: 5mm;
          column-fill: auto;
          
          /* 字体与排版 */
          font-size: 9px;
          line-height: 1.25; /* 稍微增加行高，提升可读性 */
          color: #000;
          text-align: left;
        }

        /* --- 4. 细节微调 --- */
        .katex-display { margin: 2px 0 !important; }
        .katex { font-size: 1em !important; }

        .cheat-title {
          font-size: 16px;
          font-weight: 800;
          text-align: center;
          margin-bottom: 12px;
          column-span: all;
          text-transform: uppercase;
          border-bottom: 2px solid #000;
          padding-bottom: 4px;
        }

        .cheat-section {
          margin-bottom: 8px;
          break-inside: avoid; /* 尽量保持章节完整，如果章节超长可改为 auto */
          display: inline-block;
          width: 100%;
        }

        .cheat-section-title {
          font-size: 10px;
          font-weight: 700;
          margin-bottom: 3px;
          border-bottom: 1px solid #ccc;
          padding-bottom: 1px;
          background-color: #f3f4f6;
        }

        .cheat-item {
          margin-bottom: 3px;
        }

        .cheat-item-definition {
          background-color: #fef9c3;
          border-left: 2px solid #eab308;
          padding: 2px 4px;
        }
        
        .cheat-item-equation {
          text-align: center;
          margin: 4px 0;
        }
      `}</style>

      {/* 结构说明：
         1. preview-viewport: 灰色滚动窗口 (屏幕可见，打印时虽然 hidden 但不影响绝对定位的子元素)
         2. paper-sheet (id="cheat-sheet-content"): 真正的 A4 纸 (打印时提取的主体)
      */}
      <div className="preview-viewport">
        <div id="cheat-sheet-content" className="paper-sheet">
          
          {data.sections.map((section, idx) => (
            <div key={`${section.title}-${idx}`} className="cheat-section">
              <h3 className="cheat-section-title">{section.title}</h3>
              {section.items.map((item, itemIdx) => (
                <div key={itemIdx}>
                  {renderItem(item)}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </>
  )
}

export default Preview
