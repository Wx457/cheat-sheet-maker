'use client'

/**
 * SheetCanvas — 所见即所得的分页小抄画布（Phase 7-2 ~ 7-4）
 *
 * 流程：
 *   ① 离屏测量层按栏宽渲染所有块，读取高度
 *   ② packSections 装箱到 (page, column)；字号为 auto 时二分查找能塞进目标页数的最大字号
 *   ③ 按页渲染 A4 纸页；打印时同一份 DOM 原样输出（globals.css @media print 只隐藏控件）
 *
 * 编辑期间冻结版面，失焦后再重排（避免正在编辑的 item 被挪到别的栏而失焦）。
 *
 * 拖拽：不用 dnd-kit sortable（它假设单列纵向列表），改为
 *   useDraggable（section 首片段的手柄）+ useDroppable（section 的每个片段），
 *   按指针在目标首片段的上 / 下半部决定插到它前面还是后面，松手后 reorderSections。
 */

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, HTMLAttributes } from 'react'
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  pointerWithin,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragMoveEvent,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'

import { useCheatSheetStore } from '@/stores/cheatSheetStore'
import { ItemBlock, SectionTitleBlock, SheetEditContext } from '@/components/SheetBlocks'
import {
  FONT_STEP_PT,
  FORMAT_PRESETS,
  MANUAL_FONT_SIZES,
  MIN_FONT_PT,
  PAGE_LIMIT_PAGES,
  columnHeightPx,
  packSections,
  sheetCssVars,
  type FontSizeSetting,
  type Fragment,
  type PageLayout,
  type PresetId,
  type SectionMeasure,
} from '@/lib/sheetLayout'
import type { PageLimit, UISection } from '@/types'

interface LayoutResult {
  pages: PageLayout[]
  fontPt: number
}

/** 拖拽插入位置：插到 sectionId 之前 / 之后 */
interface DropTarget {
  sectionId: string
  position: 'before' | 'after'
}

// ─────────────────────────────────────────────────────────────────────────────
// 测量
// ─────────────────────────────────────────────────────────────────────────────

/** 在测量层上以给定字号读取所有块高度并装箱 */
function measureAndPack(
  root: HTMLElement,
  sections: UISection[],
  presetId: PresetId,
  fontPt: number,
  hasTitle: boolean,
): PageLayout[] {
  const preset = FORMAT_PRESETS[presetId]
  root.style.setProperty('--font-size', `${fontPt}pt`)

  // 一次写入后集中读取：每个候选字号只触发一次 layout
  const heights = new Map<string, number>()
  root.querySelectorAll<HTMLElement>('[data-m]').forEach((el) => {
    heights.set(el.dataset.m!, el.getBoundingClientRect().height)
  })
  const h = (key: string) => heights.get(key) ?? 0

  const measures: SectionMeasure[] = sections.map((s) => ({
    id: s.id,
    titleH: h(`t:${s.id}`),
    itemHs: s.items.map((_, i) => h(`i:${s.id}:${i}`)),
  }))
  const colH = columnHeightPx(preset)

  return packSections(measures, {
    columns: preset.columns,
    colH,
    firstPageColH: colH - (hasTitle ? h('sheet-title') : 0),
    sectionGap: h('section-gap'),
  })
}

// ─────────────────────────────────────────────────────────────────────────────
// 纸页上的 section 片段
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 可拖拽的 section 标题：只在首片段渲染。
 * useDraggable 必须每个 section 只注册一次——dnd-kit 按 id 登记拖拽节点，
 * 若续接片段也用同一 id 注册（即使 disabled），会覆盖首片段的节点导致拖拽无法启动。
 * 外层 div 无 margin / padding，不影响测量高度。
 */
function DraggableTitle({ section }: { section: UISection }) {
  const { setNodeRef, attributes, listeners } = useDraggable({ id: section.id })
  return (
    <div ref={setNodeRef}>
      <SectionTitleBlock
        section={section}
        interactive
        dragHandleProps={{
          ...attributes,
          ...(listeners as HTMLAttributes<HTMLButtonElement>),
        }}
      />
    </div>
  )
}

interface FragmentViewProps {
  section: UISection
  frag: Fragment
  fragKey: string
  isLast: boolean
  isDragging: boolean
  dropTarget: DropTarget | null
}

