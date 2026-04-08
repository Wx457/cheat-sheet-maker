/**
 * Single source of truth for API base URLs (dev & production).
 *
 * When changing the production address:
 * 1. Update PRODUCTION_API_ORIGIN below
 * 2. Update host_permissions in manifest.json accordingly
 *
 * config.js picks the right origin at runtime based on whether the manifest
 * contains update_url (Chrome Web Store builds do, unpacked loads do not).
 */
;(function initApiConfig() {
  window.API_CONFIG = {
    LOCAL_API_ORIGIN: 'http://localhost:8000',
    PRODUCTION_API_ORIGIN: 'http://18.189.87.197:8000',
  }
})()
