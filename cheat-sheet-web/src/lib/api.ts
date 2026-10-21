/**
 * FastAPI 请求封装
 *
 * 封装 webapp 用到的非流式端点（小抄持久化）。摄入 / 大纲 / 知识库管理由插件直接调用后端。
 * 流式生成端点（/api/generate/stream）由 lib/streaming.ts 单独处理。
 */

import type { CheatSheetRecord, CheatSheetSaveRequest } from '@/types'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// ─────────────────────────────────────────────────────────────────────────────
// 鉴权（Phase 2）：Clerk session token → Authorization: Bearer
// 调用方传入 useAuth().getToken；后端从 token 的 sub 取用户身份，不再有 X-User-ID
// ─────────────────────────────────────────────────────────────────────────────

export type TokenGetter = () => Promise<string | null>

export async function authHeaders(getToken: TokenGetter): Promise<Record<string, string>> {
  const token = await getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
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
  getToken: TokenGetter,
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(await authHeaders(getToken)),
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
// 小抄持久化（UPGRADE_PLAN 3-4-c；后端存 Supabase，按 Clerk 用户校验归属）
// ─────────────────────────────────────────────────────────────────────────────

/** 生成完成后首次保存（POST /api/cheat-sheets），返回含 id 的记录 */
export async function createCheatSheet(
  body: CheatSheetSaveRequest,
  getToken: TokenGetter,
): Promise<CheatSheetRecord> {
  return apiFetch<CheatSheetRecord>('/api/cheat-sheets', {
    method: 'POST',
    body: JSON.stringify(body),
  }, getToken)
}

/** 编辑后覆盖保存（PUT /api/cheat-sheets/{id}） */
export async function updateCheatSheet(
  id: string,
  body: CheatSheetSaveRequest,
  getToken: TokenGetter,
): Promise<CheatSheetRecord> {
  return apiFetch<CheatSheetRecord>(`/api/cheat-sheets/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  }, getToken)
}

/** 刷新页面时恢复（GET /api/cheat-sheets/{id}）。不存在或不属于该用户 → ApiError 404 */
export async function loadCheatSheet(
  id: string,
  getToken: TokenGetter,
  signal?: AbortSignal,
): Promise<CheatSheetRecord> {
  return apiFetch<CheatSheetRecord>(`/api/cheat-sheets/${encodeURIComponent(id)}`, {
    method: 'GET',
    signal,
  }, getToken)
}
