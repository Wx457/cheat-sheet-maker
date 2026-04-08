// Global state (exposed on window for formPersistence.js access)
let currentProjectId = null
window.currentProjectId = currentProjectId
let currentOutlineData = null
window.currentOutlineData = currentOutlineData
let extendedTopics = []
window.extendedTopics = extendedTopics
let chunkCount = 0
let lastIngestBatchId = null
let lastIngestAt = null

// API base URL from config.js / api-config.js (with fallback)
const API_BASE_URL =
  window.API_BASE_URL ||
  (window.API_CONFIG && window.API_CONFIG.LOCAL_API_ORIGIN) ||
  'http://localhost:8000'

// ========== Input estimation constants ==========
const ESTIMATED_CHARS_PER_CHUNK = 450
const MAX_CHUNKS_PER_INGEST = 200
const MAX_CHUNKS_PER_USER = 500

function estimateChunks(charCount) {
  return Math.ceil(charCount / ESTIMATED_CHARS_PER_CHUNK)
}

function handleIngestResponse(data, button, idleLabel) {
  const accepted = Number(data.chunks_count || 0)
  chunkCount += accepted
  persistLastIngestInfo(data.ingest_batch_id, data.ingest_at)
  updateChunkCounter()
  persistChunkCount()
  autoCollapseHeaderIfNeeded()

  if (data.truncated) {
    const kept = data.chunks_count
    const orig = data.original_chunks_count
    showNotice(
      `Input was too large: ${orig} chunks estimated, only ${kept} saved. ` +
      'Consider uploading as PDF or splitting into smaller batches.',
      'warning', 8000
    )
    setIngestButtonState(button, 'success', `⚠️ ${kept}/${orig} saved`)
  } else {
    setIngestButtonState(button, 'success', '✅ Saved!')
  }
  setTimeout(() => setIngestButtonState(button, 'idle', idleLabel), 2500)
}

// ========== User ID management (data isolation) ==========
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
// ========== End user ID management ==========

// ========== Unified notification banner ==========
let noticeTimerId = null

function showNotice(message, type = 'error', autoHideMs = 6000) {
  if (!message) return
  let notice = document.getElementById('runtime-notice')
  if (!notice) {
    notice = document.createElement('div')
    notice.id = 'runtime-notice'
    notice.style.position = 'fixed'
    notice.style.top = '10px'
    notice.style.left = '10px'
    notice.style.right = '10px'
    notice.style.padding = '8px 10px'
    notice.style.borderRadius = '8px'
    notice.style.fontSize = '12px'
    notice.style.lineHeight = '1.4'
    notice.style.zIndex = '9999'
    notice.style.boxShadow = '0 2px 8px rgba(0,0,0,0.15)'
    document.body.appendChild(notice)
  }

  const styleMap = {
    error: { background: '#fee2e2', border: '#fecaca', color: '#991b1b' },
    warning: { background: '#fff7ed', border: '#fed7aa', color: '#9a3412' },
    info: { background: '#f3e8ff', border: '#d8b4fe', color: '#6b21a8' },
    success: { background: '#dcfce7', border: '#86efac', color: '#166534' }
  }
  const style = styleMap[type] || styleMap.error
  notice.style.backgroundColor = style.background
  notice.style.border = `1px solid ${style.border}`
  notice.style.color = style.color
  notice.textContent = message
  notice.style.display = 'block'

  if (noticeTimerId) {
    clearTimeout(noticeTimerId)
    noticeTimerId = null
  }
  if (autoHideMs > 0) {
    noticeTimerId = setTimeout(() => {
      const n = document.getElementById('runtime-notice')
      if (n) n.style.display = 'none'
    }, autoHideMs)
  }
}

async function parseErrorMessage(response, fallbackMessage) {
  const fallback = `${fallbackMessage} (HTTP ${response.status})`
  const errorData = await response.json().catch(() => null)
  if (!errorData) return fallback

  const detail = errorData.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail.message === 'string' && detail.message.trim()) return detail.message
  if (typeof errorData.message === 'string' && errorData.message.trim()) return errorData.message
  if (typeof errorData.error === 'string' && errorData.error.trim()) return errorData.error
  return fallback
}

