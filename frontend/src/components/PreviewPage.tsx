import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import axios from 'axios'
import Preview from './Preview'
import type { CheatSheet } from '../types'

/**
 * 预览页面组件
 * 用于显示通过 project_id 从后端获取的小抄内容
 * 路由: /preview/:projectId
 */
export default function PreviewPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [cheatSheet, setCheatSheet] = useState<CheatSheet | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!projectId) {
      setError('缺少项目ID')
      setLoading(false)
      return
    }

    const fetchCheatSheet = async () => {
      try {
        setLoading(true)
        const response = await axios.get<CheatSheet>(
          `http://127.0.0.1:8000/api/plugin/project/${projectId}`
        )
        setCheatSheet(response.data)
        setError(null)
      } catch (err) {
        console.error('获取小抄数据失败:', err)
        setError('获取小抄数据失败，请确认项目ID是否正确')
      } finally {
        setLoading(false)
      }
    }

    fetchCheatSheet()
  }, [projectId])

  if (loading) {
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100vh',
        backgroundColor: '#f3f4f6'
      }}>
        <div style={{ color: '#666', fontSize: '16px' }}>加载中...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100vh',
        backgroundColor: '#f3f4f6'
      }}>
        <div style={{ color: '#ef4444', fontSize: '16px' }}>{error}</div>
      </div>
    )
  }

  if (!cheatSheet) {
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100vh',
        backgroundColor: '#f3f4f6'
      }}>
        <div style={{ color: '#666', fontSize: '16px' }}>未找到小抄数据</div>
      </div>
    )
  }

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f3f4f6' }}>
      <Preview data={cheatSheet} />
    </div>
  )
}

