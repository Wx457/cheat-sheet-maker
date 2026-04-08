// Form data persistence module — debounced save to chrome.storage.local

/**
 * Form persistence manager.
 * Auto-saves form state and restores it on page load.
 */
class FormPersistence {
  constructor() {
    this.debounceTimer = null
    this.debounceDelay = 500
    this.storageKey = 'form_draft'
    this.isRestoring = false
  }

  /**
   * Collect current form data.
   */
  collectFormData() {
    const courseName = document.getElementById('courseName')?.value.trim() || ''
    const educationLevel = document.querySelector('input[name="educationLevel"]:checked')?.value || 'Undergraduate'
    const examType = document.querySelector('input[name="examType"]:checked')?.value || 'Final'
    const pageLimit = document.querySelector('input[name="pageLimit"]:checked')?.value || 'Unlimited'
    const syllabus = document.getElementById('syllabusInput')?.value.trim() || ''
    
    const activeTab = document.querySelector('.tab.active')?.dataset.tab || 'current-page'
    
    // Only persist paste text when the paste-text tab is active
    const pasteText = activeTab === 'paste-text' 
      ? (document.getElementById('pasteTextInput')?.value.trim() || '')
      : ''
    
    return {
      courseName,
      educationLevel,
      examType,
      pageLimit,
      syllabus,
      activeTab,
      pasteText
    }
  }

  /**
   * Save form data to storage (debounced).
   */
  saveFormData() {
    if (this.isRestoring) {
      return // Skip saves triggered during restore
    }

    clearTimeout(this.debounceTimer)
    this.debounceTimer = setTimeout(() => {
      const formData = this.collectFormData()
      
      const viewForm = document.getElementById('view-form')
      const viewOutline = document.getElementById('view-outline')
      const currentView = viewForm?.style.display !== 'none' ? 'form' : 'outline'
      
      let outlineData = null
      let extendedTopics = []
      if (currentView === 'outline') {
        if (typeof window.currentOutlineData !== 'undefined' && window.currentOutlineData) {
          outlineData = window.currentOutlineData
        }
        if (typeof window.extendedTopics !== 'undefined' && Array.isArray(window.extendedTopics)) {
          extendedTopics = window.extendedTopics
        }
      }
      
      const dataToSave = {
        ...formData,
        currentView,
        outlineData,
        extendedTopics,
        savedAt: Date.now()
      }
      
      chrome.storage.local.set({ [this.storageKey]: dataToSave }, () => {
        if (chrome.runtime.lastError) {
          console.error('Failed to save form data:', chrome.runtime.lastError)
        } else {
          console.log('✅ Form data saved')
        }
      })
    }, this.debounceDelay)
  }

  /**
   * Restore form data from storage.
   */
  async restoreFormData() {
    return new Promise((resolve) => {
      chrome.storage.local.get([this.storageKey], (result) => {
        if (chrome.runtime.lastError) {
          console.error('Failed to load form data:', chrome.runtime.lastError)
          resolve(null)
          return
        }
        
        const savedData = result[this.storageKey]
        if (!savedData) {
          resolve(null)
          return
        }
        
        this.isRestoring = true
        
        try {
          // Restore basic form fields
          const courseNameInput = document.getElementById('courseName')
          if (courseNameInput && savedData.courseName) {
            courseNameInput.value = savedData.courseName
          }
          
          const syllabusInput = document.getElementById('syllabusInput')
          if (syllabusInput && savedData.syllabus) {
            syllabusInput.value = savedData.syllabus
          }
          
          // Restore radio buttons
          const educationLevelRadio = document.querySelector(`input[name="educationLevel"][value="${savedData.educationLevel}"]`)
          if (educationLevelRadio) {
            educationLevelRadio.checked = true
          }
          
          const examTypeRadio = document.querySelector(`input[name="examType"][value="${savedData.examType}"]`)
          if (examTypeRadio) {
            examTypeRadio.checked = true
          }
          
          const pageLimitRadio = document.querySelector(`input[name="pageLimit"][value="${savedData.pageLimit}"]`)
          if (pageLimitRadio) {
            pageLimitRadio.checked = true
          }
          
          // Restore active tab
          if (savedData.activeTab) {
            const tabButton = document.querySelector(`.tab[data-tab="${savedData.activeTab}"]`)
            if (tabButton) {
              tabButton.click()
            }
            
            if (savedData.activeTab === 'paste-text' && savedData.pasteText) {
              const pasteTextInput = document.getElementById('pasteTextInput')
              if (pasteTextInput) {
                pasteTextInput.value = savedData.pasteText
              }
            }
          }
          
          // Restore view state
          if (savedData.currentView === 'outline' && savedData.outlineData) {
            setTimeout(() => {
              if (typeof window.currentOutlineData !== 'undefined') {
                window.currentOutlineData = savedData.outlineData
              }
              
              if (savedData.extendedTopics && Array.isArray(savedData.extendedTopics)) {
                if (typeof window.extendedTopics !== 'undefined') {
                  window.extendedTopics = savedData.extendedTopics
                }
              }
              
              if (typeof window.showView === 'function') {
                window.showView('outline')
              }
              
              // Re-render the outline list
              setTimeout(() => {
                if (typeof window.renderOutlineList === 'function' && savedData.outlineData?.topics) {
                  window.renderOutlineList(savedData.outlineData.topics)
                } else if (typeof window.renderExtendedTopics === 'function') {
                  window.renderExtendedTopics()
                }
              }, 50)
            }, 200)
          }
          
          console.log('✅ Form data restored')
          resolve(savedData)
        } catch (error) {
          console.error('Error restoring form data:', error)
          resolve(null)
        } finally {
          this.isRestoring = false
        }
      })
    })
  }

  /**
   * Clear saved draft.
   */
  clearDraft() {
    chrome.storage.local.remove([this.storageKey], () => {
      if (chrome.runtime.lastError) {
        console.error('Failed to clear draft:', chrome.runtime.lastError)
      } else {
        console.log('✅ Draft cleared')
      }
    })
  }

  /**
   * Initialize: bind event listeners and restore data.
   */
  async init() {
    const courseNameInput = document.getElementById('courseName')
    if (courseNameInput) {
      courseNameInput.addEventListener('input', () => this.saveFormData())
    }
    
    const syllabusInput = document.getElementById('syllabusInput')
    if (syllabusInput) {
      syllabusInput.addEventListener('input', () => this.saveFormData())
    }
    
    const pasteTextInput = document.getElementById('pasteTextInput')
    if (pasteTextInput) {
      pasteTextInput.addEventListener('input', () => this.saveFormData())
    }
    
    // Listen for radio button changes
    document.querySelectorAll('input[name="educationLevel"], input[name="examType"], input[name="pageLimit"]').forEach((radio) => {
      radio.addEventListener('change', () => this.saveFormData())
    })
    
    // Listen for tab switches
    document.querySelectorAll('.tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        setTimeout(() => this.saveFormData(), 100)
      })
    })
    
    // View switch handling is in popup.js; no duplicate interception needed here
    
    // Restore data last (after all listeners are bound)
    await this.restoreFormData()
  }
}

// Global instance
const formPersistence = new FormPersistence()

// Export for other scripts
if (typeof module !== 'undefined' && module.exports) {
  module.exports = FormPersistence
}