function showConfirmDialog(title, message, confirmText = 'Confirm', cancelText = 'Cancel') {
  return new Promise((resolve) => {
    const existing = document.getElementById('runtime-confirm-overlay')
    if (existing) existing.remove()

    const overlay = document.createElement('div')
    overlay.id = 'runtime-confirm-overlay'
    overlay.style.position = 'fixed'
    overlay.style.inset = '0'
    overlay.style.background = 'rgba(15, 23, 42, 0.45)'
    overlay.style.zIndex = '10000'
    overlay.style.display = 'flex'
    overlay.style.alignItems = 'center'
    overlay.style.justifyContent = 'center'
    overlay.style.padding = '12px'

    const dialog = document.createElement('div')
    dialog.style.width = '100%'
    dialog.style.maxWidth = '360px'
    dialog.style.background = '#ffffff'
    dialog.style.border = '1px solid #e5e7eb'
    dialog.style.borderRadius = '10px'
    dialog.style.boxShadow = '0 10px 30px rgba(0, 0, 0, 0.2)'
    dialog.style.padding = '14px'

    const titleEl = document.createElement('div')
    titleEl.textContent = title
    titleEl.style.fontSize = '14px'
    titleEl.style.fontWeight = '700'
    titleEl.style.color = '#0f172a'
    titleEl.style.marginBottom = '8px'

    const messageEl = document.createElement('div')
    messageEl.textContent = message
    messageEl.style.fontSize = '12px'
    messageEl.style.lineHeight = '1.5'
    messageEl.style.color = '#334155'
    messageEl.style.marginBottom = '12px'

    const actions = document.createElement('div')
    actions.style.display = 'flex'
    actions.style.justifyContent = 'flex-end'
    actions.style.gap = '8px'

    const cancelBtn = document.createElement('button')
    cancelBtn.textContent = cancelText
    cancelBtn.style.border = '1px solid #cbd5e1'
    cancelBtn.style.background = '#ffffff'
    cancelBtn.style.color = '#334155'
    cancelBtn.style.borderRadius = '8px'
    cancelBtn.style.padding = '6px 10px'
    cancelBtn.style.fontSize = '12px'
    cancelBtn.style.cursor = 'pointer'

    const confirmBtn = document.createElement('button')
    confirmBtn.textContent = confirmText
    confirmBtn.style.border = 'none'
    confirmBtn.style.background = '#ef4444'
    confirmBtn.style.color = '#ffffff'
    confirmBtn.style.borderRadius = '8px'
    confirmBtn.style.padding = '6px 10px'
    confirmBtn.style.fontSize = '12px'
    confirmBtn.style.fontWeight = '600'
    confirmBtn.style.cursor = 'pointer'

    let resolved = false
    const cleanup = (result) => {
      if (resolved) return
      resolved = true
      document.removeEventListener('keydown', onKeyDown)
      overlay.remove()
      resolve(result)
    }

    const onKeyDown = (event) => {
      if (event.key === 'Escape') cleanup(false)
      if (event.key === 'Enter') cleanup(true)
    }
    document.addEventListener('keydown', onKeyDown)

    cancelBtn.addEventListener('click', () => cleanup(false))
    confirmBtn.addEventListener('click', () => cleanup(true))
    overlay.addEventListener('click', (event) => {
      if (event.target === overlay) cleanup(false)
    })

    actions.appendChild(cancelBtn)
    actions.appendChild(confirmBtn)
    dialog.appendChild(titleEl)
    dialog.appendChild(messageEl)
    dialog.appendChild(actions)
    overlay.appendChild(dialog)
    document.body.appendChild(overlay)
    confirmBtn.focus()
  })
}

// DOM element references
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

// Button elements
const btnScanPage = document.getElementById('btnScanPage')
const btnSaveText = document.getElementById('btnSaveText')
const btnUploadPdf = document.getElementById('btnUploadPdf')
const btnNextGenerate = document.getElementById('btnNextGenerate')
const btnBack = document.getElementById('btnBack')
const btnConfirmGenerate = document.getElementById('btnConfirmGenerate')
const outlineEstimateLabel = document.getElementById('outlineEstimateLabel')

// Tab elements
const tabs = document.querySelectorAll('.tab')
const tabContents = document.querySelectorAll('.tab-content')

