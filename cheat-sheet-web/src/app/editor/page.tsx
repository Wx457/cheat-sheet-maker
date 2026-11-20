'use client'

/**
 * Editor Page — 主编辑器页面（Webapp 只负责渲染最后一步编辑）
 *
 * 数据流：
 *   Chrome Extension（插件）
 *     → POST /api/rag/ingest（同步，知识库建好才返回）
 *     → POST /api/outline → 用户在插件内勾选 topics
 *     → chrome.tabs.create({ url: '/editor?topics=[...]&...' })
 *
 *   Webapp（本页）
 *     → ① 读取 URL 参数；身份来自 Clerk session（proxy.ts 保护 /editor，与插件共享同一 Clerk 用户）
 *     → ③ URL 无 sheetId：自动触发 POST /api/generate/stream（SSE）
 *        URL 有 sheetId：GET /api/cheat-sheets/{id} 恢复，不重新生成（3-4-c）
 *     → ④ 生成完成后自动保存（POST）为 courseId 课程内的新版本，把 sheetId 写回 URL（replaceState）
 *     → ⑤ 用户拖拽 / 编辑 → 防抖 PUT（修改当前版本，不新建版本）；导出 PDF（SheetCanvas 分页画布）
 *     → ⑥ 生成中 / 有未保存修改时刷新：beforeunload 警告（6-4）
 *
 * 页面状态机：
 *   idle → connecting → streaming → complete
 *     │       (SSE)                     ↑
 *     └──→ loading（按 sheetId 恢复）───┘
 *                                   error（任意阶段可跳入）
 *
 * ⚠️  useSearchParams() 必须在 <Suspense> 内使用（Next.js App Router 要求）
 */

import { Suspense, useEffect, useRef, useCallback, useMemo, useState } from 'react'
import Link from 'next/link'
import { useSearchParams, useRouter } from 'next/navigation'
import { UserButton, useAuth } from '@clerk/nextjs'
import { useCheatSheetStore } from '@/stores/cheatSheetStore'
import { startRegenerateStreaming, startStreaming } from '@/lib/streaming'
import {
  ApiError,
  createCheatSheet,
  getCourse,
  loadCheatSheet,
  updateCheatSheet,
} from '@/lib/api'
import { clearDraft, draftMatches, draftScopeFromSearch, readDraft, writeDraft } from '@/lib/draftStorage'
import SheetCanvas from '@/components/SheetCanvas'
import StreamingStatus from '@/components/StreamingStatus'
import type {
  GenerateSheetRequest,
  AcademicLevel,
  PageLimit,
  CourseArchetype,
  ExamType,
  TopicInput,
  UISection,
  CheatSheetSaveRequest,
  CourseDetail,
  GenerationParams,
  Section,
} from '@/types'

// ─────────────────────────────────────────────────────────────────────────────
// 持久化工具（3-4-c）
// ─────────────────────────────────────────────────────────────────────────────

/** 编辑停止多久后自动保存 */
const AUTOSAVE_DELAY_MS = 1000

/** 去掉前端运行时字段（id / isStreaming） */
function toSaveRequest(title: string, sections: UISection[]): CheatSheetSaveRequest {
  return { title, sections: sections.map(({ title, items }) => ({ title, items })) }
}

/** 8-2：自定义指令长度上限（与后端 RegenerateSectionsRequest.instruction 一致） */
const INSTRUCTION_MAX = 500

/** 版本的 generation_params → 可以直接发给生成端点的请求参数（去掉 8-2 的重写记录） */
function toRequestParams(params: GenerationParams | null): GenerateSheetRequest | null {
  if (!params) return null
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { regeneration, ...rest } = params
  return rest
}

/**
 * 只改 URL 中的 sheetId，保留插件传入的其他参数。
 * 用原生 replaceState：与 useSearchParams 同步，但不触发路由导航 / 页面重渲染。
 */
function replaceSheetIdInUrl(id: string | null) {
  const params = new URLSearchParams(window.location.search)
  if (id) params.set('sheetId', id)
  else params.delete('sheetId')
  window.history.replaceState(null, '', `${window.location.pathname}?${params.toString()}`)
}

/**
 * 第 8 点：顶栏的「课程名 · v3」+ 同课程版本切换。
 * 课程 id 来自已保存 / 已加载的记录，首次保存前用插件传入的 courseId。
 * reloadKey 变化（首次保存拿到版本号）时重新拉取版本列表。
 */
