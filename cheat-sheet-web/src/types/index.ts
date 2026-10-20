// ─────────────────────────────────────────────────────────────────────────────
// 与后端 Pydantic schema 一一对应（backend/app/schemas/cheat_sheet.py）
// 如后端枚举/字段发生变更，同步修改此文件。
// ─────────────────────────────────────────────────────────────────────────────

// ── Enums ──────────────────────────────────────────────────────────────────

export type ContentType = 'text' | 'equation' | 'definition'

export type PageLimit = '1_side' | '1_page' | '2_pages' | 'unlimited'

export type AcademicLevel = 'high_school' | 'undergraduate' | 'graduate'

export type ExamType = 'quiz' | 'midterm' | 'final'

export type CourseArchetype =
  | 'stem_computational'
  | 'stem_theoretical'
  | 'coding'
  | 'humanities'
  | 'general'

// ── Backend data shapes ────────────────────────────────────────────────────

/** 单条内容项（text / equation / definition） */
export interface ContentItem {
  type: ContentType
  content: string
}

/** 一个章节（对应 outline 里的一个 topic） */
export interface Section {
  title: string
  items: ContentItem[]
}

/** 完整小抄（后端 CheatSheetSchema） */
export interface CheatSheet {
  title: string
  sections: Section[]
}

/** 大纲中的单个 topic */
export interface TopicNode {
  title: string
  relevance_score: number
}

/** 用户选定的 topic（发给后端） */
export interface TopicInput {
  title: string
  relevance_score: number
}

// ── API request shapes ─────────────────────────────────────────────────────

export interface GenerateOutlineRequest {
  raw_text: string
  user_context?: string
  exam_type?: ExamType
  ingest_batch_id?: string
}

export interface GenerateSheetRequest {
  syllabus?: string
  raw_text?: string
  user_context?: string
  page_limit?: PageLimit
  academic_level?: AcademicLevel
  selected_topics?: TopicInput[]
  archetype?: CourseArchetype
  exam_type?: ExamType
}

// ── SSE event shapes（流式端点推送的 NDJSON 行） ───────────────────────────

/** Line 1 推送的 meta 事件（包含小抄标题） */
export interface StreamMetaEvent {
  _type: 'meta'
  title: string
}

/** Line 2+ 推送的 section 事件（一行 = 一个完整 section） */
export type StreamSectionEvent = Section   // { title, items }

/** 前端 UI 使用的 section（含 id 用于 React key 和 DnD） */
export interface UISection extends Section {
  /** 前端生成的唯一 ID，用于 React key / DnD / Zustand 更新 */
  id: string
  /** true = 该 section 正在流式接收中 */
  isStreaming: boolean
}

// ── 小抄持久化（/api/cheat-sheets，Supabase） ─────────────────────────────

/** POST / PUT 请求体：只含 {title, items}，不含前端 id / isStreaming */
export interface CheatSheetSaveRequest {
  title: string
  sections: Section[]
}

/** 后端 CheatSheetRecord */
export interface CheatSheetRecord {
  id: string
  title: string
  sections: Section[]
  created_at: string
  updated_at: string
}

// ── Outline ────────────────────────────────────────────────────────────────

export interface OutlineTaskResult {
  topics: TopicNode[]
  degraded_reason?: string
}