// Step 1 (Generate Outline) timer
let outlineTimerId = null
let outlineElapsed = 0

// Step 2 (Confirm & Generate) timer
let contentTimerId = null
let contentElapsed = 0

// Ingest button state helper
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

// Sync latest chunk count from server
async function syncChunkCountFromServer() {
  try {
    const headers = await getHeaders()
    const response = await fetch(`${API_BASE_URL}/api/rag/chunks/count`, {
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
        console.log(`✅ Synced chunk count from server: ${chunkCount}`)
      }
    } else {
      const msg = await parseErrorMessage(response, 'Failed to sync chunk count')
      showNotice(`${msg} — showing local cache.`, 'info', 4500)
      console.warn('⚠️ Cannot fetch chunk count from server, using local cache')
    }
  } catch (error) {
    showNotice('Failed to sync chunk count — showing local cache.', 'info', 4500)
    console.warn('⚠️ Chunk count sync failed, using local cache:', error)
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

function persistLastIngestInfo(ingestBatchId, ingestAt) {
  if (!ingestBatchId) return
  lastIngestBatchId = ingestBatchId
  lastIngestAt = ingestAt || null
  try {
    chrome.storage.local.set({
      last_ingest_batch_id: lastIngestBatchId,
      last_ingest_at: lastIngestAt
    })
  } catch (e) {
    console.error('Failed to save last ingest info', e)
  }
}

// Header accordion & summary
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

// Knowledge base reset
async function handleResetKnowledgeBase() {
  if (!btnReset) return
  const confirmed = await showConfirmDialog(
    'Clear knowledge base?',
    'Are you sure you want to clear the entire knowledge base? This cannot be undone.',
    'Clear',
    'Cancel'
  )
  if (!confirmed) return
  btnReset.disabled = true
  try {
    const headers = await getHeaders()
    const response = await fetch(`${API_BASE_URL}/api/plugin/reset`, {
      method: 'DELETE',
      headers
    })

    if (!response.ok) {
      const msg = await parseErrorMessage(response, 'Failed to reset knowledge base')
      throw new Error(msg)
    }

    const data = await response.json()
    chunkCount = 0
    lastIngestBatchId = null
    lastIngestAt = null
    updateChunkCounter()
    persistChunkCount()
    chrome.storage.local.remove(['last_ingest_batch_id', 'last_ingest_at'])
    setHeaderCollapsed(false) // Auto-expand form after clearing
    showNotice('Knowledge base cleared!', 'success', 2200)
    console.log('Reset result', data)
  } catch (error) {
    showNotice(`Reset failed: ${error.message || error}`, 'error', 7000)
    console.error('Reset failed:', error)
  } finally {
    btnReset.disabled = false
  }
}

// View switching (global function so formPersistence.js can call it)
window.showView = function showView(viewName) {
  if (viewName === 'form') {
    viewForm.style.display = 'block'
    viewOutline.style.display = 'none'
  } else if (viewName === 'outline') {
    viewForm.style.display = 'none'
    viewOutline.style.display = 'block'
  }
  
  // Notify persistence module of view change
  if (typeof formPersistence !== 'undefined' && formPersistence.saveFormData) {
    setTimeout(() => formPersistence.saveFormData(), 100)
  }
}

// Tab switching
tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    const targetTab = tab.dataset.tab
    
    tabs.forEach(t => t.classList.remove('active'))
    tab.classList.add('active')
    
    tabContents.forEach(content => {
      content.classList.remove('active')
      if (content.id === `tab-${targetTab}`) {
        content.classList.add('active')
      }
    })
  })
})

// Get current browser tab
async function getCurrentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  return tab
}

// Scrape current page content via content script
async function scrapePageContent() {
  const tab = await getCurrentTab()

  const url = tab?.url || ''
  if (url.startsWith('chrome://') || url.startsWith('chrome-extension://') || url.startsWith('about:')) {
    throw new Error('Cannot scan browser internal pages. Please navigate to a regular webpage.')
  }

  try {
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
    const msg = String(error.message || error)
    if (msg.includes('Receiving end does not exist') || msg.includes('Could not establish connection')) {
      throw new Error(
        'Content script not loaded on this page. Please refresh the page (F5) and try again.'
      )
    }
    console.error('Failed to scrape page content:', error)
    throw error
  }
}

