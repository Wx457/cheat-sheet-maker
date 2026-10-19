/**
 * popup.js — Cheat Sheet Maker Extension (Redesigned for Webapp Flow)
 *
 * 新流程（与旧流程的区别）：
 *   旧: ingest → outline review → confirm → generate-final → PDF download link
 *   新: ingest → "Open Editor →" → chrome.tabs.create(webapp /editor?params)
 *       webapp 负责 SSE 流式渲染 + 卡片编辑 + PDF 导出
 *
 * 插件只负责：
 *   1. 数据采集（Scan / Paste / PDF → POST /api/rag/ingest）
 *   2. 参数配置（level, archetype, pageLimit, examType）
 *   3. 打开 Webapp 编辑器页面（携带 URL 参数）
 */

'use strict'

// ─────────────────────────────────────────────────────────────────────────────
// 常量
// ─────────────────────────────────────────────────────────────────────────────

const ESTIMATED_CHARS_PER_CHUNK = 450
const MAX_CHUNKS_PER_INGEST = 200
const MAX_CHUNKS_PER_USER = 500

// ─────────────────────────────────────────────────────────────────────────────
// 运行时状态
// ─────────────────────────────────────────────────────────────────────────────

let chunkCount = 0
let lastIngestBatchId = null
let lastIngestAt = null

// Outline page state
let outlineTopics = []       // [{title: string, checked: boolean}]
let outlinePollTimer = null

// ─────────────────────────────────────────────────────────────────────────────
// 工具函数
// ─────────────────────────────────────────────────────────────────────────────

function estimateChunks(charCount) {
  return Math.ceil(charCount / ESTIMATED_CHARS_PER_CHUNK)
}

// ─────────────────────────────────────────────────────────────────────────────
// User ID 管理（每次安装生成一次，存入 chrome.storage.local）
// ─────────────────────────────────────────────────────────────────────────────

async function getOrCreateUserId() {
  return new Promise((resolve, reject) => {
    chrome.storage.local.get(['user_id'], (result) => {
      if (chrome.runtime.lastError) { reject(new Error(chrome.runtime.lastError.message)); return }

      if (result.user_id) {
        resolve(result.user_id)
      } else {
        const newId = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
          const r = Math.random() * 16 | 0
          return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16)
        })
        chrome.storage.local.set({ user_id: newId }, () => {
          if (chrome.runtime.lastError) { reject(new Error(chrome.runtime.lastError.message)); return }
          resolve(newId)
        })
      }
    })
  })
}

async function getHeaders() {
  const userId = await getOrCreateUserId()
  return { 'Content-Type': 'application/json', 'X-User-ID': userId }
}

async function getHeadersForFile() {
  const userId = await getOrCreateUserId()
  return { 'X-User-ID': userId }
}

// ─────────────────────────────────────────────────────────────────────────────
// Notification banner
// ─────────────────────────────────────────────────────────────────────────────

let noticeTimerId = null

