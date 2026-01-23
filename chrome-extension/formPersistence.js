// 表单数据持久化模块
// 使用 debounce 机制保存表单状态到 chrome.storage.local

/**
 * 表单持久化管理器
 * 自动保存表单状态，并在页面加载时恢复
 */
class FormPersistence {
  constructor() {
    this.debounceTimer = null
    this.debounceDelay = 500 // 500ms 防抖延迟
    this.storageKey = 'form_draft'
    this.isRestoring = false
  }

  /**
   * 收集当前表单数据
   */
  collectFormData() {
    const courseName = document.getElementById('courseName')?.value.trim() || ''
    const educationLevel = document.querySelector('input[name="educationLevel"]:checked')?.value || 'Undergraduate'
    const examType = document.querySelector('input[name="examType"]:checked')?.value || 'Final'
    const pageLimit = document.querySelector('input[name="pageLimit"]:checked')?.value || 'Unlimited'
    const syllabus = document.getElementById('syllabusInput')?.value.trim() || ''
    
    // 获取当前激活的标签页
    const activeTab = document.querySelector('.tab.active')?.dataset.tab || 'current-page'
    
    // 获取粘贴文本内容（仅在 paste-text 标签页时保存）
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
   * 保存表单数据到存储（带防抖）
   */
  saveFormData() {
    if (this.isRestoring) {
      return // 恢复数据时不触发保存
    }

    clearTimeout(this.debounceTimer)
    this.debounceTimer = setTimeout(() => {
      const formData = this.collectFormData()
      
      // 获取当前视图状态
      const viewForm = document.getElementById('view-form')
      const viewOutline = document.getElementById('view-outline')
      const currentView = viewForm?.style.display !== 'none' ? 'form' : 'outline'
      
      // 收集大纲数据（如果在大纲视图）
      let outlineData = null
      let extendedTopics = []
      if (currentView === 'outline') {
        // 尝试从全局变量获取（如果存在）
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
   * 从存储恢复表单数据
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
          // 恢复基础表单字段
          const courseNameInput = document.getElementById('courseName')
          if (courseNameInput && savedData.courseName) {
            courseNameInput.value = savedData.courseName
          }
          
          const syllabusInput = document.getElementById('syllabusInput')
          if (syllabusInput && savedData.syllabus) {
            syllabusInput.value = savedData.syllabus
          }
          
          // 恢复单选按钮
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
          
          // 恢复标签页
          if (savedData.activeTab) {
            const tabButton = document.querySelector(`.tab[data-tab="${savedData.activeTab}"]`)
            if (tabButton) {
              tabButton.click()
            }
            
            // 恢复粘贴文本（如果存在）
            if (savedData.activeTab === 'paste-text' && savedData.pasteText) {
              const pasteTextInput = document.getElementById('pasteTextInput')
              if (pasteTextInput) {
                pasteTextInput.value = savedData.pasteText
              }
            }
          }
          
          // 恢复视图状态
          if (savedData.currentView === 'outline' && savedData.outlineData) {
            // 延迟恢复大纲视图，确保 DOM 和全局变量已准备好
            setTimeout(() => {
              // 恢复大纲数据到全局变量
              if (typeof window.currentOutlineData !== 'undefined') {
                window.currentOutlineData = savedData.outlineData
              }
              
              if (savedData.extendedTopics && Array.isArray(savedData.extendedTopics)) {
                if (typeof window.extendedTopics !== 'undefined') {
                  window.extendedTopics = savedData.extendedTopics
                }
              }
              
              // 切换视图
              if (typeof window.showView === 'function') {
                window.showView('outline')
              }
              
              // 重新渲染大纲列表
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
   * 清除保存的草稿
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
   * 初始化：绑定事件监听器并恢复数据
   */
  async init() {
    // 绑定表单字段变化监听（先绑定，这样恢复数据时也会触发保存，但会被 isRestoring 标志阻止）
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
    
    // 监听单选按钮变化
    document.querySelectorAll('input[name="educationLevel"], input[name="examType"], input[name="pageLimit"]').forEach((radio) => {
      radio.addEventListener('change', () => this.saveFormData())
    })
    
    // 监听标签页切换
    document.querySelectorAll('.tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        setTimeout(() => this.saveFormData(), 100) // 延迟以确保 DOM 更新完成
      })
    })
    
    // 视图切换已在 popup.js 中处理，这里不需要重复拦截
    
    // 最后恢复数据（确保所有监听器都已绑定）
    await this.restoreFormData()
  }
}

// 创建全局实例
const formPersistence = new FormPersistence()

// 导出供其他脚本使用
if (typeof module !== 'undefined' && module.exports) {
  module.exports = FormPersistence
}

