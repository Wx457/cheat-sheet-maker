// 全局状态管理
let currentProjectId = null // 暂存第一步分析后的项目 ID（如果需要）
let currentOutlineData = null // 暂存分析结果
let extendedTopics = [] // 存储所有主题（AI检测的 + 自定义的）

// 获取页面元素
const viewForm = document.getElementById('view-form')
const viewOutline = document.getElementById('view-outline')
const statusEl = document.getElementById('status')
const outlineList = document.getElementById('outline-list')
const resultArea = document.getElementById('resultArea')
const downloadLink = document.getElementById('downloadLink')
const customTopicInput = document.getElementById('customTopicInput')
const btnAddCustomTopic = document.getElementById('btnAddCustomTopic')

// 按钮元素
const btnSaveOnly = document.getElementById('btnSaveOnly')
const btnGenerate = document.getElementById('btnGenerate')
const btnBack = document.getElementById('btnBack')
const btnConfirmGenerate = document.getElementById('btnConfirmGenerate')

// 显示状态消息
function showStatus(message, type = 'loading') {
  statusEl.textContent = message
  statusEl.className = `status-msg ${type}`
  statusEl.style.display = 'block'
}

// 隐藏状态消息
function hideStatus() {
  statusEl.style.display = 'none'
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

// 获取当前标签页信息
async function getCurrentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  return tab
}

