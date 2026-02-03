// 全局状态管理（暴露到 window 以便 formPersistence.js 访问）
let currentProjectId = null
window.currentProjectId = currentProjectId
let currentOutlineData = null
window.currentOutlineData = currentOutlineData
let extendedTopics = []
window.extendedTopics = extendedTopics
let chunkCount = 0

// ========== [数据隔离] 用户 ID 管理 ==========
async function getOrCreateUserId() {
  return new Promise((resolve, reject) => {
    chrome.storage.local.get(['user_id'], (result) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message))
        return
      }
      
      if (result.user_id) {
        resolve(result.user_id)
      } else {
        const newUserId = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
          const r = Math.random() * 16 | 0
          const v = c === 'x' ? r : (r & 0x3 | 0x8)
          return v.toString(16)
        })
        
        chrome.storage.local.set({ user_id: newUserId }, () => {
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message))
          } else {
            console.log('✅ New user ID generated and stored:', newUserId)
            resolve(newUserId)
          }
        })
      }
    })
  })
}

async function getHeaders() {
  const userId = await getOrCreateUserId()
  return {
    'Content-Type': 'application/json',
    'X-User-ID': userId
  }
}

async function getHeadersForFile() {
  const userId = await getOrCreateUserId()
  return {
    'X-User-ID': userId
  }
}
// ========== [数据隔离] 用户 ID 管理结束 ==========

// 获取页面元素
const viewForm = document.getElementById('view-form')
const viewOutline = document.getElementById('view-outline')
const outlineList = document.getElementById('outline-list')
const resultArea = document.getElementById('resultArea')
const downloadLink = document.getElementById('downloadLink')
const btnBackHome = document.getElementById('btnBackHome')
const customTopicInput = document.getElementById('customTopicInput')
const btnAddCustomTopic = document.getElementById('btnAddCustomTopic')
const chunkCounter = document.getElementById('chunkCounter')
const btnReset = document.getElementById('btnReset')
const estimateLabel = document.getElementById('estimateLabel')
const headerAccordion = document.getElementById('headerAccordion')
const headerSummary = document.getElementById('headerSummary')
const headerSummaryMain = document.getElementById('headerSummaryMain')
const headerDetails = document.getElementById('headerDetails')
const toggleHeaderBtn = document.getElementById('toggleHeaderBtn')

// 按钮元素
const btnScanPage = document.getElementById('btnScanPage')
const btnSaveText = document.getElementById('btnSaveText')
const btnUploadPdf = document.getElementById('btnUploadPdf')
const btnNextGenerate = document.getElementById('btnNextGenerate')
const btnBack = document.getElementById('btnBack')
const btnConfirmGenerate = document.getElementById('btnConfirmGenerate')
const outlineEstimateLabel = document.getElementById('outlineEstimateLabel')

// 标签页元素
const tabs = document.querySelectorAll('.tab')
const tabContents = document.querySelectorAll('.tab-content')

// Step1（Generate Outline）计时
let outlineTimerId = null
let outlineElapsed = 0

// Step2（Confirm & Generate）计时
let contentTimerId = null
let contentElapsed = 0

// 采集按钮状态
function setIngestButtonState(button, state, label) {
  if (!button) return
  if (label) {
    button.textContent = label
  }
  if (state === 'loading') {
    button.disabled = true
  } else if (state === 'success') {
    button.disabled = true
  } else {
    button.disabled = false
  }
}

function autoCollapseHeaderIfNeeded() {
  if (chunkCount > 0 && !headerCollapsed) {
    setHeaderCollapsed(true)
  }
}

