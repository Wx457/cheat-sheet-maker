// Service Worker for Chrome Extension
// 处理 Side Panel 的打开行为

chrome.runtime.onInstalled.addListener(() => {
  // 设置点击扩展图标时打开 Side Panel
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })
})

// 确保每次点击扩展图标时都打开 Side Panel
chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ windowId: tab.windowId })
})

