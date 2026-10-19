/**
 * content.js — 页面内容抓取（双保险策略）
 *
 * 策略 A：平台感知选择器配置表
 *   - 为已知 AI 聊天平台维护语义优先的选择器（data 属性 > ARIA > class）
 *   - 新平台只需在 PLATFORM_CONFIGS 中加一行
 *
 * 策略 B：TreeWalker API — 完全选择器无关的通用 fallback
 *   - 遍历所有可见文本节点，跳过 nav/header/footer/script 等噪音区域
 *   - 任何网页都能工作，零维护成本
 *
 * 执行流程：
 *   1. 匹配当前 hostname → 取 scrollSelector 和 contentSelectors
 *   2. 尝试滚动 + 按 contentSelectors 收集（策略 A）
 *   3. 若策略 A 无结果 → TreeWalker 全文提取（策略 B）
 *   4. 若 B 也无结果 → document.body.innerText 兜底
 */

'use strict'

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

// ─────────────────────────────────────────────────────────────────────────────
// 策略 A：平台配置表
// contentSelectors 按优先级降序排列：语义属性 > 测试属性 > CSS class
// ─────────────────────────────────────────────────────────────────────────────

const PLATFORM_CONFIGS = [
  {
    // ChatGPT (chat.openai.com)
    // scrollSelectors: 有序数组，逐一尝试直到找到可滚动元素
    // 新 UI(2025): data-app-shell-* 属性替代了旧的 [data-scroll-root]
    hostMatch: 'chat.openai.com',
    scrollSelectors: [
      '[data-app-shell-focus-area="main"]',          // 新 UI 焦点区（最内、最可能滚动）
      '[data-app-shell-main-content-layout]',        // 新 UI 内容视口
      '[data-app-shell-thread-edge-divider]',        // 新 UI 会话帧
      '[data-app-shell-main-surface="browser"]',     // 新 UI 主体
      '[data-scroll-root]',                          // 旧 UI 兜底（保留兼容）
    ],
    contentSelectors: [
      // ── 最稳定：语义数据属性 ──────────────────────────────
      '[data-message-author-role="assistant"]',      // 消息角色属性（新旧 UI 均有）
      'article[data-testid]',                        // 对话 turn（article 语义元素）
      '[data-testid*="conversation-turn"]',          // 测试属性（次稳定）
      // ── 次稳定：class 包含语义词（class 名哈希变但词根不变）
      '[class*="markdown"]',
      '[class*="Markdown"]',
      '[class*="prose"]',
      // ── 兜底 ─────────────────────────────────────────────
      '.markdown', '.prose',
    ],
    wrapLabel: 'ChatGPT Message',
  },
  {
    // Claude (claude.ai)
    hostMatch: 'claude.ai',
    scrollSelectors: ['[data-is-streaming]', 'main', '[role="main"]'],
    contentSelectors: [
      '.prose',
      '[class*="prose"]',
      '[class*="message-content"]',
      '[class*="markdown"]',
    ],
    wrapLabel: 'Claude Message',
  },
  {
    // Gemini (gemini.google.com)
    hostMatch: 'gemini.google.com',
    scrollSelectors: ['[role="main"]', 'main'],
    contentSelectors: [
      'message-content',      // Web Component 元素名
      'model-response',
      '[class*="response"]',
      '[class*="markdown"]',
      '.markdown',
    ],
    wrapLabel: 'Gemini Response',
  },
  {
    // Perplexity
    hostMatch: 'perplexity.ai',
    scrollSelectors: ['[role="main"]', 'main'],
    contentSelectors: [
      '[class*="prose"]',
      '[class*="answer"]',
      '[class*="markdown"]',
    ],
    wrapLabel: 'Perplexity Answer',
  },
  {
    // 通用 fallback（匹配任意 hostname）
    hostMatch: null,
    scrollSelectors: ['[role="main"]', 'main', 'article'],
    contentSelectors: [
      'article',
      'main',
      '[role="main"]',
      '[role="log"]',         // chat log ARIA role
      '[role="article"]',
      '#main-content', '#content', '.content',
      '.post-body', '.post-content', '.entry-content',
    ],
    wrapLabel: 'Content Block',
  },
]

// ─────────────────────────────────────────────────────────────────────────────
// 获取当前 hostname 对应的平台配置
// ─────────────────────────────────────────────────────────────────────────────

function getPlatformConfig() {
  const hostname = window.location.hostname
  for (const cfg of PLATFORM_CONFIGS) {
    if (cfg.hostMatch && hostname.includes(cfg.hostMatch)) return cfg
  }
  // 通用 fallback（hostMatch === null）
  return PLATFORM_CONFIGS[PLATFORM_CONFIGS.length - 1]
}

