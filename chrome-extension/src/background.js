// Service Worker for Chrome Extension — Side Panel open behavior + Clerk session (UPGRADE_PLAN 2-3-d)
//
// Bundled by esbuild into dist/background.js. clerk-config.js stays external and is loaded at runtime
// from the extension root, so the publishable key never ends up in the bundle or in git.

import { createClerkClient } from '@clerk/chrome-extension/client'
import { CLERK_PUBLISHABLE_KEY, CLERK_SYNC_HOST } from '/clerk-config.js'

chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })
})

chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ windowId: tab.windowId })
})

// ─────────────────────────────────────────────────────────────────────────────
// Clerk
// ─────────────────────────────────────────────────────────────────────────────

// The service worker can be killed at any time, so never assume this survives between messages —
// always go through getClerk(). A background client only reads the webapp session (syncHost cookie)
// when it loads, so `fresh` rebuilds it after the user signs in / out on the webapp.
//
// The syncHost cookies live on the cookie domain "localhost" (no port). Chrome checks cookie access
// against that portless URL, so manifest host_permissions needs "http://localhost/*" — the
// "http://localhost:3000/*" entry alone makes chrome.cookies return nothing (see REPO.md §6).
let clerkPromise = null

function getClerk({ fresh = false } = {}) {
  if (fresh || !clerkPromise) {
    clerkPromise = createClerkClient({
      publishableKey: CLERK_PUBLISHABLE_KEY,
      syncHost: CLERK_SYNC_HOST,
      background: true,
    }).catch((err) => {
      clerkPromise = null
      throw err
    })
  }
  return clerkPromise
}

function tokenHasAzp(token) {
  try {
    const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    return Boolean(JSON.parse(atob(payload)).azp)
  } catch {
    return false
  }
}

async function fetchToken(clerk) {
  if (!clerk.session) return null
  try {
    let token = await clerk.session.getToken()
    // A freshly loaded client starts from the session's last_active_token. Right after an OAuth
    // sign-in on the webapp that token was minted server-side (no Origin), so it has no `azp` and the
    // backend's authorized_parties check rejects it until it expires (~60s). Mint one from here instead:
    // its azp is chrome-extension://<id>. See REPO.md §7.
    if (token && !tokenHasAzp(token)) {
      token = await clerk.session.getToken({ skipCache: true })
    }
    return token || null
  } catch (err) {
    console.warn('[Clerk] getToken failed, treating as signed out:', err)
    return null   // session revoked / signed out on the webapp
  }
}

// Returns { clerk, token } with token === null when signed out. Retries once with a fresh client
// so a sign-in or sign-out on the webapp is picked up without reloading the extension.
async function getSession() {
  let clerk = await getClerk()
  let token = await fetchToken(clerk)
  if (!token) {
    clerk = await getClerk({ fresh: true })
    token = await fetchToken(clerk)
  }
  return { clerk, token }
}

// ─────────────────────────────────────────────────────────────────────────────
// 登录态推送：webapp 登录 / 登出 → 立刻通知 side panel
// ─────────────────────────────────────────────────────────────────────────────
//
// side panel 一直开着时不会触发 visibilitychange（切换浏览器标签不影响侧栏可见性），所以不能只靠
// panel 自己在打开时查询。Clerk 在 webapp 域名上写的 `__client_uat`（dev 实例还有带后缀的
// `__client_uat_<suffix>`）只在登录 / 登出时变化（登出时值为 0），而 `__session` 每 ~60s 刷新一次，
// 太吵。所以只监听前者：变化时丢掉缓存的 client，再广播 auth:changed，panel 收到后重新查询。
// 同一次登录会连续触发「删除旧值 + 写入新值」等多个事件，防抖合并成一次。
const SYNC_HOST_DOMAIN = new URL(CLERK_SYNC_HOST).hostname
let authChangedTimer = null

function isSyncHostAuthCookie(cookie) {
  return cookie.domain.replace(/^\./, '') === SYNC_HOST_DOMAIN && cookie.name.startsWith('__client_uat')
}

chrome.cookies.onChanged.addListener(({ cookie }) => {
  if (!isSyncHostAuthCookie(cookie)) return
  clearTimeout(authChangedTimer)
  authChangedTimer = setTimeout(() => {
    clerkPromise = null
    // 没有打开的 panel 时 sendMessage 会 reject（Receiving end does not exist），忽略即可
    chrome.runtime.sendMessage({ type: 'auth:changed' }).catch(() => {})
  }, 300)
})

const handlers = {
  // popup 点了 Sign out：丢掉缓存的 client，下次查询必定重新读 cookie + 问 Clerk
  'auth:reset': async () => {
    clerkPromise = null
    return null
  },
  'auth:getToken': async () => (await getSession()).token,
  'auth:getUser': async () => {
    const { clerk, token } = await getSession()
    if (!token || !clerk.user) return null
    return {
      userId: clerk.user.id,
      email: clerk.user.primaryEmailAddress?.emailAddress || null,
    }
  },
}

// Replies { ok: true, data } or { ok: false, error } so popup can tell "signed out" from "auth broken".
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const handler = handlers[message?.type]
  if (!handler) return false
  handler()
    .then((data) => sendResponse({ ok: true, data }))
    .catch((err) => {
      console.error(`[Clerk] ${message.type} failed:`, err)
      sendResponse({ ok: false, error: String(err?.message || err) })
    })
  return true   // keep the channel open for the async reply
})