function FragmentView({ section, frag, fragKey, isLast, isDragging, dropTarget }: FragmentViewProps) {
  const { setNodeRef } = useDroppable({ id: fragKey, data: { sectionId: section.id, isHead: frag.isHead } })

  const showBefore = frag.isHead && dropTarget?.sectionId === section.id && dropTarget.position === 'before'
  const showAfter = isLast && dropTarget?.sectionId === section.id && dropTarget.position === 'after'

  return (
    <div
      ref={setNodeRef}
      className={[
        'sheet-fragment',
        frag.gapBefore ? 'sheet-gap-before' : '',
        isDragging ? 'sheet-dragging' : '',
      ].join(' ')}
    >
      {showBefore && <div className="no-print sheet-drop-line sheet-drop-before" />}

      {frag.isHead && <DraggableTitle section={section} />}
      {section.items.slice(frag.start, frag.end).map((item, k) => (
        <ItemBlock
          key={frag.start + k}
          sectionId={section.id}
          itemIndex={frag.start + k}
          item={item}
          interactive
        />
      ))}

      {showAfter && <div className="no-print sheet-drop-line sheet-drop-after" />}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 工具栏（no-print）
// ─────────────────────────────────────────────────────────────────────────────

interface ToolbarProps {
  pageCount: number
  targetPages: number | null
  fontPt: number | null
}

function Toolbar({ pageCount, targetPages, fontPt }: ToolbarProps) {
  const presetId    = useCheatSheetStore((s) => s.presetId)
  const fontSize    = useCheatSheetStore((s) => s.fontSize)
  const setPresetId = useCheatSheetStore((s) => s.setPresetId)
  const setFontSize = useCheatSheetStore((s) => s.setFontSize)

  const overLimit = targetPages !== null && pageCount > targetPages
  const selectCls =
    'text-xs rounded-md border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-zinc-700 dark:text-zinc-200 px-2 py-1 outline-none'

  return (
    <div className="no-print flex flex-wrap items-center gap-3 text-xs text-zinc-600 dark:text-zinc-300">
      <div className="flex rounded-md border border-zinc-300 dark:border-zinc-600 overflow-hidden">
        {(Object.keys(FORMAT_PRESETS) as PresetId[]).map((id) => (
          <button
            key={id}
            onClick={() => setPresetId(id)}
            className={[
              'px-3 py-1 transition-colors',
              id === presetId
                ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                : 'bg-white dark:bg-zinc-800 hover:bg-zinc-100 dark:hover:bg-zinc-700',
            ].join(' ')}
          >
            {FORMAT_PRESETS[id].label}
          </button>
        ))}
      </div>

      <label className="flex items-center gap-1.5">
        字号
        <select
          className={selectCls}
          value={String(fontSize)}
          onChange={(e) => {
            const v = e.target.value
            setFontSize(v === 'auto' ? 'auto' : Number(v) as FontSizeSetting)
          }}
        >
          <option value="auto">
            {fontSize === 'auto' && fontPt !== null ? `自动 · ${fontPt}pt` : '自动'}
          </option>
          {MANUAL_FONT_SIZES.map((pt) => (
            <option key={pt} value={pt}>{pt}pt</option>
          ))}
        </select>
      </label>

      <span className={overLimit ? 'font-semibold text-red-600 dark:text-red-400' : ''}>
        {pageCount} 页{targetPages !== null && ` / 限 ${targetPages} 页`}
        {overLimit && ' · 超出页数限制'}
      </span>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SheetCanvas — public component
// ─────────────────────────────────────────────────────────────────────────────

interface SheetCanvasProps {
  title: string
  pageLimit: PageLimit
}

export default function SheetCanvas({ title, pageLimit }: SheetCanvasProps) {
  const sections        = useCheatSheetStore((s) => s.sections)
  const status          = useCheatSheetStore((s) => s.status)
  const presetId        = useCheatSheetStore((s) => s.presetId)
  const fontSize        = useCheatSheetStore((s) => s.fontSize)
  const reorderSections = useCheatSheetStore((s) => s.reorderSections)

  const preset = FORMAT_PRESETS[presetId]
  const targetPages = PAGE_LIMIT_PAGES[pageLimit] ?? null

  const measureRef = useRef<HTMLDivElement>(null)
  const [layout, setLayout] = useState<LayoutResult | null>(null)

  // ── 编辑冻结 ───────────────────────────────────────────────────────────────
  const editCountRef = useRef(0)
  const [frozen, setFrozen] = useState(false)
  const beginEdit = useCallback(() => {
    editCountRef.current += 1
    setFrozen(true)
  }, [])
  const endEdit = useCallback(() => {
    editCountRef.current -= 1
    if (editCountRef.current === 0) setFrozen(false)
  }, [])
  const editApi = useMemo(() => ({ beginEdit, endEdit }), [beginEdit, endEdit])

  // ── 字体加载完成后重新测量（含 KaTeX 字体懒加载） ─────────────────────────
  const [fontEpoch, setFontEpoch] = useState(0)
  useEffect(() => {
    const fonts = document.fonts
    const bump = () => setFontEpoch((e) => e + 1)
    fonts.addEventListener('loadingdone', bump)
    fonts.ready.then(bump)
    return () => fonts.removeEventListener('loadingdone', bump)
  }, [])

  // ── 测量 + 装箱（+ 自动字号） ───────────────────────────────────────────────
  useLayoutEffect(() => {
    if (frozen) return
    const root = measureRef.current
    if (!root) return
    const hasTitle = !!title
    const pack = (pt: number) => measureAndPack(root, sections, presetId, pt, hasTitle)

    let fontPt: number
    let pages: PageLayout[]

    if (fontSize !== 'auto') {
      fontPt = fontSize
      pages = pack(fontPt)
    } else if (targetPages === null) {
      fontPt = preset.baseFontPt
      pages = pack(fontPt)
    } else {
      // 二分查找页数 ≤ 目标的最大字号（候选：MIN_FONT_PT + k * FONT_STEP_PT）
      let lo = 0
      let hi = Math.round((preset.baseFontPt - MIN_FONT_PT) / FONT_STEP_PT)
      let best: LayoutResult | null = null
      while (lo <= hi) {
        const mid = Math.floor((lo + hi) / 2)
        const pt = MIN_FONT_PT + mid * FONT_STEP_PT
        const candidate = pack(pt)
        if (candidate.length <= targetPages) {
          best = { pages: candidate, fontPt: pt }
          lo = mid + 1
        } else {
          hi = mid - 1
        }
      }
      // 缩到下限仍超出 → 用最小字号，工具栏提示超出
      if (best) {
        fontPt = best.fontPt
        pages = best.pages
      } else {
        fontPt = MIN_FONT_PT
        pages = pack(fontPt)
      }
    }

    // 测量层恢复到最终字号（与下面 React 渲染的 style 一致）
    root.style.setProperty('--font-size', `${fontPt}pt`)
    setLayout({ pages, fontPt })
  }, [sections, title, presetId, fontSize, targetPages, preset, fontEpoch, frozen])

  // ── 拖拽 ───────────────────────────────────────────────────────────────────
  const sensors = useSensors(
    // 移动 4px 才激活，避免误触
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
  )
  const [activeId, setActiveId] = useState<string | null>(null)
  const [dropTarget, setDropTarget] = useState<DropTarget | null>(null)
  const activeSection = sections.find((s) => s.id === activeId) ?? null

  function handleDragStart(event: DragStartEvent) {
    setActiveId(event.active.id as string)
  }

  function handleDragMove(event: DragMoveEvent) {
    const { over, activatorEvent, delta } = event
    if (!over) { setDropTarget(null); return }
    const { sectionId, isHead } = over.data.current as { sectionId: string; isHead: boolean }
    const pointerY = (activatorEvent as PointerEvent).clientY + delta.y
    const upperHalf = pointerY < over.rect.top + over.rect.height / 2
    const next: DropTarget = { sectionId, position: isHead && upperHalf ? 'before' : 'after' }
    setDropTarget((prev) =>
      prev?.sectionId === next.sectionId && prev.position === next.position ? prev : next,
    )
  }

  function handleDragEnd(event: DragEndEvent) {
    const target = dropTarget
    setActiveId(null)
    setDropTarget(null)
    if (!target || !event.over) return

    const from = sections.findIndex((s) => s.id === event.active.id)
    let to = sections.findIndex((s) => s.id === target.sectionId)
    if (from === -1 || to === -1) return
    if (target.position === 'after') to += 1
    if (from < to) to -= 1
    if (from !== to) reorderSections(from, to)
  }

  function handleDragCancel() {
    setActiveId(null)
    setDropTarget(null)
  }

  // ── 渲染 ───────────────────────────────────────────────────────────────────
  const sectionById = useMemo(() => new Map(sections.map((s) => [s.id, s])), [sections])
  const fontPt = layout?.fontPt ?? preset.baseFontPt
  const sheetStyle = sheetCssVars(preset, fontPt) as CSSProperties
  const pages = layout?.pages ?? []

  // 每个 section 的最后一个片段（「插到后面」的插入线画在这里）
  const lastFragKey = new Map<string, string>()
  pages.forEach((p, pi) => p.columns.forEach((col, ci) => col.forEach((f) => {
    lastFragKey.set(f.sectionId, `${pi}:${ci}:${f.sectionId}:${f.start}`)
  })))

  const isEmpty = sections.length === 0

  return (
    <SheetEditContext.Provider value={editApi}>
      {/* @page 不支持 var()：按预设注入 */}
      <style>{`@page { size: A4 ${preset.orientation}; margin: 0; }`}</style>

      {/* ① 离屏测量层：与纸页相同的类和 CSS 变量，栏宽 = 纸页上的栏宽 */}
      <div className="sheet-measurer" aria-hidden>
        <div ref={measureRef} className="sheet" style={sheetStyle}>
          {title && (
            <div className="sheet-measure-full">
              <div data-m="sheet-title" className="sheet-title">{title}</div>
            </div>
          )}
          <div data-m="section-gap" className="sheet-measure-gap" />
          <div className="sheet-measure-col">
            {sections.map((s) => (
              <div key={s.id}>
                <SectionTitleBlock section={s} interactive={false} measureKey={`t:${s.id}`} />
                {s.items.map((item, i) => (
                  <ItemBlock
                    key={i}
                    sectionId={s.id}
                    itemIndex={i}
                    item={item}
                    interactive={false}
                    measureKey={`i:${s.id}:${i}`}
                  />
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="sheet-canvas print-block">
        {!isEmpty && (
          <Toolbar pageCount={pages.length} targetPages={targetPages} fontPt={layout?.fontPt ?? null} />
        )}

        {isEmpty ? (
          status !== 'loading' && (
            <div className="no-print flex flex-col items-center justify-center gap-3 py-24 text-zinc-400 dark:text-zinc-600 select-none">
              <p className="text-sm">No sections yet. Generate a cheat sheet to get started.</p>
            </div>
          )
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={pointerWithin}
            onDragStart={handleDragStart}
            onDragMove={handleDragMove}
            onDragEnd={handleDragEnd}
            onDragCancel={handleDragCancel}
          >
            <div className="sheet sheet-pages print-block" style={sheetStyle}>
              {pages.map((page, pi) => {
                const overLimit = targetPages !== null && pi >= targetPages
                return (
                  <div key={pi} className="sheet-page-wrap print-block">
                    <div className={['sheet-page', overLimit ? 'sheet-page-over' : ''].join(' ')}>
                      {pi === 0 && title && <div className="sheet-title">{title}</div>}
                      <div className="sheet-columns">
                        {page.columns.map((col, ci) => (
                          <div key={ci} className="sheet-column">
                            {col.map((frag) => {
                              const section = sectionById.get(frag.sectionId)
                              if (!section) return null   // 冻结期间版面可能引用已变化的数据
                              const fragKey = `${pi}:${ci}:${frag.sectionId}:${frag.start}`
                              return (
                                <FragmentView
                                  key={fragKey}
                                  section={section}
                                  frag={frag}
                                  fragKey={fragKey}
                                  isLast={lastFragKey.get(frag.sectionId) === fragKey}
                                  isDragging={activeId === frag.sectionId}
                                  dropTarget={dropTarget}
                                />
                              )
                            })}
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className={['no-print sheet-page-label', overLimit ? 'text-red-500' : ''].join(' ')}>
                      {pi + 1} / {pages.length}{overLimit && ' · 超出页数限制'}
                    </div>
                  </div>
                )
              })}
            </div>

            <DragOverlay>
              {activeSection && (
                <div className="pointer-events-none rounded-md bg-white dark:bg-zinc-800 px-3 py-1.5 text-xs font-semibold text-zinc-800 dark:text-zinc-100 shadow-lg ring-1 ring-blue-400">
                  {activeSection.title || 'Section'}
                </div>
              )}
            </DragOverlay>
          </DndContext>
        )}
      </div>
    </SheetEditContext.Provider>
  )
}
