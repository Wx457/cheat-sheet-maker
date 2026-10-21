'use client'

/**
 * 小抄纸面上的块级组件（Phase 7-3）
 *
 * SectionTitleBlock / ItemBlock 同时用于：
 *   - 离屏测量层（interactive=false）
 *   - 纸页上的真实渲染（interactive=true）
 * 两者 DOM 结构和排版类完全一致，interactive 只增加不占布局空间的东西
 * （hover outline、绝对定位的手柄 / 删除按钮），保证测量值 = 实际高度。
 *
 * 屏幕与打印同一套样式：item 不带方框、背景和类型标签。
 */

import { createContext, memo, useContext, useEffect, useRef, useState } from 'react'
import type { HTMLAttributes } from 'react'
import katex from 'katex'
import { useCheatSheetStore } from '@/stores/cheatSheetStore'
import type { UISection, ContentItem } from '@/types'

// ─────────────────────────────────────────────────────────────────────────────
// 编辑期间冻结版面：失焦后再重排（由 SheetCanvas 提供）
// ─────────────────────────────────────────────────────────────────────────────

export interface SheetEditApi {
  beginEdit: () => void
  endEdit: () => void
}

export const SheetEditContext = createContext<SheetEditApi>({
  beginEdit: () => {},
  endEdit: () => {},
})

// ─────────────────────────────────────────────────────────────────────────────
// KaTeX math rendering
// Handles: \[...\]  $$...$$  (display)  \(...\)  $...$  (inline)
// equation items with no delimiters → entire content as display math
// ─────────────────────────────────────────────────────────────────────────────

// Pattern order matters: $$ before $ to prevent partial match
const MATH_RE = /\\\[[\s\S]*?\\\]|\$\$[\s\S]*?\$\$|\\\([\s\S]*?\\\)|\$(?!\$)[^$\n]+?\$(?!\$)/g