// 从后端获取最新的 chunks 数量并同步
async function syncChunkCountFromServer() {
  try {
    const headers = await getHeaders()
    const response = await fetch('http://127.0.0.1:8000/api/rag/chunks/count', {
      method: 'GET',
      headers
    })

    if (response.ok) {
      const data = await response.json()
      if (data.status === 'success' && typeof data.chunks_count === 'number') {
        chunkCount = data.chunks_count
        updateChunkCounter()
        persistChunkCount()
        setHeaderCollapsed(chunkCount > 0)
        console.log(`✅ 已从服务器同步 chunks 数量: ${chunkCount}`)
      }
    } else {
      console.warn('⚠️ 无法从服务器获取 chunks 数量，使用本地缓存值')
    }
  } catch (error) {
    console.warn('⚠️ 同步 chunks 数量失败，使用本地缓存值:', error)
  }
}

function updateChunkCounter() {
  if (chunkCounter) {
    chunkCounter.textContent = `📚 ${chunkCount} Chunks`
  }
}

function persistChunkCount() {
  try {
    chrome.storage.local.set({ chunk_count: chunkCount })
  } catch (e) {
    console.error('Failed to save chunk_count', e)
  }
}

// Header 折叠与摘要
let headerCollapsed = false

function buildHeaderSummary() {
  if (!headerSummaryMain) return
  const { courseName, examType, pageLimit } = collectFormData()
  const title = courseName || 'Course Name not filled'
  headerSummaryMain.textContent = `${title} | ${examType || 'Final'} | ${pageLimit || 'Unlimited'}`
}

function setHeaderCollapsed(collapsed) {
  headerCollapsed = collapsed
  if (!headerAccordion || !headerDetails || !headerSummary) return

  if (collapsed) {
    headerAccordion.classList.add('collapsed')
    headerDetails.classList.add('collapsed')
    headerSummary.style.display = 'flex'
  } else {
    headerAccordion.classList.remove('collapsed')
    headerDetails.classList.remove('collapsed')
    headerSummary.style.display = 'none'
  }
  if (toggleHeaderBtn) {
    toggleHeaderBtn.textContent = collapsed ? 'Expand' : 'Collapse'
  }
  buildHeaderSummary()
}

// 知识库重置
async function handleResetKnowledgeBase() {
  if (!btnReset) return
  const confirmed = window.confirm('Are you sure you want to clear the entire knowledge base? This cannot be undone.')
  if (!confirmed) return
  btnReset.disabled = true
  try {
    const headers = await getHeaders()
    const response = await fetch('http://127.0.0.1:8000/api/plugin/reset', {
      method: 'DELETE',
      headers
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      const msg = errorData.detail?.message || errorData.detail || 'Reset failed'
      throw new Error(msg)
    }

    const data = await response.json()
    chunkCount = 0
    updateChunkCounter()
    persistChunkCount()
    setHeaderCollapsed(false) // 清空后自动展开表单，便于重新填写
    window.alert('Knowledge base cleared!')
    console.log('Reset result', data)
  } catch (error) {
    console.error('Reset failed:', error)
  } finally {
    btnReset.disabled = false
  }
}

// 切换视图（保存为全局函数以便 formPersistence.js 可以拦截）
window.showView = function showView(viewName) {
  if (viewName === 'form') {
    viewForm.style.display = 'block'
    viewOutline.style.display = 'none'
  } else if (viewName === 'outline') {
    viewForm.style.display = 'none'
    viewOutline.style.display = 'block'
  }
  
  // 通知持久化模块视图已切换
  if (typeof formPersistence !== 'undefined' && formPersistence.saveFormData) {
    setTimeout(() => formPersistence.saveFormData(), 100)
  }
}

// 标签页切换
tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    const targetTab = tab.dataset.tab
    
    // 更新标签页状态
    tabs.forEach(t => t.classList.remove('active'))
    tab.classList.add('active')
    
    // 更新内容显示
    tabContents.forEach(content => {
      content.classList.remove('active')
      if (content.id === `tab-${targetTab}`) {
        content.classList.add('active')
      }
    })
  })
})

// 获取当前标签页信息
async function getCurrentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  return tab
}

