import React, { useState } from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import Login from './components/Login'
import './index.css'

/**
 * AuthGate — shows Login until a valid session token is present.
 * Token is persisted in sessionStorage so a page refresh keeps the user in.
 */
const AuthGate: React.FC = () => {
  const [token, setToken] = useState<string | null>(
    () => sessionStorage.getItem('auth_token')
  )
  const [username, setUsername] = useState<string | null>(
    () => sessionStorage.getItem('auth_username')
  )

  const handleLogin = (newToken: string, newUsername: string) => {
    setToken(newToken)
    setUsername(newUsername)
  }

  const handleLogout = () => {
    if (token) {
      fetch('/api/auth/logout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      }).catch(() => {})
    }
    sessionStorage.removeItem('auth_token')
    sessionStorage.removeItem('auth_username')
    setToken(null)
    setUsername(null)
  }

  if (!token) {
    return <Login onLogin={handleLogin} />
  }

  return <App username={username ?? 'User'} onLogout={handleLogout} />
}

const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
)

root.render(
  <React.StrictMode>
    <AuthGate />
  </React.StrictMode>
)