import { useCallback } from 'react'

interface InputAreaProps {
  value: string
  onChange: (val: string) => void
  onSubmit: () => void
  loading?: boolean
}

const InputArea = ({ value, onChange, onSubmit, loading = false }: InputAreaProps) => {
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        onSubmit()
      }
    },
    [onSubmit],
  )

  return (
    <div className="input-card no-print">
      <div className="input-header">
        <h2>输入文本</h2>
        <span className="hint">Ctrl/⌘ + Enter 快速生成</span>
      </div>
      <textarea
        className="input-textarea"
        placeholder="在此粘贴原始文本，点击 Generate 生成 Cheatsheet"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        rows={14}
      />
      <button
        className="primary-btn"
        onClick={onSubmit}
        disabled={loading || !value.trim()}
      >
        {loading ? 'Generating...' : 'Generate'}
      </button>
    </div>
  )
}

export default InputArea