function showNotice(message, type = 'error', autoHideMs = 6000) {
  if (!message) return
  let notice = document.getElementById('runtime-notice')
  if (!notice) {
    notice = document.createElement('div')
    notice.id = 'runtime-notice'
    document.body.appendChild(notice)
  }

  const styleMap = {
    error:   { background: '#fee2e2', border: '#fecaca', color: '#991b1b' },
    warning: { background: '#fff7ed', border: '#fed7aa', color: '#9a3412' },
    info:    { background: '#f3e8ff', border: '#d8b4fe', color: '#6b21a8' },
    success: { background: '#dcfce7', border: '#86efac', color: '#166534' },
  }
  const style = styleMap[type] || styleMap.error
  Object.assign(notice.style, {
    position: 'fixed', top: '10px', left: '10px', right: '10px',
    padding: '8px 10px', borderRadius: '8px', fontSize: '12px', lineHeight: '1.4',
    zIndex: '9999', boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
    backgroundColor: style.background, border: `1px solid ${style.border}`,
    color: style.color, display: 'block',
  })
  notice.textContent = message

  if (noticeTimerId) clearTimeout(noticeTimerId)
  if (autoHideMs > 0) {
    noticeTimerId = setTimeout(() => {
      const n = document.getElementById('runtime-notice')
      if (n) n.style.display = 'none'
    }, autoHideMs)
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Confirm dialog
// ─────────────────────────────────────────────────────────────────────────────

function showConfirmDialog(title, message, confirmText = 'Confirm', cancelText = 'Cancel') {
  return new Promise((resolve) => {
    const existing = document.getElementById('runtime-confirm-overlay')
    if (existing) existing.remove()

    const overlay = document.createElement('div')
    overlay.id = 'runtime-confirm-overlay'
    Object.assign(overlay.style, {
      position: 'fixed', inset: '0', background: 'rgba(15,23,42,0.45)',
      zIndex: '10000', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '12px',
    })

    const dialog = document.createElement('div')
    Object.assign(dialog.style, {
      width: '100%', maxWidth: '360px', background: '#fff', border: '1px solid #e5e7eb',
      borderRadius: '10px', boxShadow: '0 10px 30px rgba(0,0,0,0.2)', padding: '14px',
    })

    const titleEl = document.createElement('div')
    Object.assign(titleEl.style, { fontSize: '14px', fontWeight: '700', color: '#0f172a', marginBottom: '8px' })
    titleEl.textContent = title

    const messageEl = document.createElement('div')
    Object.assign(messageEl.style, { fontSize: '12px', lineHeight: '1.5', color: '#334155', marginBottom: '12px' })
    messageEl.textContent = message

    const actions = document.createElement('div')
    Object.assign(actions.style, { display: 'flex', justifyContent: 'flex-end', gap: '8px' })

    function makeBtn(text, bg, color, border = 'none') {
      const btn = document.createElement('button')
      btn.textContent = text
      Object.assign(btn.style, {
        border, background: bg, color, borderRadius: '8px',
        padding: '6px 10px', fontSize: '12px', fontWeight: '600', cursor: 'pointer',
      })
      return btn
    }

    const cancelBtn = makeBtn(cancelText, '#fff', '#334155', '1px solid #cbd5e1')
    const confirmBtn = makeBtn(confirmText, '#ef4444', '#fff')

    let resolved = false
    const cleanup = (result) => {
      if (resolved) return
      resolved = true
      document.removeEventListener('keydown', onKeyDown)
      overlay.remove()
      resolve(result)
    }
    const onKeyDown = (e) => {
      if (e.key === 'Escape') cleanup(false)
      if (e.key === 'Enter') cleanup(true)
    }
    document.addEventListener('keydown', onKeyDown)
    cancelBtn.addEventListener('click', () => cleanup(false))
    confirmBtn.addEventListener('click', () => cleanup(true))
    overlay.addEventListener('click', (e) => { if (e.target === overlay) cleanup(false) })

    actions.append(cancelBtn, confirmBtn)
    dialog.append(titleEl, messageEl, actions)
    overlay.appendChild(dialog)
    document.body.appendChild(overlay)
    confirmBtn.focus()
  })
}

// ─────────────────────────────────────────────────────────────────────────────
// Ingest helper
// ─────────────────────────────────────────────────────────────────────────────

async function parseErrorMessage(response, fallbackMessage) {
  const fallback = `${fallbackMessage} (HTTP ${response.status})`
  const errorData = await response.json().catch(() => null)
  if (!errorData) return fallback
  const detail = errorData.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail?.message) return detail.message
  if (errorData.message) return errorData.message
  return fallback
}

function handleIngestResponse(data, button, idleLabel) {
  const accepted = Number(data.chunks_count || 0)
  chunkCount += accepted
  persistLastIngestInfo(data.ingest_batch_id, data.ingest_at)
  updateChunkCounter()
  persistChunkCount()
  autoCollapseHeaderIfNeeded()
  updateLaunchButton()   // 有 chunks 后才允许打开编辑器

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

function setIngestButtonState(button, state, label) {
  if (!button) return
  if (label) button.textContent = label
  button.disabled = (state === 'loading' || state === 'success')
}

function updateChunkCounter() {
  const el = document.getElementById('chunkCounter')
  if (el) el.textContent = `📚 ${chunkCount} Chunks`
}

function persistChunkCount() {
  chrome.storage.local.set({ chunk_count: chunkCount }).catch(console.error)
}

function persistLastIngestInfo(ingestBatchId, ingestAt) {
  if (!ingestBatchId) return
  lastIngestBatchId = ingestBatchId
  lastIngestAt = ingestAt || null
  chrome.storage.local.set({
    last_ingest_batch_id: lastIngestBatchId,
    last_ingest_at: lastIngestAt,
  }).catch(console.error)
}

// ─────────────────────────────────────────────────────────────────────────────
// Launch button state（仅在有 chunks 时可用）
// ─────────────────────────────────────────────────────────────────────────────

function updateLaunchButton() {
  const btn = document.getElementById('btnNextToOutline')
  if (!btn) return
  btn.disabled = chunkCount === 0
}

// ─────────────────────────────────────────────────────────────────────────────
// Header accordion
// ─────────────────────────────────────────────────────────────────────────────

let headerCollapsed = false

function collectFormData() {
  const courseName = document.getElementById('courseName')?.value.trim() || ''
  const educationLevel = document.querySelector('input[name="educationLevel"]:checked')?.value || 'Undergraduate'
  const examType = document.querySelector('input[name="examType"]:checked')?.value || 'Final'
  const pageLimit = document.querySelector('input[name="pageLimit"]:checked')?.value || '1 page'
  const archetype = document.getElementById('archetypeSelect')?.value || 'general'
  return { courseName, educationLevel, examType, pageLimit, archetype }
}

function buildHeaderSummary() {
  const el = document.getElementById('headerSummaryMain')
  if (!el) return
  const { courseName, examType, pageLimit } = collectFormData()
  const title = courseName || 'Course not filled'
  el.textContent = `${title} · ${examType} · ${pageLimit}`
}

function setHeaderCollapsed(collapsed) {
  headerCollapsed = collapsed
  const accordion = document.getElementById('headerAccordion')
  const details = document.getElementById('headerDetails')
  const summary = document.getElementById('headerSummary')
  const toggleBtn = document.getElementById('toggleHeaderBtn')
  if (!accordion || !details || !summary) return

  accordion.classList.toggle('collapsed', collapsed)
  details.classList.toggle('collapsed', collapsed)
  summary.style.display = collapsed ? 'flex' : 'none'
  if (toggleBtn) toggleBtn.textContent = collapsed ? 'Expand' : 'Collapse'
  buildHeaderSummary()
}

function autoCollapseHeaderIfNeeded() {
  if (chunkCount > 0 && !headerCollapsed) setHeaderCollapsed(true)
}

// ─────────────────────────────────────────────────────────────────────────────
// Enum mappers（frontend label → backend enum value）
// ─────────────────────────────────────────────────────────────────────────────

const LEVEL_MAP = {
  'Undergraduate': 'undergraduate',
  'Graduate':      'graduate',
  'High School':   'high_school',
}
const EXAM_MAP = { 'Quiz': 'quiz', 'Midterm': 'midterm', 'Final': 'final' }
const PAGE_MAP = {
  '1 side':    '1_side',
  '1 page':    '1_page',
  '2 pages':   '2_pages',
  'Unlimited': 'unlimited',
}

// ─────────────────────────────────────────────────────────────────────────────
// Chunk count sync from server
// ─────────────────────────────────────────────────────────────────────────────

async function syncChunkCountFromServer() {
  const API_BASE_URL = window.API_BASE_URL || 'http://localhost:8000'
  try {
    const headers = await getHeaders()
    const res = await fetch(`${API_BASE_URL}/api/rag/chunks/count`, { method: 'GET', headers })
    if (res.ok) {
      const data = await res.json()
      if (data.status === 'success' && typeof data.chunks_count === 'number') {
        chunkCount = data.chunks_count
        updateChunkCounter()
        persistChunkCount()
        setHeaderCollapsed(chunkCount > 0)
        updateLaunchButton()
      }
    } else {
      showNotice('Could not sync chunk count — showing local cache.', 'info', 4000)
    }
  } catch {
    showNotice('Backend unreachable — showing local cache.', 'info', 4000)
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Page navigation (form ↔ outline)
// ─────────────────────────────────────────────────────────────────────────────

function showFormPage() {
  document.getElementById('view-form').style.display = ''
  document.getElementById('view-outline').style.display = 'none'
  if (outlinePollTimer) { clearInterval(outlinePollTimer); outlinePollTimer = null }
}

function showOutlinePage() {
  document.getElementById('view-form').style.display = 'none'
  document.getElementById('view-outline').style.display = 'flex'
}

// ─────────────────────────────────────────────────────────────────────────────
// Outline state helpers
// ─────────────────────────────────────────────────────────────────────────────

function showOutlineLoading() {
  document.getElementById('outlineLoading').style.display = 'flex'
  document.getElementById('outlineContent').style.display = 'none'
  document.getElementById('outlineError').style.display = 'none'
  document.getElementById('btnOpenEditorFromOutline').disabled = true
}

function showOutlineContent() {
  document.getElementById('outlineLoading').style.display = 'none'
  document.getElementById('outlineContent').style.display = 'block'
  document.getElementById('outlineError').style.display = 'none'
  renderTopicList()
  document.getElementById('btnOpenEditorFromOutline').disabled =
    outlineTopics.filter(t => t.checked).length === 0
}

function showOutlineError(msg) {
  document.getElementById('outlineLoading').style.display = 'none'
  document.getElementById('outlineContent').style.display = 'none'
  document.getElementById('outlineError').style.display = 'block'
  document.getElementById('outlineErrorMsg').textContent = msg || 'Failed to generate outline.'
}

// ─────────────────────────────────────────────────────────────────────────────
// Outline polling
// ─────────────────────────────────────────────────────────────────────────────

async function pollForOutlineTopics(taskId) {
  const API_BASE_URL = window.API_BASE_URL || 'http://localhost:8000'
  if (outlinePollTimer) clearInterval(outlinePollTimer)

  outlinePollTimer = setInterval(async () => {
    try {
      const headers = await getHeaders()
      const res = await fetch(`${API_BASE_URL}/api/task/${taskId}`, { method: 'GET', headers })
      if (!res.ok) throw new Error(`Task check failed (HTTP ${res.status})`)
      const data = await res.json()

      if (data.status === 'complete' || data.status === 'completed') {
        clearInterval(outlinePollTimer); outlinePollTimer = null

        // worker returns {"success": bool, "data": OutlineResponse}
        // task.py passes job_result as-is, so result = {"success":..., "data":{topics:[...]}}
        const workerResult = data.result || {}
        if (workerResult.success === false) {
          showOutlineError(workerResult.error || 'Outline generation failed.')
          return
        }
        const outline = workerResult.data || workerResult   // unwrap data wrapper if present
        const topics = outline.topics || []
        outlineTopics = topics.map(t => ({ title: t.title, checked: true }))
        showOutlineContent()
      } else if (data.status === 'failed') {
        clearInterval(outlinePollTimer); outlinePollTimer = null
        showOutlineError(data.error || 'Outline generation failed.')
      }
    } catch (err) {
      clearInterval(outlinePollTimer); outlinePollTimer = null
      showOutlineError(err.message || 'Failed to check outline status.')
    }
  }, 2000)
}

// ─────────────────────────────────────────────────────────────────────────────
// Topic list rendering & editing
// ─────────────────────────────────────────────────────────────────────────────

function renderTopicList() {
  const list = document.getElementById('topicList')
  if (!list) return
  list.innerHTML = ''

  outlineTopics.forEach((topic, idx) => {
    const row = document.createElement('div')
    row.className = 'topic-row'

    const checkbox = document.createElement('input')
    checkbox.type = 'checkbox'
    checkbox.className = 'topic-check'
    checkbox.checked = topic.checked
    checkbox.addEventListener('change', () => {
      outlineTopics[idx].checked = checkbox.checked
      document.getElementById('btnOpenEditorFromOutline').disabled =
        outlineTopics.filter(t => t.checked).length === 0
    })

    const titleSpan = document.createElement('span')
    titleSpan.className = 'topic-title-text'
    titleSpan.textContent = topic.title
    titleSpan.title = 'Click to edit'
    titleSpan.addEventListener('click', () => startEditTopic(idx, row, titleSpan))

    const deleteBtn = document.createElement('button')
    deleteBtn.className = 'topic-action-btn'
    deleteBtn.textContent = '✕'
    deleteBtn.title = 'Remove topic'
    deleteBtn.addEventListener('click', () => {
      outlineTopics.splice(idx, 1)
      renderTopicList()
      document.getElementById('btnOpenEditorFromOutline').disabled =
        outlineTopics.filter(t => t.checked).length === 0
    })

    row.append(checkbox, titleSpan, deleteBtn)
    list.appendChild(row)
  })
}

function startEditTopic(idx, row, titleSpan) {
  row.classList.add('editing')
  const input = document.createElement('input')
  input.type = 'text'
  input.className = 'topic-edit-input'
  input.value = outlineTopics[idx].title

  const saveEdit = () => {
    const val = input.value.trim()
    if (val) outlineTopics[idx].title = val
    renderTopicList()
  }
  input.addEventListener('blur', saveEdit)
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); input.blur() }
    if (e.key === 'Escape') { renderTopicList() }
  })

  titleSpan.replaceWith(input)
  input.focus(); input.select()
}

