'use client'

import { create } from 'zustand'
import type { UISection, ContentItem, CheatSheetRecord, GenerationParams, Section } from '@/types'
import { DEFAULT_PRESET, type FontSizeSetting, type PresetId } from '@/lib/sheetLayout'

// ─────────────────────────────────────────────────────────────────────────────
// State shape
// ─────────────────────────────────────────────────────────────────────────────

export interface SavedSnapshot {
  title: string
  sections: UISection[]
}

/**
 * 8-2：重新生成完成、尚未首次保存的新版本。保存时 POST 为课程内新版本
 * （origin = regenerate，parent_sheet_id = 重新生成前的版本）
 */
export interface PendingVersion {
  origin: 'regenerate'
  parentSheetId: string
}

export type StreamStatus =
  | 'idle'
  | 'loading'        // 刷新后按 sheetId 从后端恢复中（3-4-c）
  | 'connecting'     // SSE 连接中
  | 'streaming'      // 卡片流式渲染中
  | 'regenerating'   // 8-2：部分重新生成中（其余 section 保持可见）
  | 'complete'
  | 'error'

interface CheatSheetState {
  // ── 小抄数据 ────────────────────────────────────────────────────────────
  metaTitle: string           // 后端推送的 {"_type":"meta","title":"..."} 标题
  sections: UISection[]       // 所有 section（含前端 id 和 isStreaming 标志）
  sheetId: string | null      // 已保存到后端的小抄 id（首次保存前为 null）
  courseId: string | null     // 第 8 点：小抄所属课程（保存 / 加载后已知）
  version: number | null      // 第 8 点：课程内版本号（保存 / 加载后已知）
  /**
   * 最近一次成功保存（或从后端恢复）的内容，首次保存前为 null。
   * 与当前 metaTitle / sections 做引用比较判断是否有未保存修改（每次编辑都会生成新数组）。
   */
  savedSnapshot: SavedSnapshot | null
  /** 当前内容是从本标签页的未保存草稿恢复的（6-6）；保存成功 / reset / 从后端加载后清除 */
  restoredFromDraft: boolean
  /** 生成当前版本所用的参数（加载的版本 = 其 generation_params；新生成 = 这次请求的参数） */
  generationParams: GenerationParams | null
  /** 8-2：重新生成出的、尚未保存的新版本（首次保存成功后清除） */
  pendingVersion: PendingVersion | null

  // ── 8-2 部分重新生成 ────────────────────────────────────────────────────
  /** 选择模式：点击 section 切换选中，不进入编辑 */
  selecting: boolean
  selectedIds: string[]
  /** 正在重写、尚未收到新内容的 section */
  regeneratingIds: string[]

  // ── 排版设置（Phase 7；用户偏好，reset 不清空，暂不随小抄保存） ──────────
  presetId: PresetId
  fontSize: FontSizeSetting

  // ── 流式状态 ────────────────────────────────────────────────────────────
  status: StreamStatus
  error: string | null

  // ── 排版 actions ────────────────────────────────────────────────────────
  setPresetId: (id: PresetId) => void
  setFontSize: (size: FontSizeSetting) => void

  // ── 持久化 actions（由 editor page 调用） ───────────────────────────────
  setSheetId: (id: string | null) => void
  /** 首次保存（POST）成功：记下 id / 课程 / 版本号 */
  setSavedRecord: (record: Pick<CheatSheetRecord, 'id' | 'course_id' | 'version'>) => void
  markSaved: (snapshot: SavedSnapshot) => void
  /** 用后端记录填充 store（刷新恢复），status → complete，并以此为已保存基线 */
  loadSheet: (record: CheatSheetRecord) => void
  /**
   * 用本标签页的未保存草稿填充 store（6-6 缺口 2）。savedSnapshot 置空 → isDirty，
   * 自动保存会继续重试（sheetId 为空则 POST，否则 PUT）
   */
  restoreDraft: (draft: {
    title: string
    sections: Pick<UISection, 'title' | 'items'>[]
    sheetId: string | null
    /** 8-2：草稿是一个尚未保存的重新生成版本 */
    pending?: { version: PendingVersion; generationParams: GenerationParams | null; courseId: string | null }
  }) => void
  /** 记下这次生成所用的参数（首次保存时作为 generation_params） */
  setGenerationParams: (params: GenerationParams | null) => void