// 抓取当前页面内容
async function scrapePageContent() {
  try {
    const tab = await getCurrentTab()
    const response = await chrome.tabs.sendMessage(tab.id, { action: 'scrape' })
    
    if (response && response.success && response.text && response.title) {
      return {
        text: response.text,
        title: response.title,
        url: tab.url
      }
    } else {
      throw new Error(response?.error || 'Failed to get page content')
    }
  } catch (error) {
    console.error('Failed to scrape page content:', error)
    throw error
  }
}

// 收集表单数据
function collectFormData() {
  const courseName = document.getElementById('courseName').value.trim()
  const educationLevel = document.querySelector('input[name="educationLevel"]:checked')?.value || 'Undergraduate'
  const examType = document.querySelector('input[name="examType"]:checked')?.value || 'Final'
  const pageLimit = document.querySelector('input[name="pageLimit"]:checked')?.value || 'Unlimited'
  const syllabus = document.getElementById('syllabusInput').value.trim()
  
  return {
    courseName,
    educationLevel,
    examType,
    pageLimit,
    syllabus
  }
}

// 映射前端值到后端枚举值
function mapEducationLevel(frontendValue) {
  const mapping = {
    'Undergraduate': 'undergraduate',
    'Graduate': 'graduate',
    'High School': 'high_school'
  }
  return mapping[frontendValue] || 'undergraduate'
}

function mapExamType(frontendValue) {
  const mapping = {
    'Quiz': 'quiz',
    'Midterm': 'midterm',
    'Final': 'final'
  }
  return mapping[frontendValue] || 'final'
}

function mapPageLimit(frontendValue) {
  const mapping = {
    '1 side': '1_side',
    '1 page': '1_page',
    '2 pages': '2_pages',
    'Unlimited': 'unlimited'
  }
  return mapping[frontendValue] || 'unlimited'
}

