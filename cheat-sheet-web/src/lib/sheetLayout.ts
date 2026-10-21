// ─────────────────────────────────────────────────────────────────────────────
// 小抄分页排版（Phase 7-2 ~ 7-4，见 UPGRADE_PLAN.md）
//
// 流程：离屏测量每个块的高度 → packSections 装箱到 (page, column) → 按页渲染。
// 屏幕与打印使用同一份 DOM 和同一套 mm 尺寸，实现所见即所得。
// 本文件只放纯数据 / 纯函数，不碰 DOM。
// ─────────────────────────────────────────────────────────────────────────────

import type { PageLimit } from '@/types'

// ── 格式预设 ───────────────────────────────────────────────────────────────

export type PresetId = 'two-column' | 'dense' | 'study-notes'

export interface FormatPreset {
  label: string
  /** A4 纵向 / 横向 */
  orientation: 'portrait' | 'landscape'
  columns: number
  /** 基准字号（pt）：手动模式的默认值、自动模式的上限 */
  baseFontPt: number
  /** 纸页内边距（即打印页边距，mm） */
  padMm: number
  /** 栏间距（mm） */
  colGapMm: number
}

export const FORMAT_PRESETS: Record<PresetId, FormatPreset> = {
  'two-column':  { label: '双栏标准', orientation: 'portrait', columns: 2, baseFontPt: 9,  padMm: 10, colGapMm: 6 },
  'dense':       { label: '密集小抄', orientation: 'portrait', columns: 3, baseFontPt: 7,  padMm: 7,  colGapMm: 4 },
  'study-notes': { label: '笔记本',   orientation: 'portrait', columns: 1, baseFontPt: 11, padMm: 15, colGapMm: 0 },
}

export const DEFAULT_PRESET: PresetId = 'two-column'

/** 字号设置：'auto' = 按页数限制自动缩字号 */
export type FontSizeSetting = 'auto' | number

export const MIN_FONT_PT = 5
export const FONT_STEP_PT = 0.25
/** 手动字号下拉的可选值 */
export const MANUAL_FONT_SIZES = [6, 6.5, 7, 7.5, 8, 8.5, 9, 9.5, 10, 11, 12]

/** page_limit → 目标物理页数（一张纸正反面算 2 页）；null = 不限制 */
export const PAGE_LIMIT_PAGES: Record<PageLimit, number | null> = {
  '1_side': 1,
  '1_page': 2,
  '2_pages': 4,
  unlimited: null,
}

// ── 纸页几何 ───────────────────────────────────────────────────────────────

const A4 = { short: 210, long: 297 }
const PX_PER_MM = 96 / 25.4
/** 每栏留的余量：防子像素取整把最后一行挤到下一页 */
const COLUMN_SAFETY_PX = 2

export function pageSizeMm(preset: FormatPreset) {
  return preset.orientation === 'portrait'
    ? { w: A4.short, h: A4.long }
    : { w: A4.long, h: A4.short }
}

/** 纸页根节点上的 CSS 变量（屏幕 / 打印 / 测量层共用） */
export function sheetCssVars(preset: FormatPreset, fontPt: number): Record<string, string> {
  const { w, h } = pageSizeMm(preset)
  return {
    '--page-w': `${w}mm`,
    '--page-h': `${h}mm`,
    '--page-pad': `${preset.padMm}mm`,
    '--cols': String(preset.columns),
    '--col-gap': `${preset.colGapMm}mm`,
    '--font-size': `${fontPt}pt`,
  }
}

/** 内容区（扣掉页边距）的栏高，px */
export function columnHeightPx(preset: FormatPreset): number {
  const { h } = pageSizeMm(preset)
  return (h - 2 * preset.padMm) * PX_PER_MM - COLUMN_SAFETY_PX
}

// ── 装箱 ───────────────────────────────────────────────────────────────────

export interface SectionMeasure {
  id: string
  titleH: number
  itemHs: number[]
}

export interface PackGeometry {
  columns: number
  /** 普通页的栏高 */
  colH: number
  /** 第 1 页的栏高（扣掉小抄标题） */
  firstPageColH: number
  /** 非栏顶的 section 片段上方的间距 */
  sectionGap: number
}

/** section 在某一栏中的一段：items[start, end) */
export interface Fragment {
  sectionId: string
  /** 是否是 section 的第一段（显示标题、拖拽手柄） */
  isHead: boolean
  start: number
  end: number
  /** 是否在上方留 sectionGap（栏顶片段不留） */
  gapBefore: boolean
}

export interface PageLayout {
  columns: Fragment[][]
}

/**
 * 按顺序把 section 的标题和 item 填入各栏：
 * - 不可拆分单位是 item，section 可跨栏 / 跨页，续接处不重复标题
 * - 标题必须与第一个 item 同栏
 * - 比整栏还高的 item 照常放置（溢出），不拆分
 */
export function packSections(measures: SectionMeasure[], geom: PackGeometry): PageLayout[] {
  const pages: PageLayout[] = []
  let page = -1
  let col = 0
  let y = 0

  const newPage = () => {
    pages.push({ columns: Array.from({ length: geom.columns }, () => []) })
    page += 1
    col = 0
    y = 0
  }
  const nextColumn = () => {
    col += 1
    y = 0
    if (col >= geom.columns) newPage()
  }
  const capacity = () => (page === 0 ? geom.firstPageColH : geom.colH)
  const push = (f: Fragment) => pages[page].columns[col].push(f)

  newPage()

  for (const m of measures) {
    let gap = y > 0 ? geom.sectionGap : 0
    const firstItemH = m.itemHs[0] ?? 0
    if (y > 0 && y + gap + m.titleH + firstItemH > capacity()) {
      nextColumn()
      gap = 0
    }

    let frag: Fragment = { sectionId: m.id, isHead: true, start: 0, end: 0, gapBefore: gap > 0 }
    y += gap + m.titleH

    m.itemHs.forEach((h, i) => {
      const fragHasContent = frag.end > frag.start || !frag.isHead
      if (y + h > capacity() && y > 0 && fragHasContent) {
        push(frag)
        nextColumn()
        frag = { sectionId: m.id, isHead: false, start: i, end: i, gapBefore: false }
      }
      frag.end = i + 1
      y += h
    })
    push(frag)
  }

  return pages
}
