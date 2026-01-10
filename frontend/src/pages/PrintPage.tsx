import { useEffect, useState } from 'react'
import type { CheatSheet } from '../types'
import Preview from '../components/Preview'

/**
 * PrintPage 组件
 * 专门用于 PDF 生成的页面
 * 
 * 逻辑：
 * 1. 监听 window.CHEAT_SHEET_DATA 变量
 * 2. 一旦数据存在，渲染 Preview 组件
 * 3. 渲染完成后插入 #render-complete 标记
 */
const PrintPage = () => {
  const [cheatSheetData, setCheatSheetData] = useState<CheatSheet | null>(null)
  const [renderComplete, setRenderComplete] = useState(false)

  useEffect(() => {
    // 使用类型断言访问全局变量
    const windowWithData = window as typeof window & {
      CHEAT_SHEET_DATA?: CheatSheet
    }

    // 轮询检查 window.CHEAT_SHEET_DATA
    const checkForData = () => {
      if (windowWithData.CHEAT_SHEET_DATA && !cheatSheetData) {
        console.log('📄 Cheat Sheet data detected:', windowWithData.CHEAT_SHEET_DATA)
        setCheatSheetData(windowWithData.CHEAT_SHEET_DATA)
        // 不清除全局变量，保持数据以便后续使用
        return true
      }
      return false
    }

    // 立即检查一次（Playwright 可能在页面加载前就已注入数据）
    if (checkForData()) {
      return // 如果立即检测到数据，就不需要轮询了
    }

    // 轮询检查（每 50ms 检查一次，最多检查 10 秒）
    // 这样可以快速响应 Playwright 注入的数据
    let attempts = 0
    const maxAttempts = 200 // 200 * 50ms = 10秒
    
    const interval = setInterval(() => {
      attempts++
      if (checkForData() || attempts >= maxAttempts) {
        clearInterval(interval)
        if (attempts >= maxAttempts) {
          console.warn('⚠️ 超时：未检测到 CHEAT_SHEET_DATA')
        }
      }
    }, 50)

    // 清理定时器
    return () => clearInterval(interval)
  }, [cheatSheetData])

  useEffect(() => {
    // 当数据加载且渲染完成后，插入标记
    if (cheatSheetData && !renderComplete) {
      // 使用 setTimeout 确保 DOM 已经更新
      setTimeout(() => {
        // 检查是否已经存在标记
        if (!document.getElementById('render-complete')) {
          const marker = document.createElement('div')
          marker.id = 'render-complete'
          // 不要用 display: none====================================================
          marker.style.position = 'absolute'
          marker.style.top = '0'
          marker.style.opacity = '0' // 看不见，但 DOM 上是 visible 的
          document.body.appendChild(marker)
        }
        setRenderComplete(true)
        console.log('✅ Render complete marker inserted')
      }, 500) // 给 React 和 KaTeX 一点渲染时间
    }
  }, [cheatSheetData, renderComplete])

  // 渲染内容
  return (
    <div style={{ width: '100%', minHeight: '100vh', background: 'white' }}>
      {cheatSheetData ? (
        <Preview data={cheatSheetData} />
      ) : (
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center', 
          height: '100vh',
          color: '#666'
        }}>
          <div>等待数据注入...</div>
        </div>
      )}
    </div>
  )
}

export default PrintPage