// 轮询任务状态
async function pollTaskStatus(taskId, maxAttempts = 60, interval = 2000, expectTopics = true) {
  let attempts = 0
  
  while (attempts < maxAttempts) {
    try {
      const headers = await getHeaders()
      const response = await fetch(`http://127.0.0.1:8000/api/task/${taskId}`, {
        method: 'GET',
        headers: headers,
        signal: AbortSignal.timeout(5000)
      })
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`)
      }
      
      const data = await response.json()
      
      if (data.status === 'completed' && data.result) {
        if (data.result.success && data.result.data) {
          if (expectTopics && data.result.data.topics) {
            return data.result.data
          } else if (!expectTopics) {
            return data.result
          } else {
            throw new Error('Analysis result missing topics field')
          }
        } else if (data.result.data) {
          if (expectTopics && data.result.data.topics) {
            return data.result.data
          } else if (!expectTopics) {
            return data.result
          } else {
            throw new Error('Analysis result missing topics field')
          }
        } else if (!expectTopics && data.result) {
          return data.result
        } else if (data.result.error) {
          throw new Error(data.result.error)
        } else {
          throw new Error('Task completed but result format is abnormal')
        }
      } else if (data.status === 'not_found' || data.error) {
        throw new Error(data.error || 'Task not found')
      }
      
      attempts++
      await new Promise(resolve => setTimeout(resolve, interval))
    } catch (error) {
      if (error.name === 'AbortError') {
        attempts++
        continue
      }
      console.error('Failed to poll task status:', error)
      throw error
    }
  }
  
  throw new Error('Task processing timeout (over 2 minutes), please retry')
}

// ========== 数据收集功能 ==========

// 1. 扫描当前页面并保存
async function handleScanPage() {
  if (!btnScanPage) return
  setIngestButtonState(btnScanPage, 'loading', 'Scanning...')

  try {
    const { text, title, url } = await scrapePageContent()
    
    if (!text || text.trim().length === 0) {
      throw new Error('Page content is empty, cannot save')
    }

    const headers = await getHeaders()
    const sourceName = document.getElementById('courseName').value.trim() || title || url

    const response = await fetch('http://127.0.0.1:8000/api/rag/ingest', {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({
        text: text,
        source: sourceName
      })
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || 'Save failed')
    }

    const data = await response.json()
    
    if (data.status === 'success') {
      chunkCount += Number(data.chunks_count || 0)
      updateChunkCounter()
      persistChunkCount()
      autoCollapseHeaderIfNeeded()
      setIngestButtonState(btnScanPage, 'success', '✅ Saved!')
      setTimeout(() => setIngestButtonState(btnScanPage, 'idle', 'Scan & Add to KB'), 2000)
    } else {
      throw new Error('Save failed')
    }
  } catch (error) {
    console.error('Scan failed:', error)
  } finally {
    if (btnScanPage) {
      btnScanPage.disabled = false
    }
  }
}

// 2. 保存粘贴的文本
async function handleSaveText() {
  const textInput = document.getElementById('pasteTextInput')
  const text = textInput.value.trim()
  
  if (!text) {
    window.alert('❌ Please enter text content')
    return
  }

  btnSaveText.disabled = true
  setIngestButtonState(btnSaveText, 'loading', 'Saving...')

  try {
    const headers = await getHeaders()
    const sourceName = document.getElementById('courseName').value.trim() || 'User Paste'

    const response = await fetch('http://127.0.0.1:8000/api/rag/ingest', {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({
        text: text,
        source: sourceName
      })
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || 'Save failed')
    }

    const data = await response.json()
    
    if (data.status === 'success') {
      chunkCount += Number(data.chunks_count || 0)
      updateChunkCounter()
      persistChunkCount()
      autoCollapseHeaderIfNeeded()
      textInput.value = '' // 清空输入框
      setIngestButtonState(btnSaveText, 'success', '✅ Saved!')
      setTimeout(() => setIngestButtonState(btnSaveText, 'idle', 'Save & Add to KB'), 2000)
    } else {
      throw new Error('Save failed')
    }
  } catch (error) {
    console.error('Save failed:', error)
  } finally {
    btnSaveText.disabled = false
  }
}

// 3. 上传PDF
async function handleUploadPdf() {
  const fileInput = document.getElementById('pdfFileInput')
  const file = fileInput.files[0]
  
  if (!file) {
    window.alert('❌ Please select a PDF file')
    return
  }

  if (!file.name.toLowerCase().endsWith('.pdf')) {
    window.alert('❌ Only PDF file format is supported')
    return
  }

  btnUploadPdf.disabled = true
  setIngestButtonState(btnUploadPdf, 'loading', 'Uploading...')

  try {
    const headers = await getHeadersForFile()
    const formData = new FormData()
    formData.append('file', file)

    const response = await fetch('http://127.0.0.1:8000/api/rag/ingest/file', {
      method: 'POST',
      headers: headers,
      body: formData
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || 'Upload failed')
    }

    const data = await response.json()
    
    if (data.status === 'success') {
      chunkCount += Number(data.chunks_count || 0)
      updateChunkCounter()
      persistChunkCount()
      autoCollapseHeaderIfNeeded()
      fileInput.value = '' // 清空文件选择
      setIngestButtonState(btnUploadPdf, 'success', '✅ Saved!')
      setTimeout(() => setIngestButtonState(btnUploadPdf, 'idle', 'Upload PDF & Add to KB'), 2000)
    } else {
      throw new Error('Upload failed')
    }
  } catch (error) {
    console.error('Upload failed:', error)
  } finally {
    btnUploadPdf.disabled = false
  }
}

// ========== 生成功能 ==========

// 下一步：生成大纲
async function handleNextGenerate() {
  if (!btnNextGenerate) return
  
  // Step 1：智能计时器（类似 Step 2）
  const estSeconds = Math.round(8 + (chunkCount * 0.3)) // Outline 生成通常比 Content 生成快
  if (estimateLabel) {
    estimateLabel.textContent = `Est: ~${estSeconds}s`
  }
  
  btnNextGenerate.disabled = true
  outlineElapsed = 0
  btnNextGenerate.textContent = 'Generating Outline... (0s)'
  if (outlineTimerId) {
    clearInterval(outlineTimerId)
  }
  outlineTimerId = setInterval(() => {
    outlineElapsed += 1
    btnNextGenerate.textContent = `Generating Outline... (${outlineElapsed}s)`
  }, 1000)

  try {
    const formData = collectFormData()
    const headers = await getHeaders()

    // 使用 syllabus 作为 raw_text，如果没有则使用通用提示
    const rawText = formData.syllabus || 'Generate outline from knowledge base based on all accumulated data'

    const response = await fetch('http://127.0.0.1:8000/api/outline', {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({
        raw_text: rawText,
        user_context: formData.courseName || null,
        exam_type: mapExamType(formData.examType)
      })
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      const errorMsg = errorData.detail?.message || errorData.detail || errorData.message || `HTTP error! status: ${response.status}`
      throw new Error(errorMsg)
    }

    const taskData = await response.json()
    const taskId = taskData.task_id
    
    if (!taskId) {
      throw new Error('No task ID received, please retry')
    }
    
    // 轮询任务状态
    const result = await pollTaskStatus(taskId)
    
    console.log('Analysis result:', result)
    if (!result || !result.topics) {
      throw new Error('Analysis result format error: missing topics field')
    }
    
    // 保存分析结果（同步到 window 对象）
    currentOutlineData = result
    window.currentOutlineData = result
    
    // 渲染主题复选框列表
    renderOutlineList(result.topics)
    
    // 成功：清掉计时器
    if (outlineTimerId) {
      clearInterval(outlineTimerId)
      outlineTimerId = null
    }
    if (estimateLabel) estimateLabel.textContent = ''
    
    // 切换到大纲视图
    showView('outline')
    // 进入 Step 2（确认并生成）前，恢复主页面按钮状态，避免下次打开是错误状态
    btnNextGenerate.textContent = 'Next: Generate Outline'
    
  } catch (error) {
    console.error('Generation failed:', error)
    // 确保计时器被清除
    if (outlineTimerId) {
      clearInterval(outlineTimerId)
      outlineTimerId = null
    }
    if (estimateLabel) {
      estimateLabel.textContent = ''
    }
    // 错误时总是重置按钮状态，允许用户重试
    if (btnNextGenerate) {
      btnNextGenerate.disabled = false
      btnNextGenerate.textContent = 'Next: Generate Outline'
    }
    // 显示错误提示（可选）
    window.alert(`Failed to generate outline: ${error.message}`)
  } finally {
    // 如果当前仍在form视图（说明没有成功切换到outline），确保按钮可用
    if (viewForm.style.display !== 'none' && btnNextGenerate) {
      if (outlineTimerId) {
        clearInterval(outlineTimerId)
        outlineTimerId = null
      }
      if (estimateLabel) {
        estimateLabel.textContent = ''
      }
      btnNextGenerate.disabled = false
      btnNextGenerate.textContent = 'Next: Generate Outline'
    }
  }
}

// 渲染主题复选框列表
function renderOutlineList(topics) {
  outlineList.innerHTML = ''
  
  if (topics && topics.length > 0) {
    extendedTopics = topics.map(t => ({ ...t, isCustom: false }))
    window.extendedTopics = extendedTopics
  } else {
    extendedTopics = []
    window.extendedTopics = []
  }
  
  renderExtendedTopics()
}

// 渲染扩展主题列表
function renderExtendedTopics() {
  outlineList.innerHTML = ''
  
  if (extendedTopics.length === 0) {
    outlineList.innerHTML = '<p style="color: #999; text-align: center;">No topics detected</p>'
    return
  }
  
  extendedTopics.forEach((topic, index) => {
    const item = document.createElement('div')
    item.className = 'outline-item'
    
    const checkbox = document.createElement('input')
    checkbox.type = 'checkbox'
    checkbox.id = `topic-${index}`
    checkbox.value = topic.title
    checkbox.checked = true
    checkbox.dataset.isCustom = topic.isCustom ? 'true' : 'false'
    
    const label = document.createElement('label')
    label.htmlFor = `topic-${index}`
    
    if (!topic.isCustom) {
      label.textContent = `${topic.title} (Relevance: ${(topic.relevance_score * 100).toFixed(0)}%)`
    } else {
      label.appendChild(document.createTextNode(topic.title))
      const customTag = document.createElement('span')
      customTag.className = 'topic-custom-tag'
      customTag.textContent = 'Custom'
      label.appendChild(customTag)
    }
    
    item.appendChild(checkbox)
    item.appendChild(label)
    outlineList.appendChild(item)
  })
}

// 添加自定义主题
function handleAddCustomTopic() {
  const trimmed = customTopicInput.value.trim()
  
  if (!trimmed) {
    return
  }
  
  if (extendedTopics.some(t => t.title === trimmed)) {
    customTopicInput.value = ''
    return
  }
  
  const aiTopics = extendedTopics.filter(t => !t.isCustom)
  const avgScore = aiTopics.length > 0
    ? aiTopics.reduce((sum, t) => sum + t.relevance_score, 0) / aiTopics.length
    : 0.5
  
  const newTopic = {
    title: trimmed,
    relevance_score: avgScore,
    isCustom: true
  }
  
  extendedTopics.push(newTopic)
  window.extendedTopics = extendedTopics
  customTopicInput.value = ''
  
  renderExtendedTopics()
  updateAddButtonState()
}

// 收集选中的主题
function collectSelectedTopics() {
  const checkboxes = outlineList.querySelectorAll('input[type="checkbox"]:checked')
  const selectedTopics = []
  
  checkboxes.forEach(checkbox => {
    const topic = extendedTopics.find(t => t.title === checkbox.value)
    if (topic) {
      selectedTopics.push({
        title: topic.title,
        relevance_score: topic.relevance_score
      })
    }
  })
  
  return selectedTopics
}

// 更新添加按钮状态
function updateAddButtonState() {
  const trimmed = customTopicInput.value.trim()
  btnAddCustomTopic.disabled = !trimmed || extendedTopics.some(t => t.title === trimmed)
}

// 处理返回按钮
function handleBack() {
  showView('form')
  if (customTopicInput) {
    customTopicInput.value = ''
  }
  
  // 清除 Step 1 的计时器（如果存在）
  if (outlineTimerId) {
    clearInterval(outlineTimerId)
    outlineTimerId = null
  }
  
  // CRITICAL: 重置主视图按钮状态，允许用户重新生成outline
  if (btnNextGenerate) {
    btnNextGenerate.disabled = false
    btnNextGenerate.textContent = 'Next: Generate Outline'
  }
  
  // 清除任何错误消息或状态信息
  if (estimateLabel) {
    estimateLabel.textContent = ''
  }
  
  // 注意：不重置 currentOutlineData，因为它可能被用于其他目的
  // 但每次点击 Next 时会重新生成，所以这应该没问题
}

// 处理确认并生成
async function handleConfirmGenerate() {
  if (!btnConfirmGenerate) return
  // Step 2：智能计时器（重活在这里）
  const estSeconds = Math.round(15 + (chunkCount * 0.6))
  if (outlineEstimateLabel) {
    outlineEstimateLabel.textContent = `Est: ~${estSeconds}s`
  }
  btnConfirmGenerate.disabled = true
  contentElapsed = 0
  btnConfirmGenerate.textContent = 'Generating Content... (0s)'
  if (contentTimerId) {
    clearInterval(contentTimerId)
  }
  contentTimerId = setInterval(() => {
    contentElapsed += 1
    btnConfirmGenerate.textContent = `Generating Content... (${contentElapsed}s)`
  }, 1000)

  try {
    const formData = collectFormData()
    const selectedTopics = collectSelectedTopics()
    
    if (selectedTopics.length === 0) {
      throw new Error('Please select at least one topic')
    }

    const headers = await getHeaders()
    const response = await fetch('http://127.0.0.1:8000/api/plugin/generate-final', {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({
        selected_topics: selectedTopics,
        syllabus: formData.syllabus || null,
        course_name: formData.courseName || null,
        education_level: mapEducationLevel(formData.educationLevel),
        exam_type: mapExamType(formData.examType),
        page_limit: mapPageLimit(formData.pageLimit)
      })
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      const errorMsg = errorData.detail?.message || errorData.detail || errorData.message || `HTTP error! status: ${response.status}`
      throw new Error(errorMsg)
    }

    const taskData = await response.json()
    const taskId = taskData.task_id
    
    if (!taskId) {
      throw new Error('No task ID received, please retry')
    }
    
    const result = await pollTaskStatus(taskId, 120, 3000, false)
    
    console.log('Generation result:', result)
    console.log('Generation result type:', typeof result)
    console.log('Generation result keys:', result ? Object.keys(result) : 'null')
    
    // 提取 project_id：可能在不同的位置
    let projectId = null
    if (result && typeof result === 'object') {
      // 尝试多种可能的位置
      projectId = result.project_id || 
                  result.data?.project_id || 
                  (result.data && result.data.project_id)
      
      console.log('Extracted project_id:', projectId)
    }
    
    if (!projectId) {
      // If still not found, log detailed error information
      console.error('Unable to find project_id, full result:', JSON.stringify(result, null, 2))
      throw new Error('Generation result format error: project_id not found. Please check console for details.')
    }
    
    currentProjectId = projectId

    // 调用 PDF 下载接口
    // 更新按钮状态显示正在下载PDF
    if (btnConfirmGenerate) {
      btnConfirmGenerate.textContent = 'Generating PDF...'
    }
    const pdfHeaders = await getHeaders()
    const pdfResponse = await fetch(
      `http://127.0.0.1:8000/api/plugin/download-cheat-sheet/${currentProjectId}`,
      {
        method: 'GET',
        headers: pdfHeaders
      }
    )

    if (!pdfResponse.ok) {
      const errorData = await pdfResponse.json().catch(() => ({}))
      throw new Error(errorData.detail || `PDF generation failed: ${pdfResponse.status}`)
    }

    const pdfBlob = await pdfResponse.blob()
    const pdfUrl = URL.createObjectURL(pdfBlob)
    
    // 确保元素存在
    if (!downloadLink) {
      throw new Error('Cannot find download link element')
    }
    if (!resultArea) {
      throw new Error('Cannot find result area element')
    }
    
    downloadLink.href = pdfUrl
    downloadLink.download = `cheat-sheet-${currentProjectId}.pdf`
    downloadLink.textContent = 'Download Generated Cheat Sheet (PDF)'
    
    // 成功：清掉计时器，关闭大纲页，展示结果区
    if (contentTimerId) {
      clearInterval(contentTimerId)
      contentTimerId = null
    }
    if (outlineEstimateLabel) outlineEstimateLabel.textContent = ''
    
    // 隐藏其他视图
    if (viewOutline) viewOutline.style.display = 'none'
    if (viewForm) viewForm.style.display = 'none'
    
    // 显示结果区域
    resultArea.style.display = 'block'
    
    // 任务完成后清除草稿
    if (typeof formPersistence !== 'undefined' && formPersistence.clearDraft) {
      formPersistence.clearDraft()
    }
    
    console.log('✅ PDF generated successfully, result area displayed')
    
  } catch (error) {
    console.error('Generation failed:', error)
    // 显示错误信息给用户
    window.alert(`Generation failed: ${error.message || error.toString()}`)
    // 确保按钮状态被重置
    if (btnConfirmGenerate) {
      btnConfirmGenerate.disabled = false
      btnConfirmGenerate.textContent = 'Submit'
    }
    // 确保计时器被清除
    if (contentTimerId) {
      clearInterval(contentTimerId)
      contentTimerId = null
    }
    if (outlineEstimateLabel) {
      outlineEstimateLabel.textContent = ''
    }
  } finally {
    if (contentTimerId) {
      clearInterval(contentTimerId)
      contentTimerId = null
    }
    if (outlineEstimateLabel && resultArea.style.display !== 'block') {
      outlineEstimateLabel.textContent = ''
    }
    if (resultArea.style.display !== 'block') {
      btnConfirmGenerate.disabled = false
      btnConfirmGenerate.textContent = 'Submit'
    }
  }
}

