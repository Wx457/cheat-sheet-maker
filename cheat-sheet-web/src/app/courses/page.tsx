'use client'

/**
 * Courses Page — 课程与版本历史（UPGRADE_PLAN 第 8 点 · 8-1）
 *
 *   /courses          课程列表（按最近使用倒序；默认课程「Uncategorized」总是存在）
 *   /courses?id=<id>  课程详情：所有小抄版本（按生成时间倒序），点击进入编辑器；改名 / 删除课程
 *
 * 新建课程在插件里完成（插件流程中选择已有课程或新建）。
 * 用查询参数而非动态路由 /courses/[id]：与编辑器一致，客户端组件 + useSearchParams（需 Suspense）。
 */

import { Suspense, useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { UserButton, useAuth } from '@clerk/nextjs'
import { ApiError, deleteCourse, getCourse, listCourses, updateCourse } from '@/lib/api'
import type { AcademicLevel, Course, CourseArchetype, CourseDetail } from '@/types'

// ─────────────────────────────────────────────────────────────────────────────
// 展示用文案
// ─────────────────────────────────────────────────────────────────────────────

const ARCHETYPE_LABEL: Record<CourseArchetype, string> = {
  stem_computational: 'STEM · Computational',
  stem_theoretical: 'STEM · Theoretical',
  coding: 'Coding / CS',
  humanities: 'Humanities',
  general: 'General',
}

const LEVEL_LABEL: Record<AcademicLevel, string> = {
  high_school: 'High School',
  undergraduate: 'Undergraduate',
  graduate: 'Graduate',
}

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
})

function formatDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : dateFormatter.format(d)
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// ─────────────────────────────────────────────────────────────────────────────
// 外框
// ─────────────────────────────────────────────────────────────────────────────

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <header className="sticky top-0 z-20 bg-white/90 dark:bg-zinc-900/90 backdrop-blur-sm border-b border-zinc-200 dark:border-zinc-800">
        <div className="flex items-center gap-3 px-5 py-3">
          <Link href="/courses" className="font-semibold text-zinc-900 dark:text-zinc-50 select-none">
            📄 Cheat Sheet Maker
          </Link>
          <span className="flex-1" />
          <UserButton />
        </div>
      </header>
      <main className="flex-1 w-full max-w-3xl mx-auto px-5 py-8">{children}</main>
    </div>
  )
}

function Spinner() {
  return (
    <div className="flex justify-center py-16">
      <div className="h-5 w-5 rounded-full border-2 border-zinc-300 border-t-zinc-600 animate-spin" />
    </div>
  )
}

function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 dark:bg-red-950/30 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-400 flex items-center gap-3">
      <span className="flex-1">{message}</span>
      {onRetry && (
        <button onClick={onRetry} className="text-xs font-medium underline underline-offset-2">Retry</button>
      )}
    </div>
  )
}

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-zinc-100 dark:bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-600 dark:text-zinc-400">
      {children}
    </span>
  )
}

