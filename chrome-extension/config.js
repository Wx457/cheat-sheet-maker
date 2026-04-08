// Dev / production routing: unpacked loads & local zips lack update_url → local API;
// Chrome Web Store installs have update_url → production API (address in api-config.js only).
;(function initRuntimeConfig() {
  const cfg = window.API_CONFIG || {}
  const localOrigin = cfg.LOCAL_API_ORIGIN || 'http://localhost:8000'
  const isDev = !('update_url' in chrome.runtime.getManifest())

  let apiBaseUrl
  if (isDev) {
    apiBaseUrl = localOrigin
  } else {
    apiBaseUrl = cfg.PRODUCTION_API_ORIGIN
    if (!apiBaseUrl) {
      console.error(
        '[CheatSheet] Store build requires PRODUCTION_API_ORIGIN in api-config.js (must match manifest host_permissions).'
      )
      apiBaseUrl = localOrigin
    }
  }

  window.IS_DEV = isDev
  window.API_BASE_URL = apiBaseUrl
})()
