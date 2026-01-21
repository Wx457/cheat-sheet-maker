// 全局状态管理
let currentProjectId = null
let currentOutlineData = null
let extendedTopics = []
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
            console.log('✅ 已生成并存储新的用户 ID:', newUserId)
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

function updateChunkCounter() {
  if (chunkCounter) {
    chunkCounter.textContent = `📚 ${chunkCount} Chunks`
  }
}

function persistChunkCount() {
  try {
    chrome.storage.local.set({ chunk_count: chunkCount })
  } catch (e) {
    console.error('保存 chunk_count 失败', e)
  }
}

// Header 折叠与摘要
let headerCollapsed = false

function buildHeaderSummary() {
  if (!headerSummaryMain) return
  const { courseName, examType, pageLimit } = collectFormData()
  const title = courseName || '课程未填写'
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
    toggleHeaderBtn.textContent = collapsed ? '展开' : '收起'
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
      const msg = errorData.detail?.message || errorData.detail || '重置失败'
      throw new Error(msg)
    }

    const data = await response.json()
    chunkCount = 0
    updateChunkCounter()
    persistChunkCount()
    setHeaderCollapsed(false) // 清空后自动展开表单，便于重新填写
    window.alert('Knowledge base cleared!')
    console.log('重置结果', data)
  } catch (error) {
    console.error('重置失败:', error)
  } finally {
    btnReset.disabled = false
  }
}

// 切换视图
function showView(viewName) {
  if (viewName === 'form') {
    viewForm.style.display = 'block'
    viewOutline.style.display = 'none'
  } else if (viewName === 'outline') {
    viewForm.style.display = 'none'
    viewOutline.style.display = 'block'
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
      throw new Error(response?.error || '无法获取页面内容')
    }
  } catch (error) {
    console.error('抓取页面内容失败:', error)
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
            throw new Error('分析结果缺少 topics 字段')
          }
        } else if (data.result.data) {
          if (expectTopics && data.result.data.topics) {
            return data.result.data
          } else if (!expectTopics) {
            return data.result
          } else {
            throw new Error('分析结果缺少 topics 字段')
          }
        } else if (!expectTopics && data.result) {
          return data.result
        } else if (data.result.error) {
          throw new Error(data.result.error)
        } else {
          throw new Error('任务完成但结果格式异常')
        }
      } else if (data.status === 'not_found' || data.error) {
        throw new Error(data.error || '任务未找到')
      }
      
      attempts++
      await new Promise(resolve => setTimeout(resolve, interval))
    } catch (error) {
      if (error.name === 'AbortError') {
        attempts++
        continue
      }
      console.error('轮询任务状态失败:', error)
      throw error
    }
  }
  
  throw new Error('任务处理超时（超过2分钟），请重试')
}

// ========== 数据收集功能 ==========

// 1. 扫描当前页面并保存
async function handleScanPage() {
  if (!btnScanPage) return
  setIngestButtonState(btnScanPage, 'loading', 'Scanning...')

  try {
    const { text, title, url } = await scrapePageContent()
    
    if (!text || text.trim().length === 0) {
      throw new Error('页面内容为空，无法保存')
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
      throw new Error(errorData.detail || '保存失败')
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
      throw new Error('保存失败')
    }
  } catch (error) {
    console.error('扫描失败:', error)
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
    window.alert('❌ 请输入文本内容')
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
      throw new Error(errorData.detail || '保存失败')
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
      throw new Error('保存失败')
    }
  } catch (error) {
    console.error('保存失败:', error)
  } finally {
    btnSaveText.disabled = false
  }
}

// 3. 上传PDF
async function handleUploadPdf() {
  const fileInput = document.getElementById('pdfFileInput')
  const file = fileInput.files[0]
  
  if (!file) {
    window.alert('❌ 请选择PDF文件')
    return
  }

  if (!file.name.toLowerCase().endsWith('.pdf')) {
    window.alert('❌ 仅支持PDF文件格式')
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
      throw new Error(errorData.detail || '上传失败')
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
      throw new Error('上传失败')
    }
  } catch (error) {
    console.error('上传失败:', error)
  } finally {
    btnUploadPdf.disabled = false
  }
}

// ========== 生成功能 ==========

