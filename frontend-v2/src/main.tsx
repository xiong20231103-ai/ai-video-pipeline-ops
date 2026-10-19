import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { applyTheme, initialTheme } from './lib/preferences'
import './styles.css'

// External module, not an inline script: compatible with the existing cloud CSP.
applyTheme(initialTheme())
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>)
