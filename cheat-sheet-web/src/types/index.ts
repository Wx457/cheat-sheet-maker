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
  /** 第 8 点：只检索该课程的知识库；不传 → 默认课程 */
  course_id?: string
}

/**
 * 一个版本的 generation_params：生成它所用的请求参数。
 * 8-2 重新生成出的版本额外记下重写了哪些 section、用了什么指令（发请求时去掉）
 */
export interface GenerationParams extends GenerateSheetRequest {
  regeneration?: {
    /** 被重写的 section 在父版本中的下标 */
    sections: number[]
    instruction?: string
  }
}

/** POST /api/generate/regenerate（8-2 部分重新生成，SSE） */
export interface RegenerateSectionsRequest {
  title: string
  /** 当前内容（可含尚未保存的编辑） */
  sections: Section[]
  /** 要重写的 section 下标（按 sections 顺序） */
  selected_indices: number[]
  /** 自定义指令，最多 500 字符 */
  instruction?: string
  params: GenerateSheetRequest
}

// ── SSE event shapes（流式端点推送的 NDJSON 行） ───────────────────────────

/** Line 1 推送的 meta 事件（包含小抄标题） */
export interface StreamMetaEvent {
  _type: 'meta'
  title: string
}

/** Line 2+ 推送的 section 事件（一行 = 一个完整 section） */
export type StreamSectionEvent = Section   // { title, items }

/** 重新生成端点推送的 section：_index = 它要替换的位置（请求里 sections 的下标） */
export interface StreamRegeneratedSectionEvent extends Section {
  _index: number
}

/** 前端 UI 使用的 section（含 id 用于 React key 和 DnD） */
export interface UISection extends Section {
  /** 前端生成的唯一 ID，用于 React key / DnD / Zustand 更新 */
  id: string
  /** true = 该 section 正在流式接收中 */
  isStreaming: boolean
}

// ── 小抄持久化（/api/cheat-sheets，Supabase） ─────────────────────────────

/** PUT 请求体（手动编辑当前版本）：只含 {title, items}，不含前端 id / isStreaming */
export interface CheatSheetSaveRequest {
  title: string
  sections: Section[]
}

export type SheetOrigin = 'generate' | 'regenerate'

/** POST 请求体：一次生成 = 课程内一个新版本（第 8 点） */
export interface CheatSheetCreateRequest extends CheatSheetSaveRequest {
  /** 不传 → 默认课程「Uncategorized」 */
  course_id?: string
  /** 生成这一版所用的请求参数（8-2 重新生成复用） */
  generation_params?: GenerationParams
  origin?: SheetOrigin
  parent_sheet_id?: string
}

/** 后端 CheatSheetRecord */
export interface CheatSheetRecord {
  id: string
  title: string
  sections: Section[]
  course_id: string | null
  version: number
  origin: SheetOrigin
  parent_sheet_id: string | null
  generation_params: GenerationParams | null
  created_at: string
  updated_at: string
}

// ── 课程（/api/courses，第 8 点 · 8-1） ────────────────────────────────────

export interface Course {
  id: string
  name: string
  archetype: CourseArchetype | null
  academic_level: AcademicLevel | null
  /** 每个用户一门「Uncategorized」：未指定课程时的兜底 */
  is_default: boolean
  sheet_count: number
  created_at: string
  updated_at: string
}

export interface CheatSheetSummary {
  id: string
  title: string
  version: number
  origin: SheetOrigin
  parent_sheet_id: string | null
  created_at: string
  updated_at: string
}

export interface CourseDetail {
  course: Course
  /** 按创建时间倒序 */
  sheets: CheatSheetSummary[]
}

export interface CourseUpdateRequest {
  name?: string
  archetype?: CourseArchetype
  academic_level?: AcademicLevel
}

// ── Outline ────────────────────────────────────────────────────────────────

export interface OutlineTaskResult {
  topics: TopicNode[]
  degraded_reason?: string
}