// 结果页：返回首页（表单视图）
function handleBackHome() {
  // 隐藏结果区域，返回表单视图
  if (resultArea) {
    resultArea.style.display = 'none'
  }
  if (viewForm) {
    viewForm.style.display = 'block'
  }
  if (viewOutline) {
    viewOutline.style.display = 'none'
  }

  // 重置与生成相关的按钮和提示，方便重新开始
  if (btnNextGenerate) {
    btnNextGenerate.disabled = false
    btnNextGenerate.textContent = 'Next: Generate Outline'
  }
  if (btnConfirmGenerate) {
    btnConfirmGenerate.disabled = false
    btnConfirmGenerate.textContent = 'Submit'
  }
  if (estimateLabel) {
    estimateLabel.textContent = ''
  }
  if (outlineEstimateLabel) {
    outlineEstimateLabel.textContent = ''
  }

  // 清理 PDF blob URL，避免内存泄漏
  if (downloadLink && downloadLink.href && downloadLink.href.startsWith('blob:')) {
    try {
      URL.revokeObjectURL(downloadLink.href)
    } catch (e) {
      console.warn('Failed to revoke object URL:', e)
    }
    downloadLink.href = '#'
  }
}

// 绑定事件
btnScanPage.addEventListener('click', handleScanPage)
btnSaveText.addEventListener('click', handleSaveText)
btnUploadPdf.addEventListener('click', handleUploadPdf)
btnNextGenerate.addEventListener('click', handleNextGenerate)
btnBack.addEventListener('click', handleBack)
btnConfirmGenerate.addEventListener('click', handleConfirmGenerate)
if (btnReset) {
  btnReset.addEventListener('click', handleResetKnowledgeBase)
}
if (btnBackHome) {
  btnBackHome.addEventListener('click', handleBackHome)
}