function hasMathDelimiters(text: string): boolean {
  return /\\\[|\$\$|\\\(|\$/.test(text)
}

function renderKatex(formula: string, displayMode: boolean): string {
  try {
    return katex.renderToString(formula.trim(), {
      displayMode,
      throwOnError: false,
      output: 'html',
    })
  } catch {
    return formula
  }
}

interface MathContentProps {
  content: string
  isEquation: boolean
}

// memo：测量层和纸页各渲染一份，避免每次 store 变化都重跑 KaTeX
const MathContent = memo(function MathContent({ content, isEquation }: MathContentProps) {
  // equation items with no delimiters → whole string is display math
  if (isEquation && !hasMathDelimiters(content)) {
    return (
      <span dangerouslySetInnerHTML={{ __html: renderKatex(content, true) }} />
    )
  }

  // Parse content into plain-text and math segments
  const parts: React.ReactNode[] = []
  const re = new RegExp(MATH_RE.source, 'g')
  let last = 0
  let match: RegExpExecArray | null

  while ((match = re.exec(content)) !== null) {
    if (match.index > last) {
      parts.push(<span key={`t${last}`}>{content.slice(last, match.index)}</span>)
    }

    const raw = match[0]
    let formula: string
    let display: boolean

    if (raw.startsWith('\\[')) {
      formula = raw.slice(2, -2); display = true
    } else if (raw.startsWith('$$')) {
      formula = raw.slice(2, -2); display = true
    } else if (raw.startsWith('\\(')) {
      formula = raw.slice(2, -2); display = false
    } else {
      // $...$
      formula = raw.slice(1, -1); display = false
    }

    parts.push(
      <span
        key={`m${match.index}`}
        className={display ? 'block' : undefined}
        dangerouslySetInnerHTML={{ __html: renderKatex(formula, display) }}
      />
    )
    last = match.index + raw.length
  }

  if (last < content.length) {
    parts.push(<span key={`t${last}`}>{content.slice(last)}</span>)
  }

  return <>{parts}</>
})

// ─────────────────────────────────────────────────────────────────────────────
// InlineEditor — 自动增高的 textarea，字体 / 行高继承纸面
// 打开时通知 SheetCanvas 冻结版面，失焦时解冻（触发重排）
// ─────────────────────────────────────────────────────────────────────────────

interface InlineEditorProps {
  value: string
  placeholder: string
  onChange: (value: string) => void
  onDone: () => void
}

function InlineEditor({ value, placeholder, onChange, onDone }: InlineEditorProps) {
  const { beginEdit, endEdit } = useContext(SheetEditContext)
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    beginEdit()
    const el = ref.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = `${el.scrollHeight}px`
      el.focus()
      el.selectionStart = el.selectionEnd = el.value.length
    }
    return endEdit
  }, [beginEdit, endEdit])

  return (
    <textarea
      ref={ref}
      className="sheet-editor"
      rows={1}
      value={value}
      placeholder={placeholder}
      onChange={(e) => {
        onChange(e.target.value)
        e.target.style.height = 'auto'
        e.target.style.height = `${e.target.scrollHeight}px`
      }}
      onBlur={onDone}
      onKeyDown={(e) => { if (e.key === 'Escape') e.currentTarget.blur() }}
    />
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// ItemBlock — 单个 item（查看：KaTeX 渲染，点击 → 编辑原始 LaTeX）
// ─────────────────────────────────────────────────────────────────────────────

interface ItemBlockProps {
  sectionId: string
  itemIndex: number
  item: ContentItem
  interactive: boolean
  /** 测量层用于读取高度的 key */
  measureKey?: string
}

export function ItemBlock({ sectionId, itemIndex, item, interactive, measureKey }: ItemBlockProps) {
  const [isEditing, setIsEditing] = useState(false)
  const updateItem = useCheatSheetStore((s) => s.updateItem)

  return (
    <div
      data-m={measureKey}
      className={['sheet-item', interactive && !isEditing ? 'sheet-interactive' : ''].join(' ')}
      onClick={interactive && !isEditing ? () => setIsEditing(true) : undefined}
    >
      {isEditing ? (
        <InlineEditor
          value={item.content}
          placeholder="(empty)"
          onChange={(content) => updateItem(sectionId, itemIndex, { content })}
          onDone={() => setIsEditing(false)}
        />
      ) : item.content ? (
        <MathContent content={item.content} isEquation={item.type === 'equation'} />
      ) : (
        <span className="sheet-placeholder">(empty)</span>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SectionTitleBlock — section 标题（点击编辑；手柄 / 删除按钮绝对定位，no-print）
// ─────────────────────────────────────────────────────────────────────────────

interface SectionTitleBlockProps {
  section: UISection
  interactive: boolean
  measureKey?: string
  /** dnd-kit 的手柄 listeners / attributes */
  dragHandleProps?: HTMLAttributes<HTMLButtonElement>
}

export function SectionTitleBlock({ section, interactive, measureKey, dragHandleProps }: SectionTitleBlockProps) {
  const [isEditing, setIsEditing] = useState(false)
  const updateSection = useCheatSheetStore((s) => s.updateSection)
  const deleteSection = useCheatSheetStore((s) => s.deleteSection)

  return (
    <div data-m={measureKey} className="sheet-section-title group">
      <div
        className={['sheet-section-title-text', interactive && !isEditing ? 'sheet-interactive' : ''].join(' ')}
        onClick={interactive && !isEditing ? () => setIsEditing(true) : undefined}
      >
        {isEditing ? (
          <InlineEditor
            value={section.title}
            placeholder="Section title"
            onChange={(title) => updateSection(section.id, { title })}
            onDone={() => setIsEditing(false)}
          />
        ) : (
          section.title || <span className="sheet-placeholder">Section title</span>
        )}
      </div>

      {interactive && (
        <>
          <button
            className="no-print sheet-drag-handle"
            aria-label="Drag to reorder"
            {...dragHandleProps}
          >
            <svg width="10" height="14" viewBox="0 0 10 16" fill="currentColor">
              <circle cx="2.5" cy="3" r="1.5" />
              <circle cx="2.5" cy="8" r="1.5" />
              <circle cx="2.5" cy="13" r="1.5" />
              <circle cx="7.5" cy="3" r="1.5" />
              <circle cx="7.5" cy="8" r="1.5" />
              <circle cx="7.5" cy="13" r="1.5" />
            </svg>
          </button>

          <button
            className="no-print sheet-delete opacity-0 group-hover:opacity-100"
            aria-label="Delete section"
            onClick={() => deleteSection(section.id)}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" />
            </svg>
          </button>
        </>
      )}
    </div>
  )
}
