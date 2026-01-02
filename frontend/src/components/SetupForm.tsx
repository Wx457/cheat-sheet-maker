import { useState } from 'react'
import type { PageLimit, AcademicLevel, ExamType } from '../types'

interface SetupFormProps {
  onNext: (data: {
    syllabus: string
    userContext?: string
    pageLimit: PageLimit
    academicLevel: AcademicLevel
    examType: ExamType
  }) => void
  loading?: boolean
}

const SetupForm = ({ onNext, loading = false }: SetupFormProps) => {
  const [examSyllabus, setExamSyllabus] = useState('')
  const [userContext, setUserContext] = useState('')
  const [pageLimit, setPageLimit] = useState<PageLimit>('1_page')
  const [academicLevel, setAcademicLevel] = useState<AcademicLevel>('undergraduate')
  const [examType, setExamType] = useState<ExamType>('final')

  const handleSubmit = () => {
    // 考试大纲现在是可选的，不再进行必填校验
    onNext({
      syllabus: examSyllabus.trim() || '',
      userContext: userContext.trim() || undefined,
      pageLimit,
      academicLevel,
      examType,
    })
  }

  return (
    <div className="input-card no-print">
      <div className="input-header">
        <h2>步骤 1: 输入信息</h2>
        <span className="hint">Ctrl/⌘ + Enter 快速分析</span>
      </div>

      <div>
        <label className="form-label">考试大纲 (可选)</label>
        <textarea
          className="input-textarea"
          placeholder="如有特定考试大纲，请在此粘贴 (最多 500 字)，AI 将以此为最高优先级生成小抄..."
          value={examSyllabus}
          onChange={(e) => setExamSyllabus(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
              handleSubmit()
            }
          }}
          rows={10}
          maxLength={500}
        />
        <div style={{ 
          textAlign: 'right', 
          fontSize: '12px', 
          color: '#6b7280', 
          marginTop: '4px' 
        }}>
          {examSyllabus.length}/500
        </div>
      </div>

      <div>
        <label className="form-label">课程名称 / 背景信息（可选）</label>
        <input
          type="text"
          className="form-input"
          placeholder="例如：高等数学、线性代数..."
          value={userContext}
          onChange={(e) => setUserContext(e.target.value)}
        />
      </div>

      <div className="form-row">
        <div className="form-group">
          <label className="form-label">页面限制</label>
          <select
            className="form-select"
            value={pageLimit}
            onChange={(e) => setPageLimit(e.target.value as PageLimit)}
          >
            <option value="1_side">1 面 (极度精简)</option>
            <option value="1_page">1 页 (紧凑模式)</option>
            <option value="2_pages">2 页 (标准复习)</option>
            <option value="unlimited">无限制 (详细模式)</option>
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">学术水平</label>
          <select
            className="form-select"
            value={academicLevel}
            onChange={(e) => setAcademicLevel(e.target.value as AcademicLevel)}
          >
            <option value="high_school">高中</option>
            <option value="undergraduate">本科</option>
            <option value="graduate">研究生</option>
          </select>
        </div>
      </div>

      <div className="form-row">
        <div className="form-group">
          <label className="form-label">考试类型</label>
          <select
            className="form-select"
            value={examType}
            onChange={(e) => setExamType(e.target.value as ExamType)}
          >
            <option value="quiz">Quiz (3-5 个主题)</option>
            <option value="midterm">Midterm (5-8 个主题)</option>
            <option value="final">Final (8-15 个主题)</option>
          </select>
        </div>
      </div>

      <button
        className="primary-btn"
        onClick={handleSubmit}
        disabled={loading}
      >
        {loading ? '分析中...' : '分析并规划'}
      </button>
    </div>
  )
}

export default SetupForm