// Collect form data
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

// Map frontend values to backend enum values
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

// Poll task status
async function pollTaskStatus(taskId, maxAttempts = 60, interval = 2000, expectTopics = true) {
  let attempts = 0
  
  while (attempts < maxAttempts) {
    try {
      const headers = await getHeaders()
      const response = await fetch(`${API_BASE_URL}/api/task/${taskId}`, {
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

// ========== Data collection ==========

// 1. Scan current page and ingest
async function handleScanPage() {
  if (!btnScanPage) return
  setIngestButtonState(btnScanPage, 'loading', 'Scanning...')

  try {
    const { text, title, url } = await scrapePageContent()
    
    if (!text || text.trim().length === 0) {
      throw new Error('Page content is empty, cannot save')
    }

    const estChunks = estimateChunks(text.length)
    if (estChunks > MAX_CHUNKS_PER_INGEST) {
      showNotice(
        `Page is very large (~${estChunks} chunks). ` +
        'Consider using "Print to PDF" and uploading via the PDF input. ' +
        `Only the first ${MAX_CHUNKS_PER_INGEST} chunks will be saved.`,
        'info', 8000
      )
    }
    if (chunkCount + estChunks > MAX_CHUNKS_PER_USER) {
      showNotice(
        `Knowledge base is near capacity (${chunkCount}/${MAX_CHUNKS_PER_USER}). ` +
        'Some content may be truncated.',
        'info', 6000
      )
    }

    const headers = await getHeaders()
    const sourceName = document.getElementById('courseName').value.trim() || title || url

    const response = await fetch(`${API_BASE_URL}/api/rag/ingest`, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({
        text: text,
        source: sourceName
      })
    })

    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Save failed'))
    }

    const data = await response.json()
    handleIngestResponse(data, btnScanPage, 'Scan & Add to KB')
  } catch (error) {
    showNotice(`Scan failed: ${error.message || error}`, 'error', 7000)
    console.error('Scan failed:', error)
  } finally {
    if (btnScanPage) {
      btnScanPage.disabled = false
    }
  }
}

// 2. Save pasted text
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
    const estChunks = estimateChunks(text.length)
    if (estChunks > MAX_CHUNKS_PER_INGEST) {
      showNotice(
        `Text is very large (~${estChunks} chunks). ` +
        `Only the first ${MAX_CHUNKS_PER_INGEST} chunks will be saved.`,
        'info', 8000
      )
    }
    if (chunkCount + estChunks > MAX_CHUNKS_PER_USER) {
      showNotice(
        `Knowledge base is near capacity (${chunkCount}/${MAX_CHUNKS_PER_USER}). ` +
        'Some content may be truncated.',
        'info', 6000
      )
    }

    const headers = await getHeaders()
    const sourceName = document.getElementById('courseName').value.trim() || 'User Paste'

    const response = await fetch(`${API_BASE_URL}/api/rag/ingest`, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({
        text: text,
        source: sourceName
      })
    })

    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Save failed'))
    }

    const data = await response.json()
    handleIngestResponse(data, btnSaveText, 'Save & Add to KB')
    textInput.value = ''
  } catch (error) {
    showNotice(`Save failed: ${error.message || error}`, 'error', 7000)
    console.error('Save failed:', error)
  } finally {
    btnSaveText.disabled = false
  }
}

// 3. Upload PDF
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
    if (chunkCount >= MAX_CHUNKS_PER_USER) {
      showNotice(
        `Knowledge base is full (${chunkCount}/${MAX_CHUNKS_PER_USER}). ` +
        'Clear some data before uploading.',
        'info', 6000
      )
    }

    const headers = await getHeadersForFile()
    const formData = new FormData()
    formData.append('file', file)

    const response = await fetch(`${API_BASE_URL}/api/rag/ingest/file`, {
      method: 'POST',
      headers: headers,
      body: formData
    })

    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Upload failed'))
    }

    const data = await response.json()
    handleIngestResponse(data, btnUploadPdf, 'Upload PDF & Add to KB')
    fileInput.value = ''
  } catch (error) {
    showNotice(`Upload failed: ${error.message || error}`, 'error', 7000)
    console.error('Upload failed:', error)
  } finally {
    btnUploadPdf.disabled = false
  }
}

