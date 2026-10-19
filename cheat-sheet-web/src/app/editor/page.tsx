'use client'

/**
 * Editor Page — 主编辑器页面（Webapp 只负责渲染最后一步编辑）
 *
 * 数据流：
 *   Chrome Extension（插件）
 *     → POST /api/rag/ingest → 得到 task_id
 *     → 立即 chrome.tabs.create({ url: '/editor?token=JWT&taskId=xxx&userId=x&...' })
 *
 *   Webapp（本页）
 *     → ① 读取 URL 参数
 *     → ② 将 token 存入 sessionStorage（6-3：auth token 过渡方案）
 *     → ③ 若有 taskId：进入 awaiting_rag，轮询 /api/task/{taskId}（6-2）
 *     → ④ RAG 完成后自动触发 POST /api/generate/stream（SSE）
 *     → ⑤ 用户拖拽 / 编辑 / 导出 PDF
 *     → ⑥ 刷新时若正在生成：beforeunload 警告（6-4）
 *
 * 页面状态机：
 *   idle → awaiting_rag → connecting → streaming → complete
 *          (轮询 taskId)   (SSE)                      |
 *                                                  error（任意阶段可跳入）
 *
 * ⚠️  useSearchParams() 必须在 <Suspense> 内使用（Next.js App Router 要求）
 */

import { Suspense, useEffect, useRef, useCallback, useMemo } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { useCheatSheetStore } from '@/stores/cheatSheetStore'
import { startStreaming } from '@/lib/streaming'
import { getTaskResult, storeAuthToken } from '@/lib/api'
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

    // 注意：dev 模式下不设 taskId，直接跳过 awaiting_rag 进入 SSE
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
// RAG 等待界面（awaiting_rag 状态）
// ─────────────────────────────────────────────────────────────────────────────