function handleAddTopic() {
  const input = document.getElementById('addTopicInput')
  if (!input) return
  const title = input.value.trim()
  if (!title) return
  outlineTopics.push({ title, checked: true })
  input.value = ''
  renderTopicList()
  document.getElementById('btnOpenEditorFromOutline').disabled = false
}

// ─────────────────────────────────────────────────────────────────────────────
// ★ handleNextToOutline — form page "Review Topics →" button
// Calls POST /api/outline → shows outline page → starts polling
// ─────────────────────────────────────────────────────────────────────────────

async function handleNextToOutline() {
  if (chunkCount === 0) {
    showNotice('Please add content to the knowledge base first (Scan / Paste / PDF).', 'warning', 5000)
    return
  }

  const API_BASE_URL = window.API_BASE_URL || 'http://localhost:8000'
  const formData = collectFormData()

  showOutlinePage()
  showOutlineLoading()
  outlineTopics = []

  try {
    const headers = await getHeaders()
    const body = {
      academic_level: LEVEL_MAP[formData.educationLevel] || 'undergraduate',
      page_limit:     PAGE_MAP[formData.pageLimit]       || '1_page',
      archetype:      formData.archetype,
    }
    if (formData.courseName) body.user_context = formData.courseName
    if (formData.examType)   body.exam_type    = EXAM_MAP[formData.examType] || undefined

    const res = await fetch(`${API_BASE_URL}/api/outline`, {
      method: 'POST', headers, body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(await parseErrorMessage(res, 'Outline request failed'))
    const data = await res.json()
    if (!data.task_id) throw new Error('No task ID returned from outline API')
    pollForOutlineTopics(data.task_id)
  } catch (err) {
    showOutlineError(err.message || 'Failed to start outline generation.')
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// ★ handleOpenEditorFromOutline — outline page "Open Editor →" button
// Collects checked topics → builds URL → chrome.tabs.create
// ─────────────────────────────────────────────────────────────────────────────

async function handleOpenEditorFromOutline() {
  const checkedTopics = outlineTopics.filter(t => t.checked).map(t => t.title)
  if (checkedTopics.length === 0) {
    showNotice('Please select at least one topic.', 'warning', 3000)
    return
  }

  const WEBAPP_URL = window.WEBAPP_URL || 'http://localhost:3000'
  const formData = collectFormData()
  const userId = await getOrCreateUserId()

  const params = new URLSearchParams()
  params.set('userId',    userId)
  params.set('level',     LEVEL_MAP[formData.educationLevel] || 'undergraduate')
  params.set('pageLimit', PAGE_MAP[formData.pageLimit]       || '1_page')
  params.set('archetype', formData.archetype)
  params.set('topics',    JSON.stringify(checkedTopics))
  if (formData.courseName) params.set('context', formData.courseName)
  if (formData.examType)   params.set('examType', EXAM_MAP[formData.examType] || '')

  const editorUrl = `${WEBAPP_URL}/editor?${params.toString()}`
  console.log('[Outline → Launch] Opening webapp:', editorUrl)

  const btn = document.getElementById('btnOpenEditorFromOutline')
  if (btn) { btn.textContent = 'Opened! ✓'; btn.classList.add('launched'); btn.disabled = true }

  chrome.tabs.create({ url: editorUrl })

  setTimeout(() => {
    if (btn) {
      btn.textContent = 'Open Editor →'
      btn.classList.remove('launched')
      btn.disabled = checkedTopics.length === 0
    }
  }, 3000)
}

// ─────────────────────────────────────────────────────────────────────────────
// Knowledge base clear
// ─────────────────────────────────────────────────────────────────────────────

async function handleResetKnowledgeBase() {
  const btn = document.getElementById('btnReset')
  if (!btn) return
  const API_BASE_URL = window.API_BASE_URL || 'http://localhost:8000'

  const confirmed = await showConfirmDialog(
    'Clear knowledge base?',
    'This will permanently delete all ingested content. This cannot be undone.',
    'Clear', 'Cancel'
  )
  if (!confirmed) return

  btn.disabled = true
  try {
    const headers = await getHeaders()
    // DELETE /api/rag/chunks — 用户级操作，只删当前用户的向量数据
    const res = await fetch(`${API_BASE_URL}/api/rag/chunks`, { method: 'DELETE', headers })
    if (!res.ok) throw new Error(await parseErrorMessage(res, 'Failed to clear'))

    chunkCount = 0
    lastIngestBatchId = null
    lastIngestAt = null
    updateChunkCounter()
    persistChunkCount()
    chrome.storage.local.remove(['last_ingest_batch_id', 'last_ingest_at'])
    setHeaderCollapsed(false)
    updateLaunchButton()
    showNotice('Knowledge base cleared!', 'success', 2200)
  } catch (err) {
    showNotice(`Clear failed: ${err.message || err}`, 'error', 7000)
  } finally {
    btn.disabled = false
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// getCurrentTab / scrapePageContent（content.js 通信）
// ─────────────────────────────────────────────────────────────────────────────

async function getCurrentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  return tab
}

async function scrapePageContent() {
  const tab = await getCurrentTab()
  const url = tab?.url || ''
  if (url.startsWith('chrome://') || url.startsWith('chrome-extension://') || url.startsWith('about:')) {
    throw new Error('Cannot scan browser internal pages. Please navigate to a regular webpage.')
  }
  try {
    const response = await chrome.tabs.sendMessage(tab.id, { action: 'scrape' })
    if (response?.success && response.text && response.title) {
      return { text: response.text, title: response.title, url: tab.url }
    }
    throw new Error(response?.error || 'Failed to get page content')
  } catch (err) {
    const msg = String(err.message || err)
    if (msg.includes('Receiving end does not exist') || msg.includes('Could not establish connection')) {
      throw new Error('Content script not loaded. Please refresh the page (F5) and try again.')
    }
    throw err
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Ingest handlers
// ─────────────────────────────────────────────────────────────────────────────

async function handleScanPage() {
  const btn = document.getElementById('btnScanPage')
  if (!btn) return
  const API_BASE_URL = window.API_BASE_URL || 'http://localhost:8000'

  setIngestButtonState(btn, 'loading', 'Scanning…')
  try {
    const { text, title, url } = await scrapePageContent()
    if (!text?.trim()) throw new Error('Page content is empty, cannot save')

    const estChunks = estimateChunks(text.length)
    if (estChunks > MAX_CHUNKS_PER_INGEST) {
      showNotice(
        `Page is very large (~${estChunks} chunks). Only the first ${MAX_CHUNKS_PER_INGEST} will be saved.`,
        'info', 8000
      )
    }
    if (chunkCount + estChunks > MAX_CHUNKS_PER_USER) {
      showNotice(`Knowledge base is near capacity (${chunkCount}/${MAX_CHUNKS_PER_USER}).`, 'info', 6000)
    }

    const headers = await getHeaders()
    const sourceName = document.getElementById('courseName')?.value.trim() || title || url
    const res = await fetch(`${API_BASE_URL}/api/rag/ingest`, {
      method: 'POST', headers,
      body: JSON.stringify({ text, source: sourceName }),
    })
    if (!res.ok) throw new Error(await parseErrorMessage(res, 'Save failed'))
    handleIngestResponse(await res.json(), btn, 'Scan & Add to KB')
  } catch (err) {
    showNotice(`Scan failed: ${err.message || err}`, 'error', 7000)
    setIngestButtonState(btn, 'idle', 'Scan & Add to KB')
  }
}

async function handleSaveText() {
  const btn = document.getElementById('btnSaveText')
  const textInput = document.getElementById('pasteTextInput')
  if (!btn || !textInput) return
  const API_BASE_URL = window.API_BASE_URL || 'http://localhost:8000'

  const text = textInput.value.trim()
  if (!text) { showNotice('Please enter some text.', 'warning', 3000); return }

  setIngestButtonState(btn, 'loading', 'Saving…')
  try {
    const estChunks = estimateChunks(text.length)
    if (estChunks > MAX_CHUNKS_PER_INGEST) {
      showNotice(`Text is very large (~${estChunks} chunks). Only the first ${MAX_CHUNKS_PER_INGEST} will be saved.`, 'info', 8000)
    }
    if (chunkCount + estChunks > MAX_CHUNKS_PER_USER) {
      showNotice(`Knowledge base is near capacity (${chunkCount}/${MAX_CHUNKS_PER_USER}).`, 'info', 6000)
    }

    const headers = await getHeaders()
    const sourceName = document.getElementById('courseName')?.value.trim() || 'User Paste'
    const res = await fetch(`${API_BASE_URL}/api/rag/ingest`, {
      method: 'POST', headers,
      body: JSON.stringify({ text, source: sourceName }),
    })
    if (!res.ok) throw new Error(await parseErrorMessage(res, 'Save failed'))
    handleIngestResponse(await res.json(), btn, 'Save & Add to KB')
    textInput.value = ''
  } catch (err) {
    showNotice(`Save failed: ${err.message || err}`, 'error', 7000)
    setIngestButtonState(btn, 'idle', 'Save & Add to KB')
  }
}

async function handleUploadPdf() {
  const btn = document.getElementById('btnUploadPdf')
  const fileInput = document.getElementById('pdfFileInput')
  if (!btn || !fileInput) return
  const API_BASE_URL = window.API_BASE_URL || 'http://localhost:8000'

  const file = fileInput.files[0]
  if (!file) { showNotice('Please select a PDF file.', 'warning', 3000); return }
  if (!file.name.toLowerCase().endsWith('.pdf')) { showNotice('Only PDF format is supported.', 'warning', 3000); return }

  setIngestButtonState(btn, 'loading', 'Uploading…')
  try {
    if (chunkCount >= MAX_CHUNKS_PER_USER) {
      showNotice(`Knowledge base is full (${chunkCount}/${MAX_CHUNKS_PER_USER}). Clear some data first.`, 'info', 6000)
    }
    const headers = await getHeadersForFile()
    const formData = new FormData()
    formData.append('file', file)
    const res = await fetch(`${API_BASE_URL}/api/rag/ingest/file`, { method: 'POST', headers, body: formData })
    if (!res.ok) throw new Error(await parseErrorMessage(res, 'Upload failed'))
    handleIngestResponse(await res.json(), btn, 'Upload PDF & Add to KB')
    fileInput.value = ''
  } catch (err) {
    showNotice(`Upload failed: ${err.message || err}`, 'error', 7000)
    setIngestButtonState(btn, 'idle', 'Upload PDF & Add to KB')
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab switching
// ─────────────────────────────────────────────────────────────────────────────

function initTabs() {
  const tabs = document.querySelectorAll('.tab')
  const tabContents = document.querySelectorAll('.tab-content')
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'))
      tab.classList.add('active')
      tabContents.forEach(c => {
        c.classList.remove('active')
        if (c.id === `tab-${tab.dataset.tab}`) c.classList.add('active')
      })
    })
  })
}

// ─────────────────────────────────────────────────────────────────────────────
// Initialization
// ─────────────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Tabs
  initTabs()

  // Event bindings
  document.getElementById('btnScanPage')?.addEventListener('click', handleScanPage)
  document.getElementById('btnSaveText')?.addEventListener('click', handleSaveText)
  document.getElementById('btnUploadPdf')?.addEventListener('click', handleUploadPdf)
  document.getElementById('btnReset')?.addEventListener('click', handleResetKnowledgeBase)
  document.getElementById('btnNextToOutline')?.addEventListener('click', handleNextToOutline)

  // Outline page
  document.getElementById('btnBackToForm')?.addEventListener('click', showFormPage)
  document.getElementById('btnAddTopic')?.addEventListener('click', handleAddTopic)
  document.getElementById('addTopicInput')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); handleAddTopic() }
  })
  document.getElementById('btnOpenEditorFromOutline')?.addEventListener('click', handleOpenEditorFromOutline)
  document.getElementById('btnOutlineRetry')?.addEventListener('click', handleNextToOutline)

  // Header accordion
  document.getElementById('headerSummary')?.addEventListener('click', () => {
    setHeaderCollapsed(false)
    document.getElementById('courseName')?.focus()
  })
  document.getElementById('toggleHeaderBtn')?.addEventListener('click', () => {
    setHeaderCollapsed(!headerCollapsed)
  })

  // Live summary update
  document.getElementById('courseName')?.addEventListener('input', buildHeaderSummary)
  document.querySelectorAll('input[name="examType"], input[name="pageLimit"]').forEach(el => {
    el.addEventListener('change', buildHeaderSummary)
  })

  // Restore state from local storage, then sync from server
  chrome.storage.local.get(
    ['chunk_count', 'last_ingest_batch_id', 'last_ingest_at'],
    async (result) => {
      if (typeof result?.chunk_count === 'number') {
        chunkCount = result.chunk_count
        updateChunkCounter()
      }
      lastIngestBatchId = result?.last_ingest_batch_id || null
      lastIngestAt = result?.last_ingest_at || null

      await syncChunkCountFromServer()
    }
  )

  buildHeaderSummary()
  updateLaunchButton()

  // Form persistence (optional module)
  if (typeof formPersistence !== 'undefined' && formPersistence.init) {
    formPersistence.init().catch(err => {
      showNotice(`Form init failed: ${err.message || err}`, 'error', 7000)
    })
  }
})