function CourseBadges({ course }: { course: Course }) {
  return (
    <>
      {course.archetype && <Badge>{ARCHETYPE_LABEL[course.archetype] ?? course.archetype}</Badge>}
      {course.academic_level && <Badge>{LEVEL_LABEL[course.academic_level] ?? course.academic_level}</Badge>}
    </>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 课程列表
// ─────────────────────────────────────────────────────────────────────────────

function CourseList() {
  const { getToken } = useAuth()
  const [courses, setCourses] = useState<Course[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback((signal?: AbortSignal) => {
    listCourses(getToken, signal)
      .then((rows) => { setCourses(rows); setError(null) })
      .catch((err) => { if (!signal?.aborted) setError(errorMessage(err)) })
  }, [getToken])

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  return (
    <Shell>
      <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Your courses</h1>
      <p className="mt-1 mb-6 text-sm text-zinc-500 dark:text-zinc-400">
        Every generation is saved as a new version in its course. Create courses and generate
        cheat sheets from the Chrome extension.
      </p>

      {error && <ErrorBox message={`Could not load courses: ${error}`} onRetry={() => load()} />}
      {!error && courses === null && <Spinner />}

      {courses && (
        <ul className="grid gap-3 sm:grid-cols-2">
          {courses.map((course) => (
            <li key={course.id}>
              <Link href={`/courses?id=${encodeURIComponent(course.id)}`}
                className="block h-full rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 px-4 py-3 hover:border-zinc-400 dark:hover:border-zinc-600 transition-colors">
                <div className="flex items-baseline gap-2">
                  <span className="font-medium text-zinc-900 dark:text-zinc-50 truncate">{course.name}</span>
                  {course.is_default && <span className="text-[11px] text-zinc-400">default</span>}
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <CourseBadges course={course} />
                </div>
                <div className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
                  {course.sheet_count} {course.sheet_count === 1 ? 'version' : 'versions'}
                  {' · '}updated {formatDate(course.updated_at)}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Shell>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 课程详情（版本历史）
// ─────────────────────────────────────────────────────────────────────────────

function CourseView({ courseId }: { courseId: string }) {
  const { getToken } = useAuth()
  const router = useRouter()
  const [detail, setDetail] = useState<CourseDetail | null>(null)
  const [error, setError] = useState<{ message: string; notFound: boolean } | null>(null)

  const [renaming, setRenaming] = useState(false)
  const [nameDraft, setNameDraft] = useState('')
  const [renameError, setRenameError] = useState<string | null>(null)

  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const load = useCallback((signal?: AbortSignal) => {
    getCourse(courseId, getToken, signal)
      .then((d) => { setDetail(d); setError(null) })
      .catch((err) => {
        if (signal?.aborted) return
        const notFound = err instanceof ApiError && (err.status === 404 || err.status === 422)
        setError({ message: notFound ? 'This course does not exist.' : errorMessage(err), notFound })
      })
  }, [courseId, getToken])

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  const versionById = new Map(detail?.sheets.map((s) => [s.id, s.version]) ?? [])

  async function submitRename(e: React.FormEvent) {
    e.preventDefault()
    if (!detail) return
    const name = nameDraft.trim().replace(/\s+/g, ' ')
    if (!name || name === detail.course.name) { setRenaming(false); return }
    try {
      const course = await updateCourse(courseId, { name }, getToken)
      setDetail({ ...detail, course: { ...detail.course, ...course } })
      setRenaming(false)
      setRenameError(null)
    } catch (err) {
      setRenameError(err instanceof ApiError && err.status === 409
        ? `A course named "${name}" already exists.`
        : errorMessage(err))
    }
  }

  async function confirmDelete() {
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteCourse(courseId, getToken)
      router.push('/courses')
    } catch (err) {
      setDeleteError(errorMessage(err))
      setDeleting(false)
    }
  }

  return (
    <Shell>
      <Link href="/courses" className="text-sm text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100">
        ← All courses
      </Link>

      {error && (
        <div className="mt-6">
          <ErrorBox message={error.message} onRetry={error.notFound ? undefined : () => load()} />
        </div>
      )}
      {!error && detail === null && <Spinner />}

      {detail && (
        <>
          {/* 课程头部：名称（可改名）、默认参数、删除 */}
          <div className="mt-4 flex items-start gap-3">
            <div className="flex-1 min-w-0">
              {renaming ? (
                <form onSubmit={submitRename} className="flex items-center gap-2">
                  <input autoFocus value={nameDraft} maxLength={100}
                    onChange={(e) => setNameDraft(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Escape') setRenaming(false) }}
                    className="flex-1 min-w-0 rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-2 py-1 text-lg font-semibold text-zinc-900 dark:text-zinc-50 outline-none focus:ring-1 focus:ring-blue-400" />
                  <button type="submit" className="text-xs px-3 py-1.5 rounded-lg bg-zinc-900 dark:bg-zinc-50 text-white dark:text-zinc-900 font-medium">Save</button>
                  <button type="button" onClick={() => setRenaming(false)} className="text-xs px-3 py-1.5 rounded-lg border border-zinc-300 dark:border-zinc-600 text-zinc-600 dark:text-zinc-300">Cancel</button>
                </form>
              ) : (
                <div className="flex items-baseline gap-2">
                  <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50 truncate">{detail.course.name}</h1>
                  <button onClick={() => { setNameDraft(detail.course.name); setRenaming(true); setRenameError(null) }}
                    className="text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100 underline underline-offset-2">
                    Rename
                  </button>
                </div>
              )}
              {renameError && <p className="mt-1 text-xs text-red-600">{renameError}</p>}
              <div className="mt-2 flex flex-wrap gap-1.5">
                <CourseBadges course={detail.course} />
                {detail.course.is_default && <Badge>Default course</Badge>}
              </div>
            </div>
            <button onClick={() => { setConfirmingDelete(true); setDeleteError(null) }}
              className="shrink-0 text-xs px-3 py-1.5 rounded-lg border border-red-300 dark:border-red-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30">
              Delete course
            </button>
          </div>

          {confirmingDelete && (
            <div className="mt-4 rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/30 px-4 py-3 text-sm text-red-800 dark:text-red-300">
              <p>
                Delete <strong>{detail.course.name}</strong>, its {detail.sheets.length}{' '}
                {detail.sheets.length === 1 ? 'version' : 'versions'} and its knowledge base?
                This cannot be undone.
              </p>
              {deleteError && <p className="mt-2 text-xs">{deleteError}</p>}
              <div className="mt-3 flex gap-2">
                <button onClick={confirmDelete} disabled={deleting}
                  className="text-xs px-3 py-1.5 rounded-lg bg-red-600 text-white font-medium disabled:opacity-50">
                  {deleting ? 'Deleting…' : 'Delete permanently'}
                </button>
                <button onClick={() => setConfirmingDelete(false)} disabled={deleting}
                  className="text-xs px-3 py-1.5 rounded-lg border border-red-300 dark:border-red-700">
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* 版本列表 */}
          <h2 className="mt-8 mb-3 text-sm font-semibold text-zinc-700 dark:text-zinc-300">
            Versions ({detail.sheets.length})
          </h2>
          {detail.sheets.length === 0 ? (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              No cheat sheets yet. Select this course in the extension and generate one.
            </p>
          ) : (
            <ul className="divide-y divide-zinc-200 dark:divide-zinc-800 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">
              {detail.sheets.map((sheet) => {
                const parentVersion = sheet.parent_sheet_id ? versionById.get(sheet.parent_sheet_id) : undefined
                return (
                  <li key={sheet.id}>
                    <Link href={`/editor?sheetId=${encodeURIComponent(sheet.id)}`}
                      className="flex items-center gap-3 px-4 py-3 hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-colors">
                      <span className="w-10 shrink-0 text-sm font-mono text-zinc-500">v{sheet.version}</span>
                      <span className="flex-1 min-w-0">
                        <span className="block truncate text-sm text-zinc-900 dark:text-zinc-50">
                          {sheet.title || 'Untitled cheat sheet'}
                        </span>
                        <span className="block text-xs text-zinc-500 dark:text-zinc-400">
                          {sheet.origin === 'regenerate' ? 'Regenerated' : 'Generated'} {formatDate(sheet.created_at)}
                          {parentVersion !== undefined && ` · from v${parentVersion}`}
                          {sheet.updated_at !== sheet.created_at && ` · edited ${formatDate(sheet.updated_at)}`}
                        </span>
                      </span>
                      <span className="text-zinc-400 text-sm">→</span>
                    </Link>
                  </li>
                )
              })}
            </ul>
          )}
        </>
      )}
    </Shell>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Page export — <Suspense> 包裹（useSearchParams 要求）
// ─────────────────────────────────────────────────────────────────────────────

function CoursesContent() {
  const courseId = useSearchParams().get('id')
  // key：在两门课之间跳转时重置详情页内部状态
  return courseId ? <CourseView key={courseId} courseId={courseId} /> : <CourseList />
}

export default function CoursesPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <CoursesContent />
    </Suspense>
  )
}