  // ── 8-2 部分重新生成 actions ────────────────────────────────────────────
  /** 进入 / 退出选择模式（都会清空选择） */
  setSelecting: (on: boolean) => void
  toggleSelected: (id: string) => void
  selectAll: () => void
  clearSelection: () => void
  /** 开始重写这些 section：status → regenerating，退出选择模式 */
  startRegenerate: (ids: string[]) => void
  /** 用新内容原位替换（保留 id 和位置） */
  applyRegeneratedSection: (id: string, section: Section) => void
  /** 结束重写：restore 不为空时把这些 section 恢复为原内容（取消 / 失败），status → complete */
  endRegenerate: (restore: Map<string, Section> | null) => void
  /**
   * 重新生成成功：当前内容成为一个尚未保存的新版本（sheetId / version / savedSnapshot 置空 → 自动保存 POST）
   */
  markAsNewVersion: (version: PendingVersion, generationParams: GenerationParams) => void

  // ── 流式写入 actions（由 streaming.ts 调用） ────────────────────────────
  setStatus: (status: StreamStatus) => void
  setError: (msg: string | null) => void
  setMetaTitle: (title: string) => void
  /** 追加一个新 section（流式场景：isStreaming=true），返回生成的 id */
  addSection: (section: Omit<UISection, 'id' | 'isStreaming'>) => string
  /** 将 section 标记为接收完成（isStreaming=false） */
  markSectionComplete: (id: string) => void
  /**
   * 按 title 归并 section：title 已存在则追加 items，否则新建。
   * 解决后端逐 item yield 导致同一 section 重复出现的问题。
   */
  mergeOrAddSection: (section: Omit<UISection, 'id' | 'isStreaming'>) => string
  /** 清空所有 section，重置为 idle（新一轮生成前调用） */
  reset: () => void

  // ── 用户编辑 actions（由 UI 组件调用） ─────────────────────────────────
  /** 更新 section 的标题或 items */
  updateSection: (id: string, patch: Partial<Pick<UISection, 'title' | 'items'>>) => void
  /** 更新某 section 内某条 item 的内容 */
  updateItem: (sectionId: string, itemIndex: number, patch: Partial<ContentItem>) => void
  /** 删除一个 section */
  deleteSection: (id: string) => void
  /** 拖拽排序：交换 fromIndex 和 toIndex 位置 */
  reorderSections: (fromIndex: number, toIndex: number) => void
}

// ─────────────────────────────────────────────────────────────────────────────
// 生成唯一 ID（不依赖 crypto，SSR 安全）
// ─────────────────────────────────────────────────────────────────────────────
let _idCounter = 0
function nextId(): string {
  return `section-${Date.now()}-${++_idCounter}`
}

// ─────────────────────────────────────────────────────────────────────────────
// Store
// ─────────────────────────────────────────────────────────────────────────────

