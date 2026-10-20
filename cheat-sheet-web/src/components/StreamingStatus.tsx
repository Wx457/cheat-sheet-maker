'use client'

import { useCheatSheetStore, type StreamStatus } from '@/stores/cheatSheetStore'

// ─────────────────────────────────────────────────────────────────────────────
// 每种状态对应的样式与文案
// ─────────────────────────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<
  StreamStatus,
  { label: string; color: string; icon: React.ReactNode }
> = {
  idle: {
    label: 'Ready',
    color: 'text-zinc-400',
    icon: <span className="inline-block w-2 h-2 rounded-full bg-zinc-400" />,
  },
  connecting: {
    label: 'Connecting…',
    color: 'text-yellow-500',
    icon: (
      <span className="inline-block w-2 h-2 rounded-full bg-yellow-400 animate-pulse" />
    ),
  },
  streaming: {
    label: 'Generating…',
    color: 'text-blue-500',
    icon: (
      <span className="inline-block w-2 h-2 rounded-full bg-blue-500 animate-ping" />
    ),
  },
  complete: {
    label: 'Done',
    color: 'text-green-500',
    icon: (
      // Simple checkmark SVG
      <svg
        className="w-3 h-3 text-green-500"
        fill="none"
        strokeWidth={2.5}
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
      </svg>
    ),
  },
  error: {
    label: 'Error',
    color: 'text-red-500',
    icon: (
      <svg
        className="w-3 h-3 text-red-500"
        fill="none"
        strokeWidth={2.5}
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
        />
      </svg>
    ),
  },
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export default function StreamingStatus() {
  const status = useCheatSheetStore((s) => s.status)
  const error = useCheatSheetStore((s) => s.error)
  const sections = useCheatSheetStore((s) => s.sections)

  const cfg = STATUS_CONFIG[status]

  return (
    <div className="flex items-center gap-3 px-4 py-2 rounded-lg bg-zinc-50 border border-zinc-200 dark:bg-zinc-900 dark:border-zinc-700 text-sm select-none">
      {/* 状态指示点 */}
      <span className="flex items-center justify-center w-4 h-4">{cfg.icon}</span>

      {/* 状态文字 */}
      <span className={`font-medium ${cfg.color}`}>{cfg.label}</span>

      {/* streaming 时：显示已生成 section 数 */}
      {status === 'streaming' && sections.length > 0 && (
        <span className="text-zinc-400">
          {sections.length} section{sections.length > 1 ? 's' : ''} received
        </span>
      )}

      {/* complete 时：显示总 section 数 */}
      {status === 'complete' && (
        <span className="text-zinc-400">
          {sections.length} section{sections.length !== 1 ? 's' : ''}
        </span>
      )}

      {/* error 时：显示错误信息 */}
      {status === 'error' && error && (
        <span className="text-red-400 truncate max-w-xs" title={error}>
          {error}
        </span>
      )}
    </div>
  )
}
