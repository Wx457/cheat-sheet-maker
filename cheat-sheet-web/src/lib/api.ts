/**
 * FastAPI 请求封装
 *
 * 封装所有非流式端点（摄入、大纲生成、任务轮询）。
 * 流式生成端点（/api/generate/stream）由 lib/streaming.ts 单独处理。
 */

import type {
  GenerateOutlineRequest,
  TaskResponse,
  OutlineTaskResult,
} from '@/types'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// ─────────────────────────────────────────────────────────────────────────────
// Auth token 工具（插件 → Webapp URL 传递的 JWT，存入 sessionStorage）
// 后续接入 Clerk 后，此处改为从 Clerk session 读取，调用方无需修改。
// ─────────────────────────────────────────────────────────────────────────────

const TOKEN_KEY = 'auth_token'

/** 从 sessionStorage 读取 JWT（SSR 环境返回 null） */
export function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null
  return sessionStorage.getItem(TOKEN_KEY)
}

/** 将插件传来的 JWT 存入 sessionStorage（在 editor page mount 时调用） */
export function storeAuthToken(token: string): void {
  if (typeof window === 'undefined') return
  sessionStorage.setItem(TOKEN_KEY, token)
}

/** 清除 token（登出时调用） */
export function clearAuthToken(): void {
  if (typeof window === 'undefined') return
  sessionStorage.removeItem(TOKEN_KEY)
}

// ─────────────────────────────────────────────────────────────────────────────
// 内部工具
// ─────────────────────────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options: RequestInit,
): Promise<T> {
  const token = getAuthToken()
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      // 有 token 时注入 Authorization 头（Clerk 接入后自动替换此逻辑）
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
  })

  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText)
    throw new Error(`API ${res.status}: ${detail}`)
  }

  return res.json() as Promise<T>
}

// ─────────────────────────────────────────────────────────────────────────────
// RAG 摄入
// ─────────────────────────────────────────────────────────────────────────────

export interface IngestResult {
  status: string
  chunks_count: number
  ingest_batch_id: string
  ingest_at: string
  truncated: boolean
}

/**
 * 将文本存入向量库（POST /api/rag/ingest）。
 *
 * @param text    原始文本
 * @param source  来源标识（课程名 / URL 等）
 * @param userId  用户 ID
 */
export async function ingestText(
  text: string,
  source: string,
  userId: string,
): Promise<IngestResult> {
  return apiFetch<IngestResult>('/api/rag/ingest', {
    method: 'POST',
    headers: { 'X-User-ID': userId },
    body: JSON.stringify({ text, source }),
  })
}

// ─────────────────────────────────────────────────────────────────────────────
// 大纲生成（异步任务）
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 提交大纲生成任务（POST /api/outline），立即返回 task_id。
 */
export async function submitOutlineTask(
  payload: GenerateOutlineRequest,
  userId: string,
): Promise<TaskResponse> {
  return apiFetch<TaskResponse>('/api/outline', {
    method: 'POST',
    headers: { 'X-User-ID': userId },
    body: JSON.stringify(payload),
  })
}

// ─────────────────────────────────────────────────────────────────────────────
// 任务状态轮询
// ─────────────────────────────────────────────────────────────────────────────

export interface PollResult<T = unknown> {
  status: 'pending' | 'processing' | 'complete' | 'failed'
  data?: T
  error?: string
}

/**
 * 查询 ARQ 任务结果（GET /api/task/{taskId}）。
 */
export async function getTaskResult<T = unknown>(
  taskId: string,
): Promise<PollResult<T>> {
  return apiFetch<PollResult<T>>(`/api/task/${taskId}`, {
    method: 'GET',
  })
}

/**
 * 轮询直到任务完成或超时。
 *
 * @param taskId        ARQ 任务 ID
 * @param intervalMs    轮询间隔（默认 2000ms）
 * @param timeoutMs     超时上限（默认 120000ms = 2 分钟）
 */
export async function pollUntilDone<T = unknown>(
  taskId: string,
  intervalMs = 2000,
  timeoutMs = 120_000,
): Promise<T> {
  const deadline = Date.now() + timeoutMs

  while (Date.now() < deadline) {
    const result = await getTaskResult<T>(taskId)

    if (result.status === 'complete') {
      if (result.data === undefined) throw new Error('Task complete but no data returned')
      return result.data
    }

    if (result.status === 'failed') {
      throw new Error(result.error ?? 'Task failed with unknown error')
    }

    // pending / processing → 等待后重试
    await new Promise<void>((resolve) => setTimeout(resolve, intervalMs))
  }

  throw new Error(`Task ${taskId} timed out after ${timeoutMs}ms`)
}

// ─────────────────────────────────────────────────────────────────────────────
// 便捷封装：提交大纲任务 + 等待结果
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 一步完成大纲生成：提交任务 → 轮询 → 返回 OutlineTaskResult。
 */
export async function generateOutline(
  payload: GenerateOutlineRequest,
  userId: string,
): Promise<OutlineTaskResult> {
  const { task_id } = await submitOutlineTask(payload, userId)
  return pollUntilDone<OutlineTaskResult>(task_id)
}

// ─────────────────────────────────────────────────────────────────────────────
// 知识库管理
// ─────────────────────────────────────────────────────────────────────────────

/** 获取当前用户的 chunks 数量 */
export async function getChunkCount(userId: string): Promise<number> {
  const res = await apiFetch<{ status: string; chunks_count: number }>(
    '/api/rag/chunks/count',
    { method: 'GET', headers: { 'X-User-ID': userId } },
  )
  return res.chunks_count
}

/** 清空当前用户的知识库向量数据 */
export async function clearKnowledgeBase(userId: string): Promise<void> {
  await apiFetch('/api/rag/clear', {
    method: 'DELETE',
    headers: { 'X-User-ID': userId },
  })
}