export const useCheatSheetStore = create<CheatSheetState>((set) => ({
  // ── 初始状态 ──────────────────────────────────────────────────────────────
  metaTitle: '',
  sections: [],
  sheetId: null,
  courseId: null,
  version: null,
  savedSnapshot: null,
  restoredFromDraft: false,
  generationParams: null,
  pendingVersion: null,
  selecting: false,
  selectedIds: [],
  regeneratingIds: [],
  presetId: DEFAULT_PRESET,
  fontSize: 'auto',
  status: 'idle',
  error: null,

  // ── 排版 ──────────────────────────────────────────────────────────────────
  setPresetId: (presetId) => set({ presetId }),

  setFontSize: (fontSize) => set({ fontSize }),

  // ── 持久化 ────────────────────────────────────────────────────────────────
  setSheetId: (sheetId) => set({ sheetId }),

  setSavedRecord: (record) =>
    set({ sheetId: record.id, courseId: record.course_id, version: record.version, pendingVersion: null }),

  setGenerationParams: (generationParams) => set({ generationParams }),

  markSaved: (savedSnapshot) => set({ savedSnapshot, restoredFromDraft: false }),

  loadSheet: (record) => {
    const sections: UISection[] = record.sections.map((s) => ({
      title: s.title,
      items: s.items,
      id: nextId(),
      isStreaming: false,
    }))
    set({
      sheetId: record.id,
      courseId: record.course_id,
      version: record.version,
      metaTitle: record.title,
      sections,
      // 恢复的内容即已保存内容，避免恢复后立刻触发一次无意义的 PUT
      savedSnapshot: { title: record.title, sections },
      restoredFromDraft: false,
      generationParams: record.generation_params,
      pendingVersion: null,
      status: 'complete',
      error: null,
    })
  },

  restoreDraft: (draft) =>
    set({
      sheetId: draft.sheetId,
      metaTitle: draft.title,
      sections: draft.sections.map((s) => ({
        title: s.title,
        items: s.items,
        id: nextId(),
        isStreaming: false,
      })),
      savedSnapshot: null,
      restoredFromDraft: true,
      ...(draft.pending
        ? {
            pendingVersion: draft.pending.version,
            generationParams: draft.pending.generationParams,
            courseId: draft.pending.courseId,
          }
        : {}),
      status: 'complete',
      error: null,
    }),

  // ── 8-2 部分重新生成 ──────────────────────────────────────────────────────
  setSelecting: (selecting) => set({ selecting, selectedIds: [] }),

  toggleSelected: (id) =>
    set((state) => ({
      selectedIds: state.selectedIds.includes(id)
        ? state.selectedIds.filter((x) => x !== id)
        : [...state.selectedIds, id],
    })),

  selectAll: () => set((state) => ({ selectedIds: state.sections.map((s) => s.id) })),

  clearSelection: () => set({ selectedIds: [] }),

  startRegenerate: (ids) =>
    set({ status: 'regenerating', regeneratingIds: ids, selecting: false, selectedIds: [] }),

  applyRegeneratedSection: (id, section) =>
    set((state) => ({
      sections: state.sections.map((s) =>
        s.id === id ? { ...s, title: section.title, items: section.items } : s
      ),
      regeneratingIds: state.regeneratingIds.filter((x) => x !== id),
    })),

  endRegenerate: (restore) =>
    set((state) => ({
      sections: restore
        ? state.sections.map((s) => {
            const original = restore.get(s.id)
            return original ? { ...s, title: original.title, items: original.items } : s
          })
        : state.sections,
      regeneratingIds: [],
      status: 'complete',
    })),

  markAsNewVersion: (pendingVersion, generationParams) =>
    set({
      pendingVersion,
      generationParams,
      sheetId: null,
      version: null,
      savedSnapshot: null,
      restoredFromDraft: false,
    }),

  // ── 流式写入 ──────────────────────────────────────────────────────────────
  setStatus: (status) => set({ status }),

  setError: (error) => set({ error, status: 'error' }),

  setMetaTitle: (title) => set({ metaTitle: title }),

  addSection: (sectionData) => {
    const id = nextId()
    set((state) => ({
      sections: [
        ...state.sections,
        {
          ...sectionData,
          id,
          isStreaming: true,   // 刚推入时标记为流式中
        },
      ],
    }))
    return id   // 返回 ID，供调用方立即调用 markSectionComplete
  },

  markSectionComplete: (id) =>
    set((state) => ({
      sections: state.sections.map((s) =>
        s.id === id ? { ...s, isStreaming: false } : s
      ),
    })),

  mergeOrAddSection: (sectionData) => {
    let id = ''
    set((state) => {
      const existing = state.sections.find((s) => s.title === sectionData.title)
      if (existing) {
        id = existing.id
        return {
          sections: state.sections.map((s) =>
            s.id === existing.id
              ? { ...s, items: [...s.items, ...sectionData.items], isStreaming: false }
              : s
          ),
        }
      }
      id = nextId()
      return {
        sections: [...state.sections, { ...sectionData, id, isStreaming: false }],
      }
    })
    return id
  },

  reset: () =>
    set({
      metaTitle: '',
      sections: [],
      sheetId: null,
      courseId: null,
      version: null,
      savedSnapshot: null,
      restoredFromDraft: false,
      generationParams: null,
      pendingVersion: null,
      selecting: false,
      selectedIds: [],
      regeneratingIds: [],
      status: 'idle',
      error: null,
    }),

  // ── 用户编辑 ──────────────────────────────────────────────────────────────
  updateSection: (id, patch) =>
    set((state) => ({
      sections: state.sections.map((s) =>
        s.id === id ? { ...s, ...patch } : s
      ),
    })),

  updateItem: (sectionId, itemIndex, patch) =>
    set((state) => ({
      sections: state.sections.map((s) => {
        if (s.id !== sectionId) return s
        const newItems = s.items.map((item, idx) =>
          idx === itemIndex ? { ...item, ...patch } : item
        )
        return { ...s, items: newItems }
      }),
    })),

  deleteSection: (id) =>
    set((state) => ({
      sections: state.sections.filter((s) => s.id !== id),
      selectedIds: state.selectedIds.filter((x) => x !== id),
    })),

  reorderSections: (fromIndex, toIndex) =>
    set((state) => {
      const next = [...state.sections]
      const [moved] = next.splice(fromIndex, 1)
      next.splice(toIndex, 0, moved)
      return { sections: next }
    }),
}))
