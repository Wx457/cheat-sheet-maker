/**
 * SSE 流式解析工具
 *
 * 工作原理：
 *  1. 用 fetch + ReadableStream 发 POST 请求（EventSource 不支持 POST，故手动实现）
 *  2. 逐块读取字节流，用 TextDecoder 还原为字符串
 *  3. 按 "\n\n" 切分 SSE 事件（每个事件以双换行结束）
 *  4. 去掉 "data: " 前缀后 JSON.parse
 *  5. 根据事件类型调用对应回调：meta → onMeta，section → onSection，[DONE] → onDone
 */

import { authHeaders, type TokenGetter } from '@/lib/api'
import type { GenerateSheetRequest, StreamMetaEvent, StreamSectionEvent } from '@/types'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// ─────────────────────────────────────────────────────────────────────────────
// Public types
// ─────────────────────────────────────────────────────────────────────────────

export interface StreamCallbacks {
  /** 收到 meta 事件（含小抄标题） */
  onMeta: (event: StreamMetaEvent) => void
  /** 收到一个完整 section */
  onSection: (section: StreamSectionEvent) => void
  /** 流正常结束（收到 [DONE]） */
  onDone: () => void
  /** 网络或解析错误 */
  onError: (err: Error) => void
}

// ─────────────────────────────────────────────────────────────────────────────
// Main function
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 向 `/api/generate/stream` 发起 SSE 请求，解析每个事件并触发回调。
 *
 * @param payload   与后端 GenerateSheetRequest 对应的请求体
 * @param getToken  Clerk useAuth().getToken（放 Authorization: Bearer）
 * @param callbacks SSE 事件回调集合
 * @param signal    AbortController.signal，用于取消流（可选）
 */
export async function startStreaming(
  payload: GenerateSheetRequest,
  getToken: TokenGetter,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const { onMeta, onSection, onDone, onError } = callbacks

  let response: Response
  try {
    response = await fetch(`${API_URL}/api/generate/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(await authHeaders(getToken)),
      },
      body: JSON.stringify(payload),
      signal,
    })
  } catch (err) {
    // fetch 连接阶段同样需要过滤 AbortError（React StrictMode 的 cleanup 或用户主动取消）
    if (err instanceof Error && err.name === 'AbortError') return
    onError(err instanceof Error ? err : new Error(String(err)))
    return
  }

  if (!response.ok) {
    onError(new Error(`HTTP ${response.status}: ${response.statusText}`))
    return
  }

  if (!response.body) {
    onError(new Error('Response body is null — streaming not supported'))
    return
  }

  // ── 逐块读取字节流 ──────────────────────────────────────────────────────
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      // 将二进制 chunk 还原为字符串并追加到缓冲区
      buffer += decoder.decode(value, { stream: true })

      // SSE 事件以 "\n\n" 结尾，每次切出完整事件
      const events = buffer.split('\n\n')
      // 最后一段可能不完整，留在缓冲区等待更多 chunk
      buffer = events.pop() ?? ''

      for (const rawEvent of events) {
        // 去掉 "data: " 前缀
        if (!rawEvent.startsWith('data: ')) continue
        const jsonStr = rawEvent.slice(6).trim()

        // 哨兵：流正常结束
        if (jsonStr === '[DONE]') {
          onDone()
          return
        }

        // 解析 JSON
        let parsed: unknown
        try {
          parsed = JSON.parse(jsonStr)
        } catch {
          // 忽略无法解析的行（通常不会发生）
          console.warn('[streaming] Failed to parse SSE data:', jsonStr)
          continue
        }

        // 根据 _type 字段分发到不同回调
        if (
          typeof parsed === 'object' &&
          parsed !== null &&
          '_type' in parsed &&
          (parsed as Record<string, unknown>)['_type'] === 'meta'
        ) {
          onMeta(parsed as StreamMetaEvent)
        } else {
          // section 事件（无 _type 字段）
          onSection(parsed as StreamSectionEvent)
        }
      }
    }

    // 收到 [DONE] 会提前 return；走到这里说明后端在完成前断开了连接
    // （例如生成中途抛异常），否则页面会一直停在 "Generating…" 且无任何提示
    onError(new Error('Stream ended before completion — the server may have hit an error. Please retry.'))
  } catch (err) {
    // 处理 AbortError（用户主动取消）和其他网络错误
    if (err instanceof Error && err.name === 'AbortError') {
      // 正常取消，不触发 onError
      return
    }
    onError(err instanceof Error ? err : new Error(String(err)))
  } finally {
    reader.releaseLock()
  }
}