// ─────────────────────────────────────────────────────────────────────────────
// 策略 A：按配置表的 contentSelectors 收集元素文本
// 按 selectors 优先级尝试，第一个有结果的胜出
// ─────────────────────────────────────────────────────────────────────────────

function collectWithSelectors(selectors, wrapLabel) {
  for (const selector of selectors) {
    let elements
    try {
      elements = document.querySelectorAll(selector)
    } catch {
      // 无效选择器（如 Web Component 名），跳过
      continue
    }

    if (elements.length === 0) continue

    const fragments = []
    const seen = new Set()

    elements.forEach((el, i) => {
      const text = el.innerText?.trim() ?? ''
      if (text.length > 20 && !seen.has(text)) {
        seen.add(text)
        fragments.push(`=== ${wrapLabel} ${i + 1} ===\n\n${text}`)
      }
    })

    if (fragments.length > 0) {
      console.log(`[content.js] Strategy A matched: "${selector}" → ${fragments.length} blocks`)
      return fragments.join('\n\n')
    }
  }
  return null  // 所有 selector 均无结果
}

// ─────────────────────────────────────────────────────────────────────────────
// 策略 B：TreeWalker — 选择器无关的全文提取
// 遍历所有可见文本节点，跳过导航/页脚/脚本等噪音区域
// ─────────────────────────────────────────────────────────────────────────────

const SKIP_TAGS = new Set([
  'NAV', 'HEADER', 'FOOTER', 'ASIDE',
  'SCRIPT', 'STYLE', 'NOSCRIPT',
  'SVG', 'CANVAS', 'IFRAME',
  'BUTTON', 'SELECT', 'OPTION',
])

const SKIP_ROLES = new Set(['navigation', 'banner', 'contentinfo', 'toolbar', 'search'])

function isElementVisible(el) {
  if (!el || !el.isConnected) return false
  const style = window.getComputedStyle(el)
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false
  return true
}

function hasSkippedAncestor(el) {
  let node = el
  while (node && node !== document.body) {
    if (SKIP_TAGS.has(node.tagName)) return true
    const role = node.getAttribute?.('role')
    if (role && SKIP_ROLES.has(role)) return true
    node = node.parentElement
  }
  return false
}

function extractWithTreeWalker() {
  console.log('[content.js] Strategy B: TreeWalker extraction')

  const walker = document.createTreeWalker(
    document.body,
    NodeFilter.SHOW_TEXT,
    {
      acceptNode(textNode) {
        const text = textNode.textContent?.trim() ?? ''
        if (text.length < 15) return NodeFilter.FILTER_REJECT  // 过短，跳过

        const parent = textNode.parentElement
        if (!parent) return NodeFilter.FILTER_REJECT
        if (!isElementVisible(parent)) return NodeFilter.FILTER_REJECT
        if (hasSkippedAncestor(parent)) return NodeFilter.FILTER_REJECT

        return NodeFilter.FILTER_ACCEPT
      },
    }
  )

  // 按段落聚合（相邻节点合并）
  const paragraphs = []
  let currentParagraph = []
  let lastParent = null

  while (walker.nextNode()) {
    const node = walker.currentNode
    const text = node.textContent.trim()
    const parent = node.parentElement

    // 判断是否换新段落：父元素发生变化且不是内联元素
    const isBlock = parent !== lastParent &&
      !['SPAN', 'A', 'STRONG', 'EM', 'B', 'I', 'CODE', 'MARK'].includes(parent.tagName)

    if (isBlock && currentParagraph.length > 0) {
      const joined = currentParagraph.join(' ').trim()
      if (joined.length > 20) paragraphs.push(joined)
      currentParagraph = []
    }

    currentParagraph.push(text)
    lastParent = parent
  }

  if (currentParagraph.length > 0) {
    const joined = currentParagraph.join(' ').trim()
    if (joined.length > 20) paragraphs.push(joined)
  }

  // 去重（完全相同的段落只保留一次）
  const seen = new Set()
  const unique = paragraphs.filter((p) => {
    if (seen.has(p)) return false
    seen.add(p)
    return true
  })

  console.log(`[content.js] Strategy B extracted ${unique.length} paragraphs`)
  return unique.join('\n\n')
}

// ─────────────────────────────────────────────────────────────────────────────
// 核心入口：滚动 + 策略 A + 策略 B fallback
// ─────────────────────────────────────────────────────────────────────────────