function CourseVersionBadge({ courseId, sheetId, version, reloadKey }: {
  courseId: string | null
  sheetId: string | null
  version: number | null
  reloadKey: string
}) {
  const { getToken } = useAuth()
  const [loaded, setLoaded] = useState<{ key: string; detail: CourseDetail } | null>(null)
  const requestKey = courseId ? `${courseId}|${reloadKey}` : null

  useEffect(() => {
    if (!courseId || !requestKey) return
    const controller = new AbortController()
    getCourse(courseId, getToken, controller.signal)
      .then((detail) => setLoaded({ key: requestKey, detail }))
      .catch(() => { /* 只是导航信息，失败时不显示 */ })
    return () => controller.abort()
  }, [courseId, requestKey, getToken])

  const detail = loaded && loaded.key === requestKey ? loaded.detail : null
  if (!courseId || !detail) return null
  const currentVersion = version ?? detail.sheets.find((s) => s.id === sheetId)?.version ?? null

  return (
    <span className="flex items-center gap-1.5 shrink-0 text-xs text-zinc-500 dark:text-zinc-400">
      <Link href={`/courses?id=${encodeURIComponent(courseId)}`}
        className="max-w-[12rem] truncate hover:text-zinc-900 dark:hover:text-zinc-100 hover:underline"
        title="All versions of this course">
        {detail.course.name}
      </Link>
      {detail.sheets.length > 1 && sheetId ? (
        <select
          aria-label="Switch version"
          value={sheetId}
          onChange={(e) => {
            // 整页跳转而不是 router.push：编辑器的启动逻辑（恢复 / 生成）只在首次挂载时运行，
            // 也不能按 sheetId 做 key 重挂载——首次保存会 replaceState 写入 sheetId，会把刚生成的内容重载一遍
            // eslint-disable-next-line @next/next/no-location-assign-relative-destination
            window.location.assign(`/editor?sheetId=${encodeURIComponent(e.target.value)}`)
          }}
          className="rounded border border-zinc-200 dark:border-zinc-700 bg-transparent px-1 py-0.5 text-xs">
          {detail.sheets.map((s) => (
            <option key={s.id} value={s.id}>v{s.version}</option>
          ))}
        </select>
      ) : currentVersion !== null ? (
        <span>· v{currentVersion}</span>
      ) : null}
    </span>
  )
}

function SaveIndicator({ saving, saveError, isDirty, everSaved }: {
  saving: boolean
  saveError: string | null
  isDirty: boolean
  everSaved: boolean
}) {
  if (saveError) {
    return <span className="text-xs text-red-500 shrink-0" title={saveError}>Not saved</span>
  }
  if (saving || isDirty) {
    return <span className="text-xs text-zinc-400 shrink-0">Saving…</span>
  }
  if (everSaved) {
    return <span className="text-xs text-zinc-400 shrink-0">Saved</span>
  }
  return null
}

/**
 * 8-2：选择模式下顶栏下方的面板 —— 已选数量、全选 / 清空、自定义指令、提交 / 取消。
 * 选择本身在画布上点 section 完成（SheetCanvas 的 sheet-selectable）。
 */
function RegeneratePanel({ selectedCount, totalCount, instruction, onInstructionChange, onSelectAll, onClear, onSubmit, onCancel }: {
  selectedCount: number
  totalCount: number
  instruction: string
  onInstructionChange: (value: string) => void
  onSelectAll: () => void
  onClear: () => void
  onSubmit: () => void
  onCancel: () => void
}) {
  const allSelected = totalCount > 0 && selectedCount === totalCount
  const linkCls = 'text-blue-600 dark:text-blue-400 hover:underline disabled:opacity-40 disabled:no-underline disabled:cursor-not-allowed'
  return (
    <div className="border-t border-zinc-200 dark:border-zinc-800 bg-blue-50/80 dark:bg-blue-950/30 px-5 py-3">
      <div className="mx-auto flex max-w-4xl flex-col gap-2 sm:flex-row sm:items-start">
        <div className="flex shrink-0 flex-col gap-1 text-xs text-zinc-600 dark:text-zinc-300 sm:w-56">
          <span className="font-medium text-zinc-900 dark:text-zinc-50">
            Click sections to regenerate
          </span>
          <span>
            {selectedCount} of {totalCount} selected
            {' · '}
            <button type="button" onClick={onSelectAll} disabled={allSelected} className={linkCls}>Select all</button>
            {' · '}
            <button type="button" onClick={onClear} disabled={selectedCount === 0} className={linkCls}>Clear</button>
          </span>
          <span className="text-zinc-400">The rest stays as is. The result is saved as a new version.</span>
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <textarea
            value={instruction}
            onChange={(e) => onInstructionChange(e.target.value)}
            maxLength={INSTRUCTION_MAX}
            rows={2}
            placeholder="Optional instruction, e.g. “more worked examples”, “show full proof steps”"
            aria-label="Instruction for the regenerated sections"
            className="w-full resize-none rounded-md border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-900 px-2 py-1.5 text-xs text-zinc-800 dark:text-zinc-100 outline-none focus:ring-1 focus:ring-blue-400"
          />
          <span className="text-right text-[10px] text-zinc-400">{instruction.length} / {INSTRUCTION_MAX}</span>
        </div>
        <div className="flex shrink-0 gap-2 sm:flex-col">
          <button type="button" onClick={onSubmit} disabled={selectedCount === 0}
            className="flex items-center justify-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-40 transition-colors">
            <SparkleIcon />
            Regenerate{selectedCount > 0 ? ` ${selectedCount}` : ''}
          </button>
          <button type="button" onClick={onCancel}
            className="rounded-lg border border-zinc-300 dark:border-zinc-600 px-3 py-1.5 text-xs text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors">
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Icons
// ─────────────────────────────────────────────────────────────────────────────

function SparkleIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
      <path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z" />
    </svg>
  )
}

function DownloadIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  )
}

function RefreshIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10" />
      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
    </svg>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Dev Mode 模拟插件启动（仅 development 可见）
// 填参数 → "模拟插件启动" → router.push 携带 URL params → useEffect 自动触发
// ─────────────────────────────────────────────────────────────────────────────

function DevSimulatorPanel() {
  const router = useRouter()

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    const params = new URLSearchParams()

    params.set('launch', 'dev')

    const context = (fd.get('context') as string).trim()
    if (context) params.set('context', context)

    const level = fd.get('level') as string
    if (level) params.set('level', level)

    const pageLimit = fd.get('pageLimit') as string
    if (pageLimit) params.set('pageLimit', pageLimit)

    const archetype = fd.get('archetype') as string
    if (archetype) params.set('archetype', archetype)

    const examType = fd.get('examType') as string
    if (examType) params.set('examType', examType)

    router.push(`/editor?${params.toString()}`)
  }

  const selectCls =
    'w-full rounded border border-zinc-200 bg-white text-xs text-zinc-700 ' +
    'px-2 py-1.5 outline-none focus:ring-1 focus:ring-blue-400'

  return (
    <details className="mt-8 w-full max-w-sm rounded-xl border border-dashed border-amber-300 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-700">
      <summary className="cursor-pointer select-none px-4 py-3 text-xs font-semibold text-amber-700 dark:text-amber-400">
        🛠 Dev Mode — Simulate Plugin Launch
      </summary>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3 px-4 pb-4 pt-2">
        <div className="flex flex-col gap-1">
          <label className="text-[10px] text-zinc-500 font-medium">Context / Focus (optional)</label>
          <input name="context" placeholder="e.g. Focus on formulas" className={selectCls} />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-zinc-500 font-medium">Level</label>
            <select name="level" defaultValue="undergraduate" className={selectCls}>
              <option value="high_school">High School</option>
              <option value="undergraduate">Undergraduate</option>
              <option value="graduate">Graduate</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-zinc-500 font-medium">Page Limit</label>
            <select name="pageLimit" defaultValue="1_page" className={selectCls}>
              <option value="1_side">1 Side</option>
              <option value="1_page">1 Page</option>
              <option value="2_pages">2 Pages</option>
              <option value="unlimited">Unlimited</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-zinc-500 font-medium">Course Type</label>
            <select name="archetype" defaultValue="general" className={selectCls}>
              <option value="stem_computational">STEM Computational</option>
              <option value="stem_theoretical">STEM Theoretical</option>
              <option value="coding">Coding / CS</option>
              <option value="general">General</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-zinc-500 font-medium">Exam Type</label>
            <select name="examType" defaultValue="" className={selectCls}>
              <option value="">— None —</option>
              <option value="quiz">Quiz</option>
              <option value="midterm">Midterm</option>
              <option value="final">Final Exam</option>
            </select>
          </div>
        </div>
        <button type="submit"
          className="mt-1 w-full py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-white text-xs font-semibold transition-colors">
          Simulate Plugin Launch →
        </button>
      </form>
    </details>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 等待插件界面（URL 无启动参数时）
// ─────────────────────────────────────────────────────────────────────────────

function WaitingForPlugin() {
  const isDev = process.env.NODE_ENV === 'development'
  return (
    <div className="flex flex-col items-center justify-center min-h-screen gap-4 text-center px-6">
      <div className="w-16 h-16 rounded-2xl bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center text-3xl select-none">
        📄
      </div>
      <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
        Waiting for the Extension
      </h1>
      <p className="max-w-xs text-sm text-zinc-500 dark:text-zinc-400 leading-relaxed">
        Open the <strong>Cheat Sheet Maker</strong> Chrome Extension, scan a page,
        and it will automatically launch this editor with your content.
      </p>
      <p className="text-xs text-zinc-400 dark:text-zinc-600">
        This page is meant to be opened by the extension, not directly.
      </p>
      <Link href="/courses"
        className="text-sm font-medium text-zinc-700 dark:text-zinc-300 underline underline-offset-4 hover:text-zinc-900 dark:hover:text-zinc-100">
        Browse your saved cheat sheets →
      </Link>
      {isDev && <DevSimulatorPanel />}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// EditorContent — 有插件参数时渲染（需要 Suspense 包裹）
// ─────────────────────────────────────────────────────────────────────────────

function EditorContent() {
  const searchParams = useSearchParams()

  // ── 从 URL 读取插件传入的参数 ───────────────────────────────────────────────
  const context   = searchParams.get('context') ?? undefined
  const level     = (searchParams.get('level')     as AcademicLevel)   ?? 'undergraduate'
  const pageLimit = (searchParams.get('pageLimit') as PageLimit)       ?? '1_page'
  const archetype = (searchParams.get('archetype') as CourseArchetype) ?? 'general'
  const examType  = (searchParams.get('examType')  as ExamType | null) ?? undefined

  // 依赖用字符串而非 searchParams 对象：URL 其他参数变化时不重新解析，
  // selectedTopics 引用保持稳定，避免 runStreaming 被无谓重建
  const topicsParam = searchParams.get('topics')
  const selectedTopics = useMemo<TopicInput[] | undefined>(() => {
    if (!topicsParam) return undefined
    try {
      const titles: string[] = JSON.parse(topicsParam)
      return titles.map((title) => ({ title, relevance_score: 1 }))
    } catch { return undefined }
  }, [topicsParam])

  const sheetIdParam    = searchParams.get('sheetId')   // 3-4-c：已保存的小抄 id
  const courseIdParam   = searchParams.get('courseId') ?? undefined   // 第 8 点：插件选中的课程
  // 插件打开时带 topics；刷新恢复带 sheetId；Dev 模拟面板带 launch
  const hasPluginParams = !!(topicsParam || sheetIdParam || searchParams.get('launch'))
  // 6-6：本标签页草稿的归属（插件参数，不含 sheetId）
  const searchString = searchParams.toString()
  const draftScope   = useMemo(() => draftScopeFromSearch(searchString), [searchString])

  // ── Clerk（Phase 2）：后端请求用 session token 鉴权 ──────────────────────────
  const { isLoaded: authLoaded, getToken, userId } = useAuth()

  // ── Zustand store ──────────────────────────────────────────────────────────
  const status              = useCheatSheetStore((s) => s.status)
  const error               = useCheatSheetStore((s) => s.error)
  const metaTitle           = useCheatSheetStore((s) => s.metaTitle)
  const sections            = useCheatSheetStore((s) => s.sections)
  const reset               = useCheatSheetStore((s) => s.reset)
  const setStatus           = useCheatSheetStore((s) => s.setStatus)
  const setError            = useCheatSheetStore((s) => s.setError)
  const setMetaTitle        = useCheatSheetStore((s) => s.setMetaTitle)
  const mergeOrAddSection   = useCheatSheetStore((s) => s.mergeOrAddSection)
  const setSavedRecord      = useCheatSheetStore((s) => s.setSavedRecord)
  const loadSheet           = useCheatSheetStore((s) => s.loadSheet)
  const savedSnapshot       = useCheatSheetStore((s) => s.savedSnapshot)
  const markSaved           = useCheatSheetStore((s) => s.markSaved)
  const restoreDraft        = useCheatSheetStore((s) => s.restoreDraft)
  const sheetId             = useCheatSheetStore((s) => s.sheetId)
  const sheetCourseId       = useCheatSheetStore((s) => s.courseId)
  const sheetVersion        = useCheatSheetStore((s) => s.version)
  const restoredFromDraft   = useCheatSheetStore((s) => s.restoredFromDraft)
  const generationParams    = useCheatSheetStore((s) => s.generationParams)
  const setGenerationParams = useCheatSheetStore((s) => s.setGenerationParams)
  // 8-2 部分重新生成
  const selecting           = useCheatSheetStore((s) => s.selecting)
  const selectedCount       = useCheatSheetStore((s) => s.selectedIds.length)
  const setSelecting        = useCheatSheetStore((s) => s.setSelecting)
  const selectAll           = useCheatSheetStore((s) => s.selectAll)
  const clearSelection      = useCheatSheetStore((s) => s.clearSelection)
  const startRegenerate     = useCheatSheetStore((s) => s.startRegenerate)
  const applyRegenerated    = useCheatSheetStore((s) => s.applyRegeneratedSection)
  const endRegenerate       = useCheatSheetStore((s) => s.endRegenerate)
  const markAsNewVersion    = useCheatSheetStore((s) => s.markAsNewVersion)

  // ── 持久化状态（3-4-c） ────────────────────────────────────────────────────
  const [saving, setSaving]               = useState(false)
  const [saveError, setSaveError]         = useState<string | null>(null)

  // ── 8-2 部分重新生成 ───────────────────────────────────────────────────────
  const [instruction, setInstruction]     = useState('')
  // 不阻断编辑的提示：失败 / 取消 / 部分 section 没拿到（与整份生成的 error 状态分开，不触发 Retry）
  const [regenNotice, setRegenNotice]     = useState<{ kind: 'error' | 'info'; text: string } | null>(null)
  const regenAbortRef    = useRef<AbortController | null>(null)
  // 被重写 section 的原内容：取消 / 失败时恢复
  const regenOriginalRef = useRef<Map<string, Section> | null>(null)

  // ── Refs ───────────────────────────────────────────────────────────────────
  const abortRef   = useRef<AbortController | null>(null)
  const startedRef = useRef(false)   // 防止 StrictMode / URL 变化重复触发
  // 保存请求串行执行：避免并发 POST 建出两份小抄、或旧 PUT 覆盖新 PUT
  const saveChainRef = useRef<Promise<void>>(Promise.resolve())
  // 每次重新生成 +1：丢弃上一份小抄仍在路上的保存结果
  const epochRef = useRef(0)
  // 恢复失败原因：not_found 时 Retry 改为重新生成，其余错误 Retry 重新加载
  const loadFailureRef = useRef<'not_found' | 'other' | null>(null)

  // ── 派生状态 ───────────────────────────────────────────────────────────────
  const isGenerating   = status === 'connecting' || status === 'streaming'
  const isRegenerating = status === 'regenerating'
  const canExport      = sections.length > 0 && !isRegenerating
  // 加载的版本按它自己的 page_limit 排版（从课程页打开时 URL 只有 sheetId）
  const effectivePageLimit = generationParams?.page_limit ?? pageLimit
  // 生成完成后，内容与最近一次成功保存不同 → 需要保存（首次保存前 savedSnapshot 为 null）
  const isDirty =
    status === 'complete' &&
    sections.length > 0 &&
    (savedSnapshot === null ||
      savedSnapshot.sections !== sections ||
      savedSnapshot.title !== metaTitle)

  // 生成请求参数：既发给 SSE 端点，也随首次保存记为该版本的 generation_params（8-2 重新生成复用）
  const generationPayload = useMemo<GenerateSheetRequest>(() => ({
    user_context: context,
    academic_level: level,
    page_limit: pageLimit,
    archetype,
    exam_type: examType,
    selected_topics: selectedTopics,
    course_id: courseIdParam,
  }), [context, level, pageLimit, archetype, examType, selectedTopics, courseIdParam])

  // ── SSE 流式生成（被 auto-trigger / Retry 调用） ─────────────────────────────
  const runStreaming = useCallback(async (payload: GenerateSheetRequest) => {
    const controller = new AbortController()
    abortRef.current = controller
    setGenerationParams(payload)   // 首次保存时记为该版本的 generation_params
    setStatus('connecting')

    await startStreaming(
      payload,
      getToken,
      {
        onMeta: (e) => { setMetaTitle(e.title); setStatus('streaming') },
        onSection: (section) => {
          mergeOrAddSection(section)
        },
        onDone:  () => setStatus('complete'),
        onError: (err) => setError(err.message),
      },
      controller.signal,
    )
  }, [getToken, setGenerationParams, setStatus, setError, setMetaTitle, mergeOrAddSection])

  // ── 3-4-c：按 sheetId 恢复（刷新页面时不重新生成） ─────────────────────────
  const runLoad = useCallback(async (id: string) => {
    const controller = new AbortController()
    abortRef.current = controller
    loadFailureRef.current = null
    setStatus('loading')
    try {
      loadSheet(await loadCheatSheet(id, getToken, controller.signal))
    } catch (err) {
      if (controller.signal.aborted) return
      // 404：不存在或不属于该用户；422：sheetId 不是合法 UUID
      const notFound = err instanceof ApiError && (err.status === 404 || err.status === 422)
      loadFailureRef.current = notFound ? 'not_found' : 'other'
      setError(
        notFound
          ? 'This saved cheat sheet was not found. Click Retry to generate a new one.'
          : `Could not load the saved cheat sheet: ${err instanceof Error ? err.message : String(err)}`,
      )
    }
  }, [getToken, setStatus, setError, loadSheet])

  // ── 3-4-c：保存（首次 POST = 课程内新版本，并把 id 写回 URL；之后 PUT 修改当前版本） ──
  // 8-2：重新生成出的版本同样首次 POST（origin = regenerate，parent_sheet_id = 父版本）
  const persist = useCallback(() => {
    const epoch = epochRef.current
    saveChainRef.current = saveChainRef.current.then(async () => {
      if (epoch !== epochRef.current) return
      // 执行时再读 store：拿到最新内容和（可能刚由上一个 POST 写入的）sheetId
      const state = useCheatSheetStore.getState()
      // 重新生成进行中不保存：此时内容一半新一半旧
      if (state.status !== 'complete') return
      const { metaTitle: title, sections: current, sheetId, pendingVersion } = state
      const body = toSaveRequest(title, current)
      setSaving(true)
      try {
        const record = sheetId
          ? await updateCheatSheet(sheetId, body, getToken)
          : await createCheatSheet({
              ...body,
              course_id: state.courseId ?? courseIdParam,
              generation_params: state.generationParams ?? generationPayload,
              origin: pendingVersion?.origin ?? 'generate',
              parent_sheet_id: pendingVersion?.parentSheetId,
            }, getToken)
        if (epoch !== epochRef.current) return
        if (!sheetId) {
          setSavedRecord(record)
          replaceSheetIdInUrl(record.id)
        }
        markSaved({ title, sections: current })
        setSaveError(null)
      } catch (err) {
        if (epoch === epochRef.current) {
          setSaveError(err instanceof Error ? err.message : String(err))
        }
      } finally {
        setSaving(false)
      }
    })
  }, [getToken, setSavedRecord, markSaved, courseIdParam, generationPayload])

  // 内容变化后防抖保存（生成完成时 isDirty 变为 true，也由此触发首次保存）
  useEffect(() => {
    if (!isDirty) return
    const timer = setTimeout(persist, AUTOSAVE_DELAY_MS)
    return () => clearTimeout(timer)
  }, [isDirty, sections, metaTitle, persist])

  // ── 6-6：未保存的修改同步写进本标签页草稿；保存成功后删除 ──────────────────────
  useEffect(() => {
    if (!userId || status !== 'complete') return
    if (isDirty) {
      const { pendingVersion, generationParams: params, courseId } = useCheatSheetStore.getState()
      writeDraft({
        scope: draftScope,
        userId,
        sheetId,
        title: metaTitle,
        sections: sections.map(({ title, items }) => ({ title, items })),
        savedAt: Date.now(),
        // 8-2：尚未保存的重新生成版本，刷新后要能继续保存成新版本
        ...(pendingVersion && !sheetId
          ? { pending: { version: pendingVersion, generationParams: params, courseId } }
          : {}),
      })
    } else if (savedSnapshot !== null) {
      clearDraft()
    }
  }, [isDirty, status, sections, metaTitle, sheetId, savedSnapshot, draftScope, userId])

  // ── 自动触发（有插件参数时） ────────────────────────────────────────────────
  useEffect(() => {
    if (!hasPluginParams) return
    if (!authLoaded) return   // getToken 在 Clerk 加载完成前拿不到 token
    if (startedRef.current) return
    if (status !== 'idle') return

    startedRef.current = true
    reset()

    // 6-6：本标签页有对得上的未保存草稿 → 直接恢复，不再生成 / 加载；自动保存会继续重试
    const draft = userId ? readDraft() : null
    if (draft && userId && draftMatches(draft, draftScope, sheetIdParam, userId)) {
      restoreDraft(draft)
      return
    }

    if (sheetIdParam) runLoad(sheetIdParam)
    else runStreaming(generationPayload)

    return () => {
      abortRef.current?.abort()
      startedRef.current = false
      // 只在 streaming/complete 之前 reset：保护已渲染的数据不被 HMR/Suspense remount 清掉
      const currentStatus = useCheatSheetStore.getState().status
      if (currentStatus !== 'streaming' && currentStatus !== 'complete') {
        useCheatSheetStore.getState().reset()
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasPluginParams, authLoaded])

  // ── 6-4：刷新警告（生成中，或有尚未保存的修改时拦截） ─────────────────────────
  const warnOnUnload = isGenerating || isRegenerating || isDirty || saving
  useEffect(() => {
    if (!warnOnUnload) return
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault() }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [warnOnUnload])

  // ── 操作处理 ───────────────────────────────────────────────────────────────
  /** 开始新一轮生成：丢弃旧小抄的保存状态，并从 URL 去掉旧 sheetId */
  const startFreshGeneration = () => {
    // 已知当前版本的参数（从课程页打开的旧版本）就沿用它，否则用插件传入的 URL 参数
    const payload = toRequestParams(useCheatSheetStore.getState().generationParams) ?? generationPayload
    epochRef.current += 1
    loadFailureRef.current = null
    setSaveError(null)
    setRegenNotice(null)
    clearDraft()   // 6-6：旧小抄的草稿不再适用
    reset()   // 同时清空 sheetId / savedSnapshot
    replaceSheetIdInUrl(null)
    runStreaming(payload)
  }

  // ── 8-2：部分重新生成 ──────────────────────────────────────────────────────
  // 只在当前版本已保存、没有待保存的编辑时可用：新版本要以「已保存的当前版本」为父版本
  const canRegenerate = status === 'complete' && sections.length > 0 && !!sheetId && !isDirty && !saving
  const regenerateHint = !sheetId || isDirty || saving
    ? 'Available once this version is saved'
    : 'Rewrite selected sections — saved as a new version'

  const handleRegenerate = async () => {
    const state = useCheatSheetStore.getState()
    const parentSheetId = state.sheetId
    if (!parentSheetId || state.status !== 'complete') return

    // 按画布顺序排列被选中的 section
    const indices = state.sections
      .map((s, i) => (state.selectedIds.includes(s.id) ? i : -1))
      .filter((i) => i >= 0)
    if (indices.length === 0) return
    const ids = indices.map((i) => state.sections[i].id)
    const idByIndex = new Map(indices.map((i, k) => [i, ids[k]]))
    regenOriginalRef.current = new Map(
      indices.map((i) => [state.sections[i].id, { title: state.sections[i].title, items: state.sections[i].items }]),
    )

    const base = toRequestParams(state.generationParams) ?? generationPayload
    const params: GenerateSheetRequest = { ...base, course_id: state.courseId ?? base.course_id }
    const trimmed = instruction.trim()

    const controller = new AbortController()
    regenAbortRef.current = controller
    setRegenNotice(null)
    startRegenerate(ids)

    let received = 0
    await startRegenerateStreaming(
      {
        title: state.metaTitle,
        sections: toSaveRequest(state.metaTitle, state.sections).sections,
        selected_indices: indices,
        instruction: trimmed || undefined,
        params,
      },
      getToken,
      {
        onSection: (ev) => {
          const id = idByIndex.get(ev._index)
          if (!id) return
          applyRegenerated(id, { title: ev.title, items: ev.items })
          received += 1
        },
        onDone: () => {
          const original = regenOriginalRef.current
          regenOriginalRef.current = null
          regenAbortRef.current = null
          if (received === 0) {
            endRegenerate(original)
            setRegenNotice({ kind: 'error', text: 'The model returned no sections — nothing was changed. Please try again.' })
            return
          }
          const missing = useCheatSheetStore.getState().regeneratingIds.length
          endRegenerate(null)
          // 当前内容成为新版本：丢弃父版本仍在路上的保存，自动保存会 POST
          epochRef.current += 1
          setSaveError(null)
          markAsNewVersion(
            { origin: 'regenerate', parentSheetId },
            { ...params, regeneration: { sections: indices, ...(trimmed ? { instruction: trimmed } : {}) } },
          )
          if (missing > 0) {
            setRegenNotice({
              kind: 'info',
              text: `${missing} of ${indices.length} sections did not come back and were kept as they were.`,
            })
          }
        },
        onError: (err) => {
          endRegenerate(regenOriginalRef.current)
          regenOriginalRef.current = null
          regenAbortRef.current = null
          setRegenNotice({ kind: 'error', text: `Regeneration failed, nothing was changed: ${err.message}` })
        },
      },
      controller.signal,
    )
  }

  const handleCancelRegenerate = () => {
    regenAbortRef.current?.abort()
    regenAbortRef.current = null
    endRegenerate(regenOriginalRef.current)   // 已替换的也恢复：取消 = 什么都没发生
    regenOriginalRef.current = null
  }

  // 离开页面 / 卸载时中断重新生成请求
  useEffect(() => () => regenAbortRef.current?.abort(), [])

  const handleCancel = () => {
    abortRef.current?.abort()
    startedRef.current = false   // 允许重新触发（如果用户重新打开相同 URL）
    reset()
  }

  const handleRetry = () => {
    startedRef.current = true
    // 恢复失败（网络 / 服务端错误）→ 重新加载；其余情况（含 404）→ 重新生成
    if (sheetIdParam && loadFailureRef.current === 'other') {
      runLoad(sheetIdParam)
      return
    }
    startFreshGeneration()
  }

  const handleExportPDF = () => window.print()

  // ── 无插件参数：等待界面 ───────────────────────────────────────────────────
  if (!hasPluginParams) return <WaitingForPlugin />

  // ── 正常编辑器界面 ─────────────────────────────────────────────────────────
  return (
    <div className="print-block flex flex-col min-h-screen bg-zinc-200 dark:bg-zinc-950">

      {/* ══ HEADER ════════════════════════════════════════════════════════════ */}
      <header className="no-print sticky top-0 z-20 bg-white/90 dark:bg-zinc-900/90 backdrop-blur-sm border-b border-zinc-200 dark:border-zinc-800">
        <div className="flex items-center gap-3 px-5 py-3">

          <span className="font-semibold text-zinc-900 dark:text-zinc-50 shrink-0 select-none">
            📄 Cheat Sheet Maker
          </span>
          <span className="text-zinc-300 dark:text-zinc-700 select-none">|</span>

          <span className="flex-1 text-sm text-zinc-500 dark:text-zinc-400 truncate min-w-0">
            {metaTitle || (isGenerating ? '…' : 'Ready')}
          </span>

          <CourseVersionBadge
            courseId={sheetCourseId ?? courseIdParam ?? null}
            sheetId={sheetId}
            version={sheetVersion}
            reloadKey={`${sheetId ?? ''}|${sheetVersion ?? ''}`}
          />

          <StreamingStatus />

          {status === 'complete' && restoredFromDraft && (
            <span className="text-xs text-amber-600 dark:text-amber-400 shrink-0"
              title="Your last edits had not been saved before the page reloaded; they were restored from this tab and will be saved automatically.">
              Restored unsaved edits
            </span>
          )}

          {status === 'complete' && (
            <SaveIndicator
              saving={saving}
              saveError={saveError}
              isDirty={isDirty}
              everSaved={savedSnapshot !== null}
            />
          )}

          {/* Cancel：生成中可见 */}
          {isGenerating && (
            <button onClick={handleCancel}
              className="text-xs px-3 py-1.5 rounded-lg border border-zinc-300 dark:border-zinc-600 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors">
              Cancel
            </button>
          )}

          {/* 8-2 Regenerate…：进入选择模式；重新生成中变为 Cancel */}
          {isRegenerating ? (
            <button onClick={handleCancelRegenerate}
              title="Stop and keep the previous content"
              className="text-xs px-3 py-1.5 rounded-lg border border-zinc-300 dark:border-zinc-600 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors">
              Cancel
            </button>
          ) : status === 'complete' && sections.length > 0 && (
            <button
              onClick={() => { setRegenNotice(null); setSelecting(!selecting) }}
              disabled={!canRegenerate && !selecting}
              aria-pressed={selecting}
              title={regenerateHint}
              className={[
                'flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-colors disabled:opacity-40 disabled:cursor-not-allowed',
                selecting
                  ? 'border-blue-500 bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
                  : 'border-zinc-300 dark:border-zinc-600 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800',
              ].join(' ')}>
              <SparkleIcon />
              Regenerate…
            </button>
          )}

          {/* Retry：error 时可见 */}
          {status === 'error' && (
            <button onClick={handleRetry}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors">
              <RefreshIcon />
              Retry
            </button>
          )}

          {/* Export PDF */}
          <button onClick={handleExportPDF} disabled={!canExport}
            title={canExport
              ? 'Export as PDF — keep print scale at Default / 100%'
              : 'Generate a cheat sheet first'}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-zinc-900 dark:bg-zinc-50 text-white dark:text-zinc-900 font-medium disabled:opacity-40 disabled:cursor-not-allowed hover:bg-zinc-700 dark:hover:bg-zinc-200 transition-colors">
            <DownloadIcon />
            Export PDF
          </button>

          <UserButton />

        </div>

        {selecting && status === 'complete' && (
          <RegeneratePanel
            selectedCount={selectedCount}
            totalCount={sections.length}
            instruction={instruction}
            onInstructionChange={setInstruction}
            onSelectAll={selectAll}
            onClear={clearSelection}
            onSubmit={handleRegenerate}
            onCancel={() => setSelecting(false)}
          />
        )}
      </header>

      {/* ══ MAIN ══════════════════════════════════════════════════════════════ */}
      <main className="print-block flex-1">
        {/* 错误信息块 */}
        {status === 'error' && error && (
          <div className="no-print max-w-[210mm] mx-auto mt-6 rounded-lg border border-red-200 bg-red-50 dark:bg-red-950/30 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-400">
            <strong>Failed: </strong>{error}
          </div>
        )}

        {/* 8-2：重新生成的结果提示（不进入 error 状态，内容保持可编辑） */}
        {regenNotice && (
          <div className={[
            'no-print max-w-[210mm] mx-auto mt-6 flex items-start gap-3 rounded-lg border px-4 py-3 text-sm',
            regenNotice.kind === 'error'
              ? 'border-red-200 bg-red-50 text-red-700 dark:bg-red-950/30 dark:border-red-800 dark:text-red-400'
              : 'border-amber-200 bg-amber-50 text-amber-800 dark:bg-amber-950/30 dark:border-amber-800 dark:text-amber-300',
          ].join(' ')}>
            <span className="flex-1">{regenNotice.text}</span>
            <button onClick={() => setRegenNotice(null)} aria-label="Dismiss" className="shrink-0 opacity-60 hover:opacity-100">✕</button>
          </div>
        )}

        {/* 分页画布：小抄标题画在第 1 页；打印即屏幕所见（见 SheetCanvas / globals.css） */}
        <SheetCanvas title={metaTitle} pageLimit={effectivePageLimit} />
      </main>

    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Page export — <Suspense> 包裹（useSearchParams 要求）
// ─────────────────────────────────────────────────────────────────────────────

function LoadingFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="h-5 w-5 rounded-full border-2 border-zinc-300 border-t-zinc-600 animate-spin" />
    </div>
  )
}

export default function EditorPage() {
  return (
    <Suspense fallback={<LoadingFallback />}>
      <EditorContent />
    </Suspense>
  )
}
