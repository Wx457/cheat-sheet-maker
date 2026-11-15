/**
 * 本标签页的未保存草稿（Phase 6-6 缺口 2）
 *
 * 场景：生成完成后用户做了编辑，但自动保存失败（后端 / Supabase 不可用、网络断开）。
 * 这时刷新页面，内存里的修改会丢；重新生成又会命中缓存，拿回的是没改过的原始版本。
 *
 * 做法：有未保存修改时，把内容写进 sessionStorage；刷新后如果草稿与当前页面对得上，
 * 就恢复草稿（跳过生成 / 加载），并由自动保存继续重试。保存成功后删除草稿。
 *
 * 为什么用 sessionStorage：只属于当前标签页，刷新仍在、关闭标签页即清除；
 * 不会被别的标签页读到过期内容，用户登出后内容也不会一直留在这台电脑上。
 *
 * 一个标签页只有一个草稿槽，恢复前必须同时匹配：
 *   - scope：插件传入的 URL 参数（不含 sheetId），保证不会把 A 小抄恢复到 B 页面
 *   - sheetId：首次保存失败时两边都是 null；之后的 PUT 失败时两边是同一个 id
 *   - userId：同一标签页里换了 Clerk 账号时不恢复别人的草稿
 */

import type { ContentItem } from '@/types'

const STORAGE_KEY = 'cheatsheet-draft:v1'

export interface Draft {
  scope: string
  userId: string
  sheetId: string | null
  title: string
  sections: { title: string; items: ContentItem[] }[]
  savedAt: number
}

/** URL 参数（去掉 sheetId，按 key 排序）→ 稳定的 scope 字符串 */
export function draftScopeFromSearch(search: string): string {
  const params = new URLSearchParams(search)
  params.delete('sheetId')
  params.sort()
  return params.toString()
}

export function readDraft(): Draft | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const draft = JSON.parse(raw) as Draft
    if (!draft || typeof draft.scope !== 'string' || !Array.isArray(draft.sections)) return null
    return draft
  } catch {
    return null   // 存储被禁用 / 内容损坏：当作没有草稿
  }
}

export function writeDraft(draft: Draft): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(draft))
  } catch {
    // 配额满 / 存储被禁用：放弃兜底，不影响编辑
  }
}

export function clearDraft(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // ignore
  }
}

/** 草稿是否属于当前页面（scope + sheetId + 用户都一致） */
export function draftMatches(
  draft: Draft,
  scope: string,
  sheetId: string | null,
  userId: string,
): boolean {
  return draft.scope === scope && (draft.sheetId ?? null) === (sheetId ?? null) && draft.userId === userId
}