async function scrollAndCollect() {
  const config = getPlatformConfig()
  console.log(`[content.js] Platform config:`, config.hostMatch || 'generic fallback')

  // ── 1. 定位滚动容器 ────────────────────────────────────────────────────────
  // 兼容旧的 scrollSelector（string）和新的 scrollSelectors（array）
  let scrollEl = null
  const scrollCandidates = config.scrollSelectors
    ?? (config.scrollSelector ? [config.scrollSelector] : [])

  for (const sel of scrollCandidates) {
    const el = document.querySelector(sel)
    if (el) {
      // 验证该元素确实可以滚动（scrollHeight > clientHeight）
      if (el.scrollHeight > el.clientHeight + 50) {
        scrollEl = el
        console.log(`[content.js] Scroll container found: "${sel}"`)
        break
      }
      // 元素存在但不可滚动，继续尝试下一个
      console.log(`[content.js] Selector "${sel}" found but not scrollable, trying next…`)
    }
  }

  // 仍未找到：自动检测最大可滚动 div
  if (!scrollEl) {
    scrollEl = findLargestScrollable()
    if (scrollEl) console.log('[content.js] Scroll container found via findLargestScrollable()')
  }

  // ── 2. 执行滚动（确保懒加载内容全部渲染） ────────────────────────────────────
  if (scrollEl) {
    await doScroll(scrollEl)
  } else {
    // 没有滚动容器：滚动整个页面
    await scrollPage()
  }

  // ── 3. 策略 A：按配置表选择器收集 ────────────────────────────────────────────
  const strategyAResult = collectWithSelectors(config.contentSelectors, config.wrapLabel)
  if (strategyAResult && strategyAResult.length > 100) {
    return {
      title: document.title || window.location.href,
      text: strategyAResult,
      strategy: 'A',
    }
  }

  // ── 4. 策略 B：TreeWalker fallback ───────────────────────────────────────────
  console.log('[content.js] Strategy A insufficient, falling back to TreeWalker')
  const strategyBResult = extractWithTreeWalker()
  if (strategyBResult && strategyBResult.length > 50) {
    return {
      title: document.title || window.location.href,
      text: strategyBResult,
      strategy: 'B',
    }
  }

  // ── 5. 终极兜底：document.body.innerText ─────────────────────────────────────
  console.warn('[content.js] Both strategies insufficient, using body.innerText')
  return {
    title: document.title || window.location.href,
    text: document.body.innerText || '',
    strategy: 'fallback',
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 辅助：找页面上最大的可滚动 div（当没有显式 scrollSelector 时）
// ─────────────────────────────────────────────────────────────────────────────

function findLargestScrollable() {
  let best = null
  let bestSize = 0

  document.querySelectorAll('div, main, section, article').forEach((el) => {
    if (el.scrollHeight > el.clientHeight + 100) {
      const size = el.scrollHeight * el.clientWidth
      if (size > bestSize) {
        bestSize = size
        best = el
      }
    }
  })

  return best
}

// ─────────────────────────────────────────────────────────────────────────────
// 辅助：在指定元素内滚动（逐步，触发懒加载）
// ─────────────────────────────────────────────────────────────────────────────

async function doScroll(el) {
  el.scrollTo({ top: 0, behavior: 'instant' })
  await sleep(800)

  let lastTop = -1
  const step = 600
  let stuckCount = 0

  while (true) {
    const isAtBottom =
      Math.ceil(el.scrollTop + el.clientHeight) >= el.scrollHeight - 50

    if (isAtBottom) break

    if (Math.abs(el.scrollTop - lastTop) < 5 && lastTop !== -1) {
      stuckCount++
      if (stuckCount >= 3) { console.warn('[content.js] Scroll stuck, stopping'); break }
      el.scrollBy({ top: step * 2, behavior: 'instant' })
    } else {
      stuckCount = 0
    }

    lastTop = el.scrollTop
    el.scrollBy({ top: step, behavior: 'instant' })
    await sleep(600)
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 辅助：滚动整个页面（无独立滚动容器时）
// ─────────────────────────────────────────────────────────────────────────────

async function scrollPage() {
  window.scrollTo({ top: 0, behavior: 'instant' })
  await sleep(500)

  let lastY = -1
  while (true) {
    const isAtBottom =
      Math.ceil(window.scrollY + window.innerHeight) >= document.body.scrollHeight - 50
    if (isAtBottom || window.scrollY === lastY) break

    lastY = window.scrollY
    window.scrollBy({ top: 600, behavior: 'instant' })
    await sleep(500)
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Message listener
// ─────────────────────────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'scrape') {
    ;(async () => {
      try {
        const data = await scrollAndCollect()
        if (!data.text || data.text.trim().length < 5) {
          throw new Error('Captured content is empty')
        }
        console.log(`[content.js] Scrape complete via strategy "${data.strategy}", ${data.text.length} chars`)
        sendResponse({ success: true, text: data.text, title: data.title, strategy: data.strategy })
      } catch (error) {
        console.error('[content.js] Scrape failed:', error)
        sendResponse({ success: false, error: error.message })
      }
    })()
    return true   // 保持 sendResponse 通道异步打开
  }
})
