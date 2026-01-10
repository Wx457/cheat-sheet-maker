import axios from 'axios'
import { useState } from 'react'

import SetupForm from './components/SetupForm'
import TopicSelector from './components/TopicSelector'
import Preview from './components/Preview'
import IngestPanel from './components/IngestPanel'
import type {
  CheatSheet,
  OutlineResponse,
  PageLimit,
  AcademicLevel,
  ExamType,
  TopicInput,
} from './types'

import './App.css'

type Step = 'setup' | 'outline' | 'result'

function App() {
  const [currentStep, setCurrentStep] = useState<Step>('setup')
  const [loading, setLoading] = useState(false)
  const [showIngestPanel, setShowIngestPanel] = useState(false)
  
  // Step 1 数据
  const [setupData, setSetupData] = useState<{
    syllabus: string
    userContext?: string
    pageLimit: PageLimit
    academicLevel: AcademicLevel
    examType: ExamType
  } | null>(null)
  
  // Step 2 数据
  const [outlineData, setOutlineData] = useState<OutlineResponse | null>(null)
  
  // Step 3 数据
  const [cheatSheet, setCheatSheet] = useState<CheatSheet | null>(null)

  // Step 1 -> Step 2: 生成大纲
  const handleSetupNext = async (data: {
    syllabus: string
    userContext?: string
    pageLimit: PageLimit
    academicLevel: AcademicLevel
    examType: ExamType
  }) => {
    setSetupData(data)
    setLoading(true)
    
    try {
      const res = await axios.post<OutlineResponse>(
        'http://127.0.0.1:8000/api/outline',
        {
          raw_text: data.syllabus, // 生成大纲接口仍使用 raw_text，但传入 syllabus 内容
          user_context: data.userContext,
          exam_type: data.examType,
        }
      )
      setOutlineData(res.data)
      setCurrentStep('outline')
    } catch (error) {
      console.error(error)
      alert('生成大纲失败，请确认后端已启动。')
    } finally {
      setLoading(false)
    }
  }

  // Step 2 -> Step 3: 生成小抄
  const handleGenerate = async (selectedTopics: TopicInput[]) => {
    if (!setupData) return
    
    setLoading(true)
    
    try {
      const res = await axios.post<CheatSheet>(
        'http://127.0.0.1:8000/api/generate',
        {
          syllabus: setupData.syllabus,
          user_context: setupData.userContext,
          page_limit: setupData.pageLimit,
          academic_level: setupData.academicLevel,
          selected_topics: selectedTopics,
          exam_type: setupData.examType,
        }
      )
      setCheatSheet(res.data)
      setCurrentStep('result')
    } catch (error) {
      console.error(error)
      alert('生成小抄失败，请重试。')
    } finally {
      setLoading(false)
    }
  }

  // 重置到第一步
  const handleStartOver = () => {
    setCurrentStep('setup')
    setSetupData(null)
    setOutlineData(null)
    setCheatSheet(null)
  }

  return (
    <div className="page">
      <header className="page-header no-print">
        <div>
          <h1>Cheat Sheet Maker</h1>
          <p className="subtitle">三步向导：分析 → 选择 → 生成</p>
        </div>
        {currentStep === 'result' && (
          <>
            <button className="secondary-btn" onClick={handleStartOver}>
              重新开始
            </button>
            <button className="secondary-btn" onClick={() => window.print()}>
              打印 / 保存 PDF
            </button>
          </>
        )}
      </header>

      {/* 知识库管理区域 */}
      <div className="no-print" style={{ marginBottom: '16px' }}>
        <button
          onClick={() => setShowIngestPanel(!showIngestPanel)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 16px',
            border: '1px solid #e5e7eb',
            borderRadius: '8px',
            background: showIngestPanel ? '#6366f1' : '#ffffff',
            color: showIngestPanel ? '#ffffff' : '#111827',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: 500,
            transition: 'all 0.2s',
          }}
        >
          <span>{showIngestPanel ? '▼' : '▶'}</span>
          <span>知识库管理</span>
        </button>
        
        {showIngestPanel && (
          <div style={{ marginTop: '12px' }}>
            <IngestPanel />
          </div>
        )}
      </div>

      {/* 进度条 */}
      <div className="progress-bar no-print">
        <div className="progress-steps">
          <div className={`progress-step ${currentStep === 'setup' ? 'active' : ''} ${currentStep !== 'setup' ? 'completed' : ''}`}>
            <div className="step-number">1</div>
            <div className="step-label">输入信息</div>
          </div>
          <div className={`progress-step ${currentStep === 'outline' ? 'active' : ''} ${currentStep === 'result' ? 'completed' : ''}`}>
            <div className="step-number">2</div>
            <div className="step-label">选择主题</div>
          </div>
          <div className={`progress-step ${currentStep === 'result' ? 'active' : ''}`}>
            <div className="step-number">3</div>
            <div className="step-label">查看结果</div>
          </div>
        </div>
      </div>

      <div className="layout">
        {/* 左侧：输入区域 */}
        <div className="left-pane">
          {currentStep === 'setup' && (
            <SetupForm onNext={handleSetupNext} loading={loading} />
          )}
          
          {currentStep === 'outline' && outlineData && (
            <TopicSelector
              topics={outlineData.topics}
              onGenerate={handleGenerate}
              loading={loading}
            />
          )}
          
          {currentStep === 'result' && (
            <div className="input-card no-print">
              <h2>生成完成！</h2>
              <p>您的小抄已生成，请在右侧查看。</p>
              <button className="primary-btn" onClick={handleStartOver}>
                重新开始
              </button>
            </div>
          )}
        </div>

        {/* 右侧：预览区域 */}
        <div className="right-pane" style={{ position: 'relative', height: '100%', overflow: 'hidden' }}>
          {currentStep === 'result' && cheatSheet ? (
            <Preview data={cheatSheet} />
          ) : (
            <div className="preview-card" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#f3f4f6' }}>
              <div className="placeholder" style={{ color: '#666' }}>
                {currentStep === 'setup' && '请先输入信息并分析...'}
                {currentStep === 'outline' && '请选择主题并生成小抄...'}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default App
