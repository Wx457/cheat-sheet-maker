'use client'

/**
 * Editor Page — 主编辑器页面（Webapp 只负责渲染最后一步编辑）
 *
 * 数据流：
 *   Chrome Extension（插件）
 *     → POST /api/rag/ingest（同步，知识库建好才返回）
 *     → POST /api/outline → 用户在插件内勾选 topics
 *     → chrome.tabs.create({ url: '/editor?userId=x&topics=[...]&...' })
 *
 *   Webapp（本页）
 *     → ① 读取 URL 参数
 *     → ② 将 token 存入 sessionStorage（6-3：auth token 过渡方案）
 *     → ③ 自动触发 POST /api/generate/stream（SSE）
 *     → ④ 用户拖拽 / 编辑 / 导出 PDF
 *     → ⑤ 刷新时若正在生成：beforeunload 警告（6-4）
 *
 * 页面状态机：
 *   idle → connecting → streaming → complete
 *            (SSE)                     |
 *                                   error（任意阶段可跳入）
 *
 * ⚠️  useSearchParams() 必须在 <Suspense> 内使用（Next.js App Router 要求）
 */

import { Suspense, useEffect, useRef, useCallback, useMemo } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { useCheatSheetStore } from '@/stores/cheatSheetStore'
import { startStreaming } from '@/lib/streaming'
import { storeAuthToken } from '@/lib/api'
import CardList from '@/components/CardList'
import StreamingStatus from '@/components/StreamingStatus'
import type {
  GenerateSheetRequest,
  AcademicLevel,
  PageLimit,
  CourseArchetype,
  ExamType,
  TopicInput,
} from '@/types'

// ─────────────────────────────────────────────────────────────────────────────
// Icons
// ─────────────────────────────────────────────────────────────────────────────

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

    params.set('userId', (fd.get('userId') as string).trim() || 'dev-user')

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
          <label className="text-[10px] text-zinc-500 font-medium">User ID</label>
          <input name="userId" defaultValue="dev-user" className={selectCls} />
        </div>
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
              <option value="humanities">Humanities</option>
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
// 等待插件界面（URL 无 userId 参数时）
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
  const userId    = searchParams.get('userId')  ?? ''
  const token     = searchParams.get('token')   ?? null   // 6-3：auth JWT
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

  const hasPluginParams = !!searchParams.get('userId')

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

  // ── Refs ───────────────────────────────────────────────────────────────────
  const abortRef   = useRef<AbortController | null>(null)
  const startedRef = useRef(false)   // 防止 StrictMode / URL 变化重复触发

  // ── 派生状态 ───────────────────────────────────────────────────────────────
  const isGenerating = status === 'connecting' || status === 'streaming'
  const canExport    = sections.length > 0

  // ── 6-3：token 存入 sessionStorage ─────────────────────────────────────────
  useEffect(() => {
    if (token) storeAuthToken(token)
  }, [token])

  // ── SSE 流式生成（被 auto-trigger / Retry 调用） ─────────────────────────────
  const runStreaming = useCallback(async () => {
    const controller = new AbortController()
    abortRef.current = controller
    setStatus('connecting')

    const payload: GenerateSheetRequest = {
      user_context: context,
      academic_level: level,
      page_limit: pageLimit,
      archetype,
      exam_type: examType,
      selected_topics: selectedTopics,
    }

    await startStreaming(
      payload,
      userId,
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
  }, [
    userId, context, level, pageLimit, archetype, examType, selectedTopics,
    setStatus, setError, setMetaTitle, mergeOrAddSection,
  ])

  // ── 自动触发（有插件参数时） ────────────────────────────────────────────────
  useEffect(() => {
    if (!hasPluginParams) return
    if (startedRef.current) return
    if (status !== 'idle') return

    startedRef.current = true
    reset()
    runStreaming()

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
  }, [hasPluginParams])

  // ── 6-4：刷新警告（生成中时拦截） ────────────────────────────────────────────
  useEffect(() => {
    if (!isGenerating) return
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault() }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [isGenerating])

  // ── 操作处理 ───────────────────────────────────────────────────────────────
  const handleCancel = () => {
    abortRef.current?.abort()
    startedRef.current = false   // 允许重新触发（如果用户重新打开相同 URL）
    reset()
  }

  const handleRetry = () => {
    startedRef.current = false
    reset()
    runStreaming()
    startedRef.current = true
  }

  const handleExportPDF = () => window.print()

  // ── 无插件参数：等待界面 ───────────────────────────────────────────────────
  if (!hasPluginParams) return <WaitingForPlugin />

  // ── 正常编辑器界面 ─────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col min-h-screen bg-zinc-50 dark:bg-zinc-950">

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

          <StreamingStatus />

          {/* Cancel：生成中可见 */}
          {isGenerating && (
            <button onClick={handleCancel}
              className="text-xs px-3 py-1.5 rounded-lg border border-zinc-300 dark:border-zinc-600 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors">
              Cancel
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
            title={canExport ? 'Export as PDF' : 'Generate a cheat sheet first'}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-zinc-900 dark:bg-zinc-50 text-white dark:text-zinc-900 font-medium disabled:opacity-40 disabled:cursor-not-allowed hover:bg-zinc-700 dark:hover:bg-zinc-200 transition-colors">
            <DownloadIcon />
            Export PDF
          </button>

        </div>
      </header>

      {/* ══ MAIN ══════════════════════════════════════════════════════════════ */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-6 py-6">

          {/* 错误信息块 */}
          {status === 'error' && error && (
            <div className="mb-6 rounded-lg border border-red-200 bg-red-50 dark:bg-red-950/30 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-400">
              <strong>Failed: </strong>{error}
            </div>
          )}

          {/* 小抄标题（cards 上方，收到 meta 后出现） */}
          {metaTitle && (
            <h1 className="text-xl font-bold text-zinc-900 dark:text-zinc-50 mb-6 print:text-base print:mb-3">
              {metaTitle}
            </h1>
          )}

          {/* print-area：@media print 变两栏（见 globals.css） */}
          <div className="print-area">
            <CardList />
          </div>

        </div>
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
