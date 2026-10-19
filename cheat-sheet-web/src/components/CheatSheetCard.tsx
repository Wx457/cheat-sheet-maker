'use client'

import { useState, useEffect, useRef } from 'react'
import type { CSSProperties } from 'react'
import katex from 'katex'
import { useCheatSheetStore } from '@/stores/cheatSheetStore'
import type { UISection, ContentItem, ContentType } from '@/types'

// ─────────────────────────────────────────────────────────────────────────────
// Item type badge + styling
// ─────────────────────────────────────────────────────────────────────────────

const TYPE_META: Record<ContentType, { label: string; cardCls: string; textCls: string }> = {
  text: {
    label: 'text',
    cardCls: 'bg-white dark:bg-zinc-800 border-zinc-200 dark:border-zinc-700',
    textCls: 'text-zinc-800 dark:text-zinc-100 font-normal',
  },
  equation: {
    label: '∑ eq',
    cardCls: 'bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800',
    textCls: 'text-blue-900 dark:text-blue-100 font-mono text-sm',
  },
  definition: {
    label: 'def',
    cardCls: 'bg-amber-50 dark:bg-amber-950 border-amber-200 dark:border-amber-800',
    textCls: 'text-amber-900 dark:text-amber-100 font-medium',
  },
}

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

function MathContent({ content, isEquation }: MathContentProps) {
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
}

// ─────────────────────────────────────────────────────────────────────────────
// ItemRow — single editable item inside a section card
// View mode:  KaTeX-rendered content, click → edit
// Edit mode:  raw textarea, blur → view
// ─────────────────────────────────────────────────────────────────────────────

interface ItemRowProps {
  sectionId: string
  itemIndex: number
  item: ContentItem
  disabled: boolean
}

function ItemRow({ sectionId, itemIndex, item, disabled }: ItemRowProps) {
  const [isEditing, setIsEditing] = useState(false)
  const updateItem = useCheatSheetStore((s) => s.updateItem)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const meta = TYPE_META[item.type]

  // Focus + auto-size textarea when entering edit mode
  useEffect(() => {
    if (!isEditing || !textareaRef.current) return
    const el = textareaRef.current
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
    el.focus()
    el.selectionStart = el.selectionEnd = el.value.length
  }, [isEditing])

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    updateItem(sectionId, itemIndex, { content: e.target.value })
    e.target.style.height = 'auto'
    e.target.style.height = `${e.target.scrollHeight}px`
  }

  return (
    <div
      className={[
        'flex gap-2 rounded-md border px-3 py-2 transition-colors',
        meta.cardCls,
        item.type === 'equation' ? 'item-equation' : '',
      ].join(' ')}
    >
      {/* Type badge */}
      <span className="mt-0.5 shrink-0 rounded text-[10px] font-semibold uppercase tracking-wide text-zinc-400 w-8 text-center select-none">
        {meta.label}
      </span>

      {isEditing ? (
        /* Edit mode: raw LaTeX textarea */
        <textarea
          ref={textareaRef}
          className={`flex-1 resize-none bg-transparent outline-none leading-relaxed ${meta.textCls} placeholder:text-zinc-300 dark:placeholder:text-zinc-600`}
          rows={1}
          value={item.content}
          placeholder="(empty)"
          onChange={handleChange}
          onBlur={() => setIsEditing(false)}
        />
      ) : (
        /* View mode: KaTeX-rendered, click to edit */
        <div
          className={[
            'item-content flex-1 leading-relaxed min-h-[1.5em]',
            meta.textCls,
            !disabled ? 'cursor-text' : '',
          ].join(' ')}
          onClick={() => { if (!disabled) setIsEditing(true) }}
        >
          {item.content ? (
            <MathContent content={item.content} isEquation={item.type === 'equation'} />
          ) : (
            <span className="text-zinc-300 dark:text-zinc-600 select-none italic text-xs">
              (empty)
            </span>
          )}
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// CheatSheetCard — public component
// ─────────────────────────────────────────────────────────────────────────────

export interface CheatSheetCardProps {
  section: UISection
  setNodeRef?: (node: HTMLElement | null) => void
  attributes?: React.HTMLAttributes<HTMLElement>
  listeners?: Record<string, unknown>
  style?: CSSProperties
  isDragging?: boolean
}

export default function CheatSheetCard({
  section,
  setNodeRef,
  attributes,
  listeners,
  style,
  isDragging = false,
}: CheatSheetCardProps) {
  const updateSection = useCheatSheetStore((s) => s.updateSection)
  const deleteSection = useCheatSheetStore((s) => s.deleteSection)

  const isEditable = !section.isStreaming

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={[
        'print-card group relative flex flex-col gap-3 rounded-xl border bg-white px-5 py-4 shadow-sm',
        'dark:bg-zinc-900 dark:border-zinc-700',
        'transition-shadow',
        isDragging
          ? 'opacity-50 shadow-lg ring-2 ring-blue-400'
          : 'hover:shadow-md',
      ].join(' ')}
      {...attributes}
    >
      {/* ── Top bar: drag handle + title + delete ── */}
      <div className="flex items-center gap-2">
        <button
          className="no-print shrink-0 cursor-grab active:cursor-grabbing text-zinc-300 hover:text-zinc-500 dark:text-zinc-600 dark:hover:text-zinc-300 transition-colors touch-none"
          aria-label="Drag to reorder"
          {...(listeners as React.ButtonHTMLAttributes<HTMLButtonElement>)}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" className="opacity-60">
            <circle cx="5" cy="4" r="1.5" />
            <circle cx="5" cy="8" r="1.5" />
            <circle cx="5" cy="12" r="1.5" />
            <circle cx="11" cy="4" r="1.5" />
            <circle cx="11" cy="8" r="1.5" />
            <circle cx="11" cy="12" r="1.5" />
          </svg>
        </button>

        <input
          type="text"
          className="flex-1 bg-transparent text-base font-semibold text-zinc-900 dark:text-zinc-50 outline-none placeholder:text-zinc-300"
          value={section.title}
          placeholder="Section title"
          disabled={!isEditable}
          onChange={(e) => updateSection(section.id, { title: e.target.value })}
        />

        {section.isStreaming && (
          <span className="flex items-center gap-1 text-xs text-blue-500 font-medium select-none">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-500 animate-ping" />
            streaming
          </span>
        )}

        {isEditable && (
          <button
            className="no-print opacity-0 group-hover:opacity-100 shrink-0 rounded p-1 text-zinc-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950 transition-all"
            aria-label="Delete section"
            onClick={() => deleteSection(section.id)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" />
            </svg>
          </button>
        )}
      </div>

      {/* ── Item list ── */}
      {section.isStreaming && section.items.length === 0 ? (
        <div className="flex flex-col gap-2">
          {[60, 90, 45].map((w, i) => (
            <div
              key={i}
              className="h-4 rounded bg-zinc-100 dark:bg-zinc-800 animate-pulse"
              style={{ width: `${w}%` }}
            />
          ))}
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {(section.items ?? []).map((item, idx) => (
            <ItemRow
              key={idx}
              sectionId={section.id}
              itemIndex={idx}
              item={item}
              disabled={!isEditable}
            />
          ))}
        </div>
      )}
    </div>
  )
}
