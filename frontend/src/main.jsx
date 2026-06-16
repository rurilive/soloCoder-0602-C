import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './App.css'

try {
  const params = new URLSearchParams(window.location.search)
  const hashToken = window.location.hash.match(/[?&]token=([^&]+)/)?.[1]
  const urlToken = params.get('token') || hashToken
  if (urlToken) {
    localStorage.setItem('token', urlToken)
    const cleanUrl = window.location.pathname + window.location.hash.replace(/[?&]token=[^&]+/g, '').replace(/^#/, '#')
    window.history.replaceState({}, document.title, cleanUrl)
  }
} catch (e) {
  console.warn('Failed to set token from URL:', e)
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
)