// 下一步：生成大纲
async function handleNextGenerate() {
  if (!btnNextGenerate) return
  btnNextGenerate.disabled = true
  btnNextGenerate.textContent = 'Generating Outline...'
  // Step 1 不需要估时/计时
  if (estimateLabel) estimateLabel.textContent = ''

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
      throw new Error('未收到任务ID，请重试')
    }
    
    // 轮询任务状态
    const result = await pollTaskStatus(taskId)
    
    console.log('分析结果:', result)
    if (!result || !result.topics) {
      throw new Error('分析结果格式异常：缺少 topics 字段')
    }
    
    // 保存分析结果
    currentOutlineData = result
    
    // 渲染主题复选框列表
    renderOutlineList(result.topics)
    
    // 切换到大纲视图
    showView('outline')
    // 进入 Step 2（确认并生成）前，恢复主页面按钮状态，避免下次打开是错误状态
    btnNextGenerate.textContent = 'Next: Generate Outline'
    
  } catch (error) {
    console.error('生成失败:', error)
    // 错误时总是重置按钮状态，允许用户重试
    if (btnNextGenerate) {
      btnNextGenerate.disabled = false
      btnNextGenerate.textContent = 'Next: Generate Outline'
    }
    // 显示错误提示（可选）
    window.alert(`生成大纲失败: ${error.message}`)
  } finally {
    // 如果当前仍在form视图（说明没有成功切换到outline），确保按钮可用
    if (viewForm.style.display !== 'none' && btnNextGenerate) {
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
  } else {
    extendedTopics = []
  }
  
  renderExtendedTopics()
}

// 渲染扩展主题列表
function renderExtendedTopics() {
  outlineList.innerHTML = ''
  
  if (extendedTopics.length === 0) {
    outlineList.innerHTML = '<p style="color: #999; text-align: center;">未检测到主题</p>'
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
      label.textContent = `${topic.title} (相关性: ${(topic.relevance_score * 100).toFixed(0)}%)`
    } else {
      label.appendChild(document.createTextNode(topic.title))
      const customTag = document.createElement('span')
      customTag.className = 'topic-custom-tag'
      customTag.textContent = '自定义'
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
      throw new Error('请至少选择一个主题')
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
      throw new Error('未收到任务ID，请重试')
    }
    
    const result = await pollTaskStatus(taskId, 120, 3000, false)
    
    console.log('生成结果:', result)
    console.log('生成结果类型:', typeof result)
    console.log('生成结果键:', result ? Object.keys(result) : 'null')
    
    // 提取 project_id：可能在不同的位置
    let projectId = null
    if (result && typeof result === 'object') {
      // 尝试多种可能的位置
      projectId = result.project_id || 
                  result.data?.project_id || 
                  (result.data && result.data.project_id)
      
      console.log('提取的 project_id:', projectId)
    }
    
    if (!projectId) {
      // 如果仍然没有找到，记录详细错误信息
      console.error('无法找到 project_id，完整结果:', JSON.stringify(result, null, 2))
      throw new Error('生成结果格式异常：未找到 project_id。请查看控制台获取详细信息。')
    }
    
    currentProjectId = projectId

    // 调用 PDF 下载接口
    // 更新按钮状态显示正在下载PDF
    if (btnConfirmGenerate) {
      btnConfirmGenerate.textContent = '正在生成 PDF...'
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
      throw new Error(errorData.detail || `PDF 生成失败: ${pdfResponse.status}`)
    }

    const pdfBlob = await pdfResponse.blob()
    const pdfUrl = URL.createObjectURL(pdfBlob)
    
    // 确保元素存在
    if (!downloadLink) {
      throw new Error('无法找到下载链接元素')
    }
    if (!resultArea) {
      throw new Error('无法找到结果区域元素')
    }
    
    downloadLink.href = pdfUrl
    downloadLink.download = `cheat-sheet-${currentProjectId}.pdf`
    downloadLink.textContent = '下载生成的 Cheat Sheet (PDF)'
    
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
    
    console.log('✅ PDF生成成功，已显示结果区域')
    
  } catch (error) {
    console.error('生成失败:', error)
    // 显示错误信息给用户
    window.alert(`生成失败: ${error.message || error.toString()}`)
    // 确保按钮状态被重置
    if (btnConfirmGenerate) {
      btnConfirmGenerate.disabled = false
      btnConfirmGenerate.textContent = '确认并生成'
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
      btnConfirmGenerate.textContent = '确认并生成'
    }
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
showView('form')
chrome.storage.local.get(['chunk_count'], (result) => {
  if (typeof result?.chunk_count === 'number') {
    chunkCount = result.chunk_count
  }
  updateChunkCounter()
  // 启动时：有已存数据则收起，否则展开
  setHeaderCollapsed(chunkCount > 0)
})
buildHeaderSummary()

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