// ========== Generation ==========

// Next step: generate outline
async function handleNextGenerate() {
  if (!btnNextGenerate) return
  
  // Adaptive time estimate based on indexing state + data size
  const secondsSinceIngest = lastIngestAt
    ? Math.max(0, (Date.now() - new Date(lastIngestAt).getTime()) / 1000)
    : Infinity
  const indexingEst = secondsSinceIngest < 60
    ? Math.round(Math.max(0, 30 - secondsSinceIngest))
    : 0
  const ragEst = 2
  const llmEst = Math.round(6 + Math.min(chunkCount * 0.1, 10))
  const estSeconds = indexingEst + ragEst + llmEst
  const showIndexingHintAt = indexingEst > 5 ? 5 : null

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
    if (showIndexingHintAt !== null && outlineElapsed === showIndexingHintAt) {
      showNotice(
        'Indexing your data — this may take a moment on first use. Please wait...',
        'info', 12000
      )
    }
  }, 1000)

  try {
    const formData = collectFormData()
    const headers = await getHeaders()

    const rawText = formData.syllabus || 'Generate outline from knowledge base based on all accumulated data'

    const response = await fetch(`${API_BASE_URL}/api/outline`, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({
        raw_text: rawText,
        user_context: formData.courseName || null,
        exam_type: mapExamType(formData.examType),
        ingest_batch_id: lastIngestBatchId || null
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
    
    const result = await pollTaskStatus(taskId)
    
    console.log('Analysis result:', result)
    if (result?.degraded_reason) {
      showNotice(
        'Your data is still being indexed. The outline was generated using available context ' +
        'and may be less specific. You can retry later for better results.',
        'warning', 10000
      )
      console.warn('Outline degraded:', result.degraded_reason)
    }
    if (!result || !result.topics) {
      throw new Error('Analysis result format error: missing topics field')
    }
    
    // Save analysis result (sync to window)
    currentOutlineData = result
    window.currentOutlineData = result
    
    renderOutlineList(result.topics)
    
    // Clear timer on success
    if (outlineTimerId) {
      clearInterval(outlineTimerId)
      outlineTimerId = null
    }
    if (estimateLabel) estimateLabel.textContent = ''
    
    showView('outline')
    // Reset button for next visit
    btnNextGenerate.textContent = 'Next: Generate Outline'
    
  } catch (error) {
    console.error('Generation failed:', error)
    if (outlineTimerId) {
      clearInterval(outlineTimerId)
      outlineTimerId = null
    }
    if (estimateLabel) {
      estimateLabel.textContent = ''
    }
    if (btnNextGenerate) {
      btnNextGenerate.disabled = false
      btnNextGenerate.textContent = 'Next: Generate Outline'
    }
    window.alert(`Failed to generate outline: ${error.message}`)
  } finally {
    // If still on form view (outline switch failed), ensure button is usable
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

// Render topic checkbox list
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

// Render extended topics list
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

// Add custom topic
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

// Collect selected topics
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

// Update add-topic button state
function updateAddButtonState() {
  const trimmed = customTopicInput.value.trim()
  btnAddCustomTopic.disabled = !trimmed || extendedTopics.some(t => t.title === trimmed)
}

// Handle back button
function handleBack() {
  showView('form')
  if (customTopicInput) {
    customTopicInput.value = ''
  }
  
  if (outlineTimerId) {
    clearInterval(outlineTimerId)
    outlineTimerId = null
  }
  
  // Reset button so user can re-generate outline
  if (btnNextGenerate) {
    btnNextGenerate.disabled = false
    btnNextGenerate.textContent = 'Next: Generate Outline'
  }
  
  if (estimateLabel) {
    estimateLabel.textContent = ''
  }
}

// Handle confirm & generate
async function handleConfirmGenerate() {
  if (!btnConfirmGenerate) return
  // Cheat sheet generation: RAG retrieval + LLM + PDF render + upload
  const estSeconds = Math.round(15 + Math.min(chunkCount * 0.2, 20))
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
    const response = await fetch(`${API_BASE_URL}/api/plugin/generate-final`, {
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
    
    // Extract project_id (may be nested at different levels)
    let projectId = null
    if (result && typeof result === 'object') {
      projectId = result.project_id || 
                  result.data?.project_id || 
                  (result.data && result.data.project_id)
      
      console.log('Extracted project_id:', projectId)
    }
    
    if (!projectId) {
      console.error('Unable to find project_id, full result:', JSON.stringify(result, null, 2))
      throw new Error('Generation result format error: project_id not found. Please check console for details.')
    }
    
    currentProjectId = projectId

    // Request PDF generation
    if (btnConfirmGenerate) {
      btnConfirmGenerate.textContent = 'Generating PDF...'
    }
    const pdfHeaders = await getHeaders()
    const pdfResponse = await fetch(
      `${API_BASE_URL}/api/plugin/download-cheat-sheet/${currentProjectId}`,
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
    
    if (!downloadLink) {
      throw new Error('Cannot find download link element')
    }
    if (!resultArea) {
      throw new Error('Cannot find result area element')
    }
    
    downloadLink.href = pdfUrl
    downloadLink.download = `cheat-sheet-${currentProjectId}.pdf`
    downloadLink.textContent = 'Download Generated Cheat Sheet (PDF)'
    
    // Clear timer, hide outline, show result area
    if (contentTimerId) {
      clearInterval(contentTimerId)
      contentTimerId = null
    }
    if (outlineEstimateLabel) outlineEstimateLabel.textContent = ''
    
    if (viewOutline) viewOutline.style.display = 'none'
    if (viewForm) viewForm.style.display = 'none'
    
    resultArea.style.display = 'block'
    
    // Clear draft after successful generation
    if (typeof formPersistence !== 'undefined' && formPersistence.clearDraft) {
      formPersistence.clearDraft()
    }
    
    console.log('✅ PDF generated successfully, result area displayed')
    
  } catch (error) {
    console.error('Generation failed:', error)
    window.alert(`Generation failed: ${error.message || error.toString()}`)
    if (btnConfirmGenerate) {
      btnConfirmGenerate.disabled = false
      btnConfirmGenerate.textContent = 'Submit'
    }
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

// Result page: back to home (form view)
function handleBackHome() {
  if (resultArea) {
    resultArea.style.display = 'none'
  }
  if (viewForm) {
    viewForm.style.display = 'block'
  }
  if (viewOutline) {
    viewOutline.style.display = 'none'
  }

  // Reset generation-related buttons and labels
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

  // Revoke PDF blob URL to prevent memory leak
  if (downloadLink && downloadLink.href && downloadLink.href.startsWith('blob:')) {
    try {
      URL.revokeObjectURL(downloadLink.href)
    } catch (e) {
      console.warn('Failed to revoke object URL:', e)
    }
    downloadLink.href = '#'
  }
}

// Event bindings
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

// Custom topic event bindings
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

// Page load initialization — set default view (persistence module may override)
showView('form')

// Restore chunk count & last ingest info from local storage, then sync from server
chrome.storage.local.get(['chunk_count', 'last_ingest_batch_id', 'last_ingest_at'], async (result) => {
  if (typeof result?.chunk_count === 'number') {
    chunkCount = result.chunk_count
    updateChunkCounter()
  }
  if (typeof result?.last_ingest_batch_id === 'string' && result.last_ingest_batch_id) {
    lastIngestBatchId = result.last_ingest_batch_id
  }
  if (typeof result?.last_ingest_at === 'string' && result.last_ingest_at) {
    lastIngestAt = result.last_ingest_at
  }
  // Sync latest chunk count from server (overrides local cache)
  await syncChunkCountFromServer()
})
buildHeaderSummary()

// Initialize formPersistence here (avoids inline script CSP issues in popup.html)
if (typeof formPersistence !== 'undefined' && formPersistence.init) {
  formPersistence.init().catch((error) => {
    showNotice(`Form init failed: ${error.message || error}`, 'error', 7000)
    console.error('Form persistence init failed:', error)
  })
}

// Header accordion: click summary to expand
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

// Update summary in real time on form field changes (even when collapsed)
const courseNameInput = document.getElementById('courseName')
if (courseNameInput) {
  courseNameInput.addEventListener('input', buildHeaderSummary)
}
document.querySelectorAll('input[name="examType"], input[name="pageLimit"]').forEach((el) => {
  el.addEventListener('change', buildHeaderSummary)
})
