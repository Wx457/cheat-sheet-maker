'use client'

import { create } from 'zustand'
import type { UISection, ContentItem } from '@/types'

// ─────────────────────────────────────────────────────────────────────────────
// State shape
// ─────────────────────────────────────────────────────────────────────────────

export type StreamStatus =
  | 'idle'
  | 'connecting'     // SSE 连接中
  | 'streaming'      // 卡片流式渲染中
  | 'complete'
  | 'error'

interface CheatSheetState {
  // ── 小抄数据 ────────────────────────────────────────────────────────────
  metaTitle: string           // 后端推送的 {"_type":"meta","title":"..."} 标题
  sections: UISection[]       // 所有 section（含前端 id 和 isStreaming 标志）

  // ── 流式状态 ────────────────────────────────────────────────────────────
  status: StreamStatus
  error: string | null

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
  status: 'idle',
  error: null,

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
    })),

  reorderSections: (fromIndex, toIndex) =>
    set((state) => {
      const next = [...state.sections]
      const [moved] = next.splice(fromIndex, 1)
      next.splice(toIndex, 0, moved)
      return { sections: next }
    }),
}))