function AwaitingRagView({ progress }: { progress: number }) {
  return (
    <div className="flex flex-col items-center justify-center py-32 gap-5">
      {/* Spinner */}
      <div className="h-10 w-10 rounded-full border-2 border-zinc-200 dark:border-zinc-700 border-t-purple-500 animate-spin" />

      <div className="flex flex-col items-center gap-1.5 text-center">
        <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          Building knowledge base…
        </p>
        <p className="text-xs text-zinc-400 dark:text-zinc-500">
          The extension is ingesting your page content. This takes a few seconds.
        </p>
      </div>

      {/* Progress bar（仅在有进度值时显示） */}
      {progress > 0 && (
        <div className="w-52 flex flex-col items-end gap-1">
          <span className="text-[10px] text-zinc-400">{progress}%</span>
          <div className="w-full h-1.5 rounded-full bg-zinc-100 dark:bg-zinc-800 overflow-hidden">
            <div
              className="h-full bg-purple-500 transition-all duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}
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
  const taskId    = searchParams.get('taskId')  ?? null   // 6-2：RAG ingest task ID
  const context   = searchParams.get('context') ?? undefined
  const level     = (searchParams.get('level')     as AcademicLevel)   ?? 'undergraduate'
  const pageLimit = (searchParams.get('pageLimit') as PageLimit)       ?? '1_page'
  const archetype = (searchParams.get('archetype') as CourseArchetype) ?? 'general'
  const examType  = (searchParams.get('examType')  as ExamType | null) ?? undefined

  const selectedTopics = useMemo<TopicInput[] | undefined>(() => {
    const raw = searchParams.get('topics')
    if (!raw) return undefined
    try {
      const titles: string[] = JSON.parse(raw)
      return titles.map((title) => ({ title, relevance_score: 1 }))
    } catch { return undefined }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams.get('topics')])

  const hasPluginParams = !!searchParams.get('userId')

  // ── Zustand store ──────────────────────────────────────────────────────────
  const status              = useCheatSheetStore((s) => s.status)
  const error               = useCheatSheetStore((s) => s.error)
  const ragProgress         = useCheatSheetStore((s) => s.ragProgress)
  const metaTitle           = useCheatSheetStore((s) => s.metaTitle)
  const sections            = useCheatSheetStore((s) => s.sections)
  const reset               = useCheatSheetStore((s) => s.reset)
  const setStatus           = useCheatSheetStore((s) => s.setStatus)
  const setError            = useCheatSheetStore((s) => s.setError)
  const setRagProgress      = useCheatSheetStore((s) => s.setRagProgress)
  const setMetaTitle        = useCheatSheetStore((s) => s.setMetaTitle)
  const mergeOrAddSection   = useCheatSheetStore((s) => s.mergeOrAddSection)

  // ── Refs ───────────────────────────────────────────────────────────────────
  const abortRef   = useRef<AbortController | null>(null)
  const startedRef = useRef(false)   // 防止 StrictMode / URL 变化重复触发

  // ── 派生状态 ───────────────────────────────────────────────────────────────
  const isAwaitingOrGenerating =
    status === 'awaiting_rag' || status === 'connecting' || status === 'streaming'
  const isGenerating = status === 'connecting' || status === 'streaming'
  const canExport    = sections.length > 0

  // ── 6-3：token 存入 sessionStorage ─────────────────────────────────────────
  useEffect(() => {
    if (token) storeAuthToken(token)
  }, [token])

  // ── SSE 流式生成（被 auto-trigger 或 RAG 轮询完成后调用） ────────────────────
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

  // ── 6-2：自动触发（有插件参数时） ──────────────────────────────────────────
  useEffect(() => {
    if (!hasPluginParams) return
    if (startedRef.current) return
    if (status !== 'idle') return

    startedRef.current = true
    reset()

    if (taskId) {
      setStatus('awaiting_rag')
    } else {
      runStreaming()
    }

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

  // ── 6-2：RAG 任务轮询（awaiting_rag 阶段） ──────────────────────────────────
  useEffect(() => {
    if (status !== 'awaiting_rag' || !taskId) return

    let fakeProgress = 0   // 伪进度（后端有真实进度时替换 setRagProgress 来源）

    const interval = setInterval(async () => {
      try {
        const result = await getTaskResult(taskId)

        // 伪进度递增（每 2 秒 +5~8%，上限 90%）
        fakeProgress = Math.min(90, fakeProgress + 5 + Math.random() * 3)
        setRagProgress(Math.round(fakeProgress))

        if (result.status === 'complete') {
          clearInterval(interval)
          setRagProgress(100)
          // 稍作停顿让进度条动画完成
          setTimeout(() => runStreaming(), 300)
        }

        if (result.status === 'failed') {
          clearInterval(interval)
          setError(result.error ?? 'Knowledge base build failed. Please retry.')
        }
      } catch (err) {
        clearInterval(interval)
        setError(err instanceof Error ? err.message : 'Failed to check task status')
      }
    }, 2000)

    return () => clearInterval(interval)
  }, [status, taskId, runStreaming, setRagProgress, setError])

  // ── 6-4：刷新警告（生成中 / 等待中时拦截） ──────────────────────────────────
  useEffect(() => {
    if (!isAwaitingOrGenerating) return
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault() }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [isAwaitingOrGenerating])

  // ── 操作处理 ───────────────────────────────────────────────────────────────
  const handleCancel = () => {
    abortRef.current?.abort()
    startedRef.current = false   // 允许重新触发（如果用户重新打开相同 URL）
    reset()
  }

  const handleRetry = () => {
    startedRef.current = false
    reset()
    if (taskId) {
      setStatus('awaiting_rag')  // 重新进入轮询
    } else {
      runStreaming()
    }
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
            {metaTitle || (isAwaitingOrGenerating ? '…' : 'Ready')}
          </span>

          <StreamingStatus />

          {/* Cancel：等待 / 生成中可见 */}
          {isAwaitingOrGenerating && (
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

          {/* 6-2：RAG 等待界面 */}
          {status === 'awaiting_rag' && (
            <AwaitingRagView progress={ragProgress} />
          )}

          {/* 错误信息块 */}
          {status === 'error' && error && (
            <div className="mb-6 rounded-lg border border-red-200 bg-red-50 dark:bg-red-950/30 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-400">
              <strong>Failed: </strong>{error}
            </div>
          )}

          {/* 小抄标题（cards 上方，RAG 完成后出现） */}
          {metaTitle && status !== 'awaiting_rag' && (
            <h1 className="text-xl font-bold text-zinc-900 dark:text-zinc-50 mb-6 print:text-base print:mb-3">
              {metaTitle}
            </h1>
          )}

          {/* print-area：@media print 变两栏（见 globals.css） */}
          {status !== 'awaiting_rag' && (
            <div className="print-area">
              <CardList />
            </div>
          )}

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
