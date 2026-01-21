// 全局状态管理
let currentProjectId = null
let currentOutlineData = null
let extendedTopics = []

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
const statusBar = document.getElementById('statusBar')
const outlineList = document.getElementById('outline-list')
const resultArea = document.getElementById('resultArea')
const downloadLink = document.getElementById('downloadLink')
const customTopicInput = document.getElementById('customTopicInput')
const btnAddCustomTopic = document.getElementById('btnAddCustomTopic')

// 按钮元素
const btnScanPage = document.getElementById('btnScanPage')
const btnSaveText = document.getElementById('btnSaveText')
const btnUploadPdf = document.getElementById('btnUploadPdf')
const btnNextGenerate = document.getElementById('btnNextGenerate')
const btnBack = document.getElementById('btnBack')
const btnConfirmGenerate = document.getElementById('btnConfirmGenerate')

// 标签页元素
const tabs = document.querySelectorAll('.tab')
const tabContents = document.querySelectorAll('.tab-content')

// 显示状态消息
function showStatusBar(message, type = '') {
  statusBar.textContent = message
  statusBar.className = `status-bar ${type}`
}

function clearStatusBar() {
  statusBar.textContent = ''
  statusBar.className = 'status-bar'
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
  btnScanPage.disabled = true
  showStatusBar('正在扫描页面...', 'loading')

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
      showStatusBar(`✅ 页面已扫描！已保存 ${data.chunks_count} 个切片到知识库`, 'success')
      setTimeout(clearStatusBar, 3000)
    } else {
      throw new Error('保存失败')
    }
  } catch (error) {
    showStatusBar(`❌ 错误: ${error.message}`, 'error')
    console.error('扫描失败:', error)
  } finally {
    btnScanPage.disabled = false
  }
}

// 2. 保存粘贴的文本
async function handleSaveText() {
  const textInput = document.getElementById('pasteTextInput')
  const text = textInput.value.trim()
  
  if (!text) {
    showStatusBar('❌ 请输入文本内容', 'error')
    return
  }

  btnSaveText.disabled = true
  showStatusBar('正在保存文本...', 'loading')

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
      showStatusBar(`✅ 文本已保存！已保存 ${data.chunks_count} 个切片到知识库`, 'success')
      textInput.value = '' // 清空输入框
      setTimeout(clearStatusBar, 3000)
    } else {
      throw new Error('保存失败')
    }
  } catch (error) {
    showStatusBar(`❌ 错误: ${error.message}`, 'error')
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
    showStatusBar('❌ 请选择PDF文件', 'error')
    return
  }

  if (!file.name.toLowerCase().endsWith('.pdf')) {
    showStatusBar('❌ 仅支持PDF文件格式', 'error')
    return
  }

  btnUploadPdf.disabled = true
  showStatusBar('正在上传PDF...', 'loading')

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
      showStatusBar(`✅ PDF已上传！已保存 ${data.chunks_count} 个切片到知识库`, 'success')
      fileInput.value = '' // 清空文件选择
      setTimeout(clearStatusBar, 3000)
    } else {
      throw new Error('上传失败')
    }
  } catch (error) {
    showStatusBar(`❌ 错误: ${error.message}`, 'error')
    console.error('上传失败:', error)
  } finally {
    btnUploadPdf.disabled = false
  }
}

// ========== 生成功能 ==========

// 下一步：生成大纲
async function handleNextGenerate() {
  btnNextGenerate.disabled = true
  showStatusBar('正在生成大纲...', 'loading')

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
    clearStatusBar()
    
  } catch (error) {
    showStatusBar(`❌ 错误: ${error.message}`, 'error')
    console.error('生成失败:', error)
  } finally {
    btnNextGenerate.disabled = false
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
  clearStatusBar()
  if (customTopicInput) {
    customTopicInput.value = ''
  }
}

// 处理确认并生成
async function handleConfirmGenerate() {
  btnConfirmGenerate.disabled = true
  showStatusBar('正在生成小抄...', 'loading')

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
    
    if (result && result.project_id) {
      currentProjectId = result.project_id
    } else if (result && typeof result === 'object') {
      const projectId = result.project_id || result.data?.project_id
      if (projectId) {
        currentProjectId = projectId
      }
    }
    
    if (!currentProjectId) {
      throw new Error('生成结果格式异常：未找到 project_id')
    }

    // 调用 PDF 下载接口
    showStatusBar('正在生成 PDF...', 'loading')
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
    
    downloadLink.href = pdfUrl
    downloadLink.download = `cheat-sheet-${currentProjectId}.pdf`
    downloadLink.textContent = '下载生成的 Cheat Sheet (PDF)'
    resultArea.style.display = 'block'
    
    showStatusBar('✅ 生成成功！', 'success')
    showView('form')
    
  } catch (error) {
    showStatusBar(`❌ 错误: ${error.message}`, 'error')
    console.error('生成失败:', error)
  } finally {
    btnConfirmGenerate.disabled = false
  }
}

// 绑定事件
btnScanPage.addEventListener('click', handleScanPage)
btnSaveText.addEventListener('click', handleSaveText)
btnUploadPdf.addEventListener('click', handleUploadPdf)
btnNextGenerate.addEventListener('click', handleNextGenerate)
btnBack.addEventListener('click', handleBack)
btnConfirmGenerate.addEventListener('click', handleConfirmGenerate)

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
