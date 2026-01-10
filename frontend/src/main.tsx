import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import PreviewPage from './components/PreviewPage.tsx'
import PrintPage from './pages/PrintPage.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HashRouter>
      <Routes>
        <Route path="/" element={<App />} />
        <Route path="/preview/:projectId" element={<PreviewPage />} />
        <Route path="/print" element={<PrintPage />} />
      </Routes>
    </HashRouter>
  </StrictMode>,
)
