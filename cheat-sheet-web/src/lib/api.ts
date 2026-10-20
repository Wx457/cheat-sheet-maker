/**
 * FastAPI 请求封装
 *
 * 封装所有非流式端点（摄入、大纲生成、知识库管理）。
 * 流式生成端点（/api/generate/stream）由 lib/streaming.ts 单独处理。
 */

import type {
  CheatSheetRecord,
  CheatSheetSaveRequest,
  GenerateOutlineRequest,
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

/** 非 2xx 响应。保留 status，调用方可区分 404 等情况 */
export class ApiError extends Error {
  constructor(public readonly status: number, detail: string) {
    super(`API ${status}: ${detail}`)
    this.name = 'ApiError'
  }
}

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
    throw new ApiError(res.status, detail)
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
// 大纲生成
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 生成大纲（POST /api/outline）。后端在请求内完成 RAG + LLM，直接返回 topics。
 */
export async function generateOutline(
  payload: GenerateOutlineRequest,
  userId: string,
): Promise<OutlineTaskResult> {
  return apiFetch<OutlineTaskResult>('/api/outline', {
    method: 'POST',
    headers: { 'X-User-ID': userId },
    body: JSON.stringify(payload),
  })
}

// ─────────────────────────────────────────────────────────────────────────────
// 小抄持久化（UPGRADE_PLAN 3-4-c；后端存 Supabase，按 X-User-ID 校验归属）
// ─────────────────────────────────────────────────────────────────────────────

/** 生成完成后首次保存（POST /api/cheat-sheets），返回含 id 的记录 */
export async function createCheatSheet(
  body: CheatSheetSaveRequest,
  userId: string,
): Promise<CheatSheetRecord> {
  return apiFetch<CheatSheetRecord>('/api/cheat-sheets', {
    method: 'POST',
    headers: { 'X-User-ID': userId },
    body: JSON.stringify(body),
  })
}

/** 编辑后覆盖保存（PUT /api/cheat-sheets/{id}） */
export async function updateCheatSheet(
  id: string,
  body: CheatSheetSaveRequest,
  userId: string,
): Promise<CheatSheetRecord> {
  return apiFetch<CheatSheetRecord>(`/api/cheat-sheets/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: { 'X-User-ID': userId },
    body: JSON.stringify(body),
  })
}

/** 刷新页面时恢复（GET /api/cheat-sheets/{id}）。不存在或不属于该用户 → ApiError 404 */
export async function loadCheatSheet(
  id: string,
  userId: string,
  signal?: AbortSignal,
): Promise<CheatSheetRecord> {
  return apiFetch<CheatSheetRecord>(`/api/cheat-sheets/${encodeURIComponent(id)}`, {
    method: 'GET',
    headers: { 'X-User-ID': userId },
    signal,
  })
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
