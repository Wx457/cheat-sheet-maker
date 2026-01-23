import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import PrintPage from './pages/PrintPage.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HashRouter>
      <Routes>
        {/* Headless Renderer only: Playwright 访问 #/print 并注入 window.CHEAT_SHEET_DATA */}
        <Route path="/print" element={<PrintPage />} />
      </Routes>
    </HashRouter>
  </StrictMode>,
)
