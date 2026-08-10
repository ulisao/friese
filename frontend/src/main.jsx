import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import { restoreSession } from '@/lib/api'
import App from './App.jsx'
import './index.css'

// Se dispara una sola vez, antes del primer render: si había sesión guardada, la
// app arranca ya logueada. Fuera de un efecto a propósito, para que StrictMode
// no lo ejecute dos veces en desarrollo.
restoreSession()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
