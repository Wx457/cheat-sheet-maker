// 运行环境配置（开发模式: localhost；生产模式: AWS）
// 开发（unpacked）通常没有 update_url；商店发布版本会包含 update_url
(function initRuntimeConfig() {
  const isDev = !('update_url' in chrome.runtime.getManifest())
  const apiBaseUrl = isDev ? 'http://localhost:8000' : 'http://18.189.87.197:8000'

  window.IS_DEV = isDev
  window.API_BASE_URL = apiBaseUrl
})()
