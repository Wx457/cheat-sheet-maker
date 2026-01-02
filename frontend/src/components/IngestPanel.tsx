import { useState } from 'react'
import axios from 'axios'
import '../App.css'

type IngestMode = 'text' | 'pdf'

interface IngestResponse {
  status: string
  chunks_count: number
}

const IngestPanel = () => {
  const [mode, setMode] = useState<IngestMode>('text')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  // 文本模式状态
  const [text, setText] = useState('')
  const [source, setSource] = useState('')

  // PDF 模式状态
  const [selectedFile, setSelectedFile] = useState<File | null>(null)

  const handleTextSubmit = async () => {
    if (!text.trim()) {
      setMessage({ type: 'error', text: '请输入文本内容' })
      return
    }
    if (!source.trim()) {
      setMessage({ type: 'error', text: '请输入来源名称' })
      return
    }

    setLoading(true)
    setMessage(null)

    try {
      const res = await axios.post<IngestResponse>(
        'http://127.0.0.1:8000/api/rag/ingest',
        {
          text: text.trim(),
          source: source.trim(),
        }
      )

      if (res.data.status === 'success') {
        setMessage({
          type: 'success',
          text: `✅ 成功存入知识库，共处理 ${res.data.chunks_count} 个切片`,
        })
        // 清空表单
        setText('')
        setSource('')
      }
    } catch (error: any) {
      const errorMsg =
        error.response?.data?.detail || error.message || '提交失败，请重试'
      setMessage({ type: 'error', text: errorMsg })
    } finally {
      setLoading(false)
    }
  }

  const handleFileSubmit = async () => {
    if (!selectedFile) {
      setMessage({ type: 'error', text: '请选择 PDF 文件' })
      return
    }

    setLoading(true)
    setMessage(null)

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)

      const res = await axios.post<IngestResponse>(
        'http://127.0.0.1:8000/api/rag/ingest/file',
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        }
      )

      if (res.data.status === 'success') {
        setMessage({
          type: 'success',
          text: `✅ 成功存入知识库，共处理 ${res.data.chunks_count} 个切片`,
        })
        // 清空文件选择
        setSelectedFile(null)
        // 重置文件输入框
        const fileInput = document.getElementById('pdf-file-input') as HTMLInputElement
        if (fileInput) {
          fileInput.value = ''
        }
      }
    } catch (error: any) {
      const errorMsg =
        error.response?.data?.detail || error.message || '上传失败，请重试'
      setMessage({ type: 'error', text: errorMsg })
    } finally {
      setLoading(false)
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      if (file.type !== 'application/pdf') {
        setMessage({ type: 'error', text: '仅支持 PDF 文件格式' })
        return
      }
      setSelectedFile(file)
      setMessage(null)
    }
  }

  return (
    <div className="input-card no-print">
      <div className="input-header">
        <h2>知识库摄入</h2>
      </div>

      {/* Tab 切换 */}
      <div
        style={{
          display: 'flex',
          gap: '8px',
          marginBottom: '16px',
          borderBottom: '1px solid #e5e7eb',
        }}
      >
        <button
          onClick={() => {
            setMode('text')
            setMessage(null)
          }}
          style={{
            padding: '8px 16px',
            border: 'none',
            background: mode === 'text' ? '#6366f1' : 'transparent',
            color: mode === 'text' ? '#fff' : '#6b7280',
            cursor: 'pointer',
            borderBottom: mode === 'text' ? '2px solid #6366f1' : '2px solid transparent',
            fontWeight: mode === 'text' ? 600 : 400,
            transition: 'all 0.2s',
          }}
        >
          文本输入
        </button>
        <button
          onClick={() => {
            setMode('pdf')
            setMessage(null)
          }}
          style={{
            padding: '8px 16px',
            border: 'none',
            background: mode === 'pdf' ? '#6366f1' : 'transparent',
            color: mode === 'pdf' ? '#fff' : '#6b7280',
            cursor: 'pointer',
            borderBottom: mode === 'pdf' ? '2px solid #6366f1' : '2px solid transparent',
            fontWeight: mode === 'pdf' ? 600 : 400,
            transition: 'all 0.2s',
          }}
        >
          PDF 上传
        </button>
      </div>

      {/* 文本模式 */}
      {mode === 'text' && (
        <>
          <div>
            <label className="form-label">文本内容 *</label>
            <textarea
              className="input-textarea"
              placeholder="在此粘贴文本内容..."
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={5}
            />
          </div>

          <div>
            <label className="form-label">来源名称 *</label>
            <input
              type="text"
              className="form-input"
              placeholder="例如：Chapter 1 Note"
              value={source}
              onChange={(e) => setSource(e.target.value)}
            />
          </div>

          <button
            className="primary-btn"
            onClick={handleTextSubmit}
            disabled={loading || !text.trim() || !source.trim()}
          >
            {loading ? '正在处理...' : '提交'}
          </button>
        </>
      )}

      {/* PDF 模式 */}
      {mode === 'pdf' && (
        <>
          <div>
            <label className="form-label">PDF 文件 *</label>
            <input
              id="pdf-file-input"
              type="file"
              accept=".pdf"
              onChange={handleFileChange}
              style={{
                width: '100%',
                padding: '10px',
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
                fontSize: '14px',
                cursor: 'pointer',
              }}
            />
            {selectedFile && (
              <div
                style={{
                  marginTop: '8px',
                  padding: '8px',
                  background: '#f0f9ff',
                  borderRadius: '6px',
                  fontSize: '13px',
                  color: '#0369a1',
                }}
              >
                已选择: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(2)} KB)
              </div>
            )}
          </div>

          <button
            className="primary-btn"
            onClick={handleFileSubmit}
            disabled={loading || !selectedFile}
          >
            {loading ? '正在处理...' : '上传并处理'}
          </button>
        </>
      )}

      {/* 状态反馈 */}
      {message && (
        <div
          style={{
            padding: '12px',
            borderRadius: '8px',
            fontSize: '14px',
            backgroundColor: message.type === 'success' ? '#d1fae5' : '#fee2e2',
            color: message.type === 'success' ? '#065f46' : '#991b1b',
            border: `1px solid ${
              message.type === 'success' ? '#a7f3d0' : '#fecaca'
            }`,
          }}
        >
          {message.text}
        </div>
      )}
    </div>
  )
}

export default IngestPanel