// 抓取当前页面内容
async function scrapePageContent() {
  try {
    const tab = await getCurrentTab()
    
    // 向 content script 发送消息，请求抓取页面内容
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
      const response = await fetch(`http://127.0.0.1:8000/api/task/${taskId}`, {
        method: 'GET',
        signal: AbortSignal.timeout(5000)
      })
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`)
      }
      
      const data = await response.json()
      console.log('轮询任务状态:', { 
        status: data.status, 
        hasResult: !!data.result,
        resultKeys: data.result ? Object.keys(data.result) : null,
        resultType: data.result ? typeof data.result : null
      })
      
      if (data.status === 'completed' && data.result) {
        // 处理生成大纲的返回格式：{success: true, data: {topics: [...]}}
        if (data.result.success && data.result.data) {
          console.log('检测到生成大纲格式，提取 data:', data.result.data)
          if (expectTopics && data.result.data.topics) {
            return data.result.data
          } else if (!expectTopics) {
            // 生成小抄不需要 topics，直接返回整个 result
            return data.result
          } else {
            console.warn('data.result.data 缺少 topics 字段:', data.result.data)
            throw new Error('分析结果缺少 topics 字段')
          }
        } else if (data.result.data) {
          // 直接包含 data 字段
          console.log('检测到直接 data 格式，提取 data:', data.result.data)
          if (expectTopics && data.result.data.topics) {
            return data.result.data
          } else if (!expectTopics) {
            // 生成小抄不需要 topics，直接返回整个 result
            return data.result
          } else {
            console.warn('data.result.data 缺少 topics 字段:', data.result.data)
            throw new Error('分析结果缺少 topics 字段')
          }
        } else if (!expectTopics && data.result) {
          // 生成小抄的返回格式：直接返回 result（包含 project_id, file_key 等）
          console.log('检测到生成小抄格式，返回整个 result:', data.result)
          return data.result
        } else if (data.result.error) {
          throw new Error(data.result.error)
        } else {
          console.warn('任务完成但结果格式异常:', JSON.stringify(data.result, null, 2))
          throw new Error('任务完成但结果格式异常，请查看控制台')
        }
      } else if (data.status === 'not_found' || data.error) {
        throw new Error(data.error || '任务未找到')
      }
      
      // 如果还在处理中，继续轮询
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

// 第一阶段：分析接口
async function callAnalyzeAPI(content, formData, url) {
  try {
    // 提交分析任务
    const response = await fetch('http://127.0.0.1:8000/api/plugin/analyze', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        content: content,
        syllabus: formData.syllabus || null,
        url: url,
        course_name: formData.courseName || null,
        education_level: mapEducationLevel(formData.educationLevel),
        exam_type: mapExamType(formData.examType)
      })
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      const errorMsg = errorData.detail?.message || errorData.detail || errorData.message || `HTTP error! status: ${response.status}`
      throw new Error(errorMsg)
    }

    const taskData = await response.json()
    console.log('收到任务响应:', taskData)
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
    
    return result
  } catch (error) {
    console.error('分析失败:', error)
    throw error
  }
}

// 渲染主题复选框列表（支持显示扩展主题列表，包括自定义主题）
function renderOutlineList(topics) {
  outlineList.innerHTML = '' // 清空现有内容
  
  // 初始化 extendedTopics：将 AI 检测的主题转换为扩展格式
  if (topics && topics.length > 0) {
    extendedTopics = topics.map(t => ({ ...t, isCustom: false }))
  } else {
    extendedTopics = []
  }
  
  // 重新渲染所有主题（包括自定义的）
  renderExtendedTopics()
}

// 渲染扩展主题列表（包括 AI 检测的和自定义的）
function renderExtendedTopics() {
  outlineList.innerHTML = '' // 清空现有内容
  
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
    checkbox.checked = true // 默认全选
    checkbox.dataset.isCustom = topic.isCustom ? 'true' : 'false'
    
    const label = document.createElement('label')
    label.htmlFor = `topic-${index}`
    
    // 构建标签文本
    if (!topic.isCustom) {
      // AI 检测的主题：显示相关性分数
      label.textContent = `${topic.title} (相关性: ${(topic.relevance_score * 100).toFixed(0)}%)`
    } else {
      // 自定义主题：显示标题 + 自定义标记
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
  
  // 验证输入
  if (!trimmed) {
    return
  }
  
  // 检查是否已存在
  if (extendedTopics.some(t => t.title === trimmed)) {
    customTopicInput.value = ''
    return
  }
  
  // 计算 AI 检测主题的平均权重
  const aiTopics = extendedTopics.filter(t => !t.isCustom)
  const avgScore = aiTopics.length > 0
    ? aiTopics.reduce((sum, t) => sum + t.relevance_score, 0) / aiTopics.length
    : 0.5  // 如果没有 AI 主题，默认使用 0.5
  
  // 添加自定义主题
  const newTopic = {
    title: trimmed,
    relevance_score: avgScore,
    isCustom: true
  }
  
  extendedTopics.push(newTopic)
  customTopicInput.value = ''
  
  // 重新渲染列表
  renderExtendedTopics()
  
  // 更新添加按钮状态
  updateAddButtonState()
}

// 收集选中的主题（包括自定义主题）
function collectSelectedTopics() {
  const checkboxes = outlineList.querySelectorAll('input[type="checkbox"]:checked')
  const selectedTopics = []
  
  checkboxes.forEach(checkbox => {
    // 从 extendedTopics 中找到对应的 topic（包括自定义的）
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

// 第二阶段：生成最终内容接口
async function callGenerateFinalAPI(selectedTopics, formData) {
  try {
    // 提交生成任务
    const response = await fetch('http://127.0.0.1:8000/api/plugin/generate-final', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
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
    console.log('收到生成任务响应:', taskData)
    const taskId = taskData.task_id
    
    if (!taskId) {
      throw new Error('未收到任务ID，请重试')
    }
    
    // 轮询任务状态（expectTopics = false，因为生成小抄不需要 topics）
    showStatus('正在生成小抄...', 'loading')
    const result = await pollTaskStatus(taskId, 120, 3000, false) // 最多轮询120次，每次3秒（6分钟）
    
    console.log('生成结果:', result)
    
    // 生成小抄的返回格式：{status: "completed", file_key: ..., project_id: ..., data: {...}}
    // result 就是整个返回的字典
    if (result && result.project_id) {
      return { project_id: result.project_id }
    } else if (result && typeof result === 'object') {
      // 如果 result 是字典，尝试查找 project_id
      const projectId = result.project_id || result.data?.project_id
      if (projectId) {
        return { project_id: projectId }
      }
    }
    
    console.error('生成结果格式异常，未找到 project_id:', result)
    throw new Error('生成结果格式异常：未找到 project_id，请查看控制台')
  } catch (error) {
    console.error('生成失败:', error)
    throw error
  }
}

// 处理"仅保存"按钮点击
async function handleSaveOnly() {
  btnSaveOnly.disabled = true
  showStatus('正在抓取页面内容...', 'loading')

  try {
    // 1. 抓取页面内容
    const { text, title, url } = await scrapePageContent()
    
    if (!text || text.trim().length === 0) {
      throw new Error('页面内容为空，无法保存')
    }

    // 2. 保存到知识库（使用旧的接口）
    showStatus('正在保存到知识库...', 'loading')
    
    const saveResponse = await fetch('http://127.0.0.1:8000/api/rag/ingest', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        text: text,
        source: url || title
      })
    })

    if (!saveResponse.ok) {
      const errorData = await saveResponse.json().catch(() => ({}))
      throw new Error(errorData.detail || '保存失败')
    }

    const saveData = await saveResponse.json()
    
    if (saveData.status === 'success') {
      showStatus(`✅ 成功保存！共处理 ${saveData.chunks_count} 个切片`, 'success')
    } else {
      throw new Error('保存失败')
    }
  } catch (error) {
    showStatus(`❌ 错误: ${error.message}`, 'error')
    console.error('保存失败:', error)
  } finally {
    btnSaveOnly.disabled = false
  }
}

// 处理"一键生成"按钮点击（第一阶段）
async function handleGenerate() {
  btnGenerate.disabled = true
  showStatus('正在抓取页面内容...', 'loading')

  try {
    // 1. 抓取页面内容
    const { text, title, url } = await scrapePageContent()
    
    if (!text || text.trim().length === 0) {
      throw new Error('页面内容为空，无法生成')
    }

    // 2. 收集表单数据
    const formData = collectFormData()

    // 3. 调用分析接口
    showStatus('正在提交分析任务...', 'loading')
    const analyzeResult = await callAnalyzeAPI(text, formData, url)
    
    console.log('分析结果:', analyzeResult)
    
    // 4. 保存分析结果
    currentOutlineData = analyzeResult
    
    // 5. 渲染主题复选框列表
    if (!analyzeResult || !analyzeResult.topics) {
      throw new Error('分析结果格式异常：未找到 topics 字段')
    }
    
    renderOutlineList(analyzeResult.topics)
    
    // 6. 切换到大纲视图
    showView('outline')
    hideStatus()
    
  } catch (error) {
    showStatus(`❌ 错误: ${error.message}`, 'error')
    console.error('生成失败:', error)
  } finally {
    btnGenerate.disabled = false
  }
}

// 处理"返回修改"按钮点击
function handleBack() {
  showView('form')
  hideStatus()
  // 清空自定义主题输入框
  if (customTopicInput) {
    customTopicInput.value = ''
  }
}

// 处理"确认并生成"按钮点击（第二阶段）
async function handleConfirmGenerate() {
  btnConfirmGenerate.disabled = true
  showStatus('正在生成小抄...', 'loading')

  try {
    // 1. 收集表单数据
    const formData = collectFormData()
    
    // 2. 收集选中的主题
    const selectedTopics = collectSelectedTopics()
    
    if (selectedTopics.length === 0) {
      throw new Error('请至少选择一个主题')
    }

    // 3. 调用生成接口
    const generateResult = await callGenerateFinalAPI(selectedTopics, formData)
    
    // 4. 检查是否有 project_id
    if (!generateResult.project_id) {
      throw new Error('生成失败：未返回项目ID')
    }

    // 5. 调用 PDF 下载接口
    showStatus('正在生成 PDF...', 'loading')
    const pdfResponse = await fetch(
      `http://127.0.0.1:8000/api/plugin/download-cheat-sheet/${generateResult.project_id}`,
      {
        method: 'GET',
      }
    )

    if (!pdfResponse.ok) {
      const errorData = await pdfResponse.json().catch(() => ({}))
      throw new Error(errorData.detail || `PDF 生成失败: ${pdfResponse.status}`)
    }

    // 6. 获取 PDF 二进制数据并创建下载链接
    const pdfBlob = await pdfResponse.blob()
    const pdfUrl = URL.createObjectURL(pdfBlob)
    
    downloadLink.href = pdfUrl
    downloadLink.download = `cheat-sheet-${generateResult.project_id}.pdf`
    downloadLink.textContent = '下载生成的 Cheat Sheet (PDF)'
    resultArea.style.display = 'block'
    
    showStatus('✅ 生成成功！', 'success')
    
    // 切换回表单视图，显示结果
    showView('form')
    
  } catch (error) {
    showStatus(`❌ 错误: ${error.message}`, 'error')
    console.error('生成失败:', error)
  } finally {
    btnConfirmGenerate.disabled = false
  }
}

// 绑定事件
btnSaveOnly.addEventListener('click', handleSaveOnly)
btnGenerate.addEventListener('click', handleGenerate)
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
  
  // 初始化按钮状态
  updateAddButtonState()
}

// 页面加载时初始化
// 默认显示表单视图
showView('form')