// 绑定自定义主题相关事件
if (btnAddCustomTopic && customTopicInput) {
  btnAddCustomTopic.addEventListener('click', handleAddCustomTopic)
  
  customTopicInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleAddCustomTopic()
    }
  })
  
  customTopicInput.addEventListener('input', updateAddButtonState)
  updateAddButtonState()
}

// 页面加载时初始化
// 先设置默认视图（如果持久化模块没有恢复视图，则使用默认值）
showView('form')

// 先从本地存储恢复 chunks 数量，然后从服务器同步最新值
chrome.storage.local.get(['chunk_count'], async (result) => {
  if (typeof result?.chunk_count === 'number') {
    chunkCount = result.chunk_count
    updateChunkCounter()
  }
  // 从服务器同步最新的 chunks 数量（覆盖本地缓存）
  await syncChunkCountFromServer()
})
buildHeaderSummary()

// 注意：formPersistence.js 的初始化在 popup.html 的 script 标签中处理
// 这样可以确保所有 DOM 元素和全局变量都已准备好

// Header Accordion：点击“编辑/摘要”展开
if (headerSummary) {
  headerSummary.addEventListener('click', () => {
    setHeaderCollapsed(false)
    const input = document.getElementById('courseName')
    if (input) input.focus()
  })
}

if (toggleHeaderBtn) {
  toggleHeaderBtn.addEventListener('click', () => {
    setHeaderCollapsed(!headerCollapsed)
    const input = document.getElementById('courseName')
    if (!headerCollapsed && input) input.focus()
  })
}

// 表单字段变化时，实时更新摘要（即便已折叠）
const courseNameInput = document.getElementById('courseName')
if (courseNameInput) {
  courseNameInput.addEventListener('input', buildHeaderSummary)
}
document.querySelectorAll('input[name="examType"], input[name="pageLimit"]').forEach((el) => {
  el.addEventListener('change', buildHeaderSummary)
})
