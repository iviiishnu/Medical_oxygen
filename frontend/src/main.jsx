import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// ── Apply saved theme before render (prevents flash) ─────────────────────────
try {
  const theme = localStorage.getItem('medigas_theme');
  if (theme === 'dark') {
    document.documentElement.dataset.theme = 'dark';
  }
} catch {}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
