import React, { FormEvent, useState } from 'react'
import './Login.css'

interface LoginProps {
  onLogin: (token: string, username: string) => void
}

const Login: React.FC<LoginProps> = ({ onLogin }) => {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password.trim()) return

    setLoading(true)
    setError(null)

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      })

      const data = await res.json()

      if (!res.ok) {
        setError(data.detail || 'Login failed. Please check your credentials.')
        return
      }

      // Persist token in sessionStorage so page refresh keeps you logged in
      sessionStorage.setItem('auth_token', data.token)
      sessionStorage.setItem('auth_username', data.username)
      onLogin(data.token, data.username)
    } catch {
      setError('Could not reach the server. Make sure the backend is running.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-container">
      {/* Decorative blobs */}
      <div className="login-blob login-blob-1" aria-hidden="true" />
      <div className="login-blob login-blob-2" aria-hidden="true" />

      <div className="login-card">
        {/* Brand header */}
        <div className="login-brand">
          <span className="login-logo-pill">EduBot</span>
          <h1 className="login-title">Compliance Studio</h1>
          <p className="login-subtitle">NAAC Intelligence Platform — MVSR</p>
        </div>

        {/* Demo hint */}
        <div className="login-hint">
          <p className="login-hint-label">Demo accounts</p>
          <div className="login-hint-chips">
            {[
              { u: 'admin', p: 'naac2025' },
              { u: 'faculty', p: 'mvsr@faculty' },
              { u: 'demo', p: 'demo1234' },
            ].map(({ u, p }) => (
              <button
                key={u}
                type="button"
                className="login-chip"
                onClick={() => { setUsername(u); setPassword(p); setError(null) }}
              >
                {u}
              </button>
            ))}
          </div>
        </div>

        {/* Form */}
        <form className="login-form" onSubmit={handleSubmit} noValidate>
          <div className="login-field">
            <label htmlFor="login-username">Username</label>
            <input
              id="login-username"
              type="text"
              autoComplete="username"
              placeholder="Enter your username"
              value={username}
              onChange={e => { setUsername(e.target.value); setError(null) }}
              disabled={loading}
            />
          </div>

          <div className="login-field">
            <label htmlFor="login-password">Password</label>
            <div className="login-password-wrap">
              <input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                placeholder="Enter your password"
                value={password}
                onChange={e => { setPassword(e.target.value); setError(null) }}
                disabled={loading}
              />
              <button
                type="button"
                className="login-eye"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                onClick={() => setShowPassword(v => !v)}
              >
                {showPassword ? '🙈' : '👁'}
              </button>
            </div>
          </div>

          {error && (
            <div className="login-error" role="alert">
              {error}
            </div>
          )}

          <button
            id="login-submit"
            type="submit"
            className="login-submit"
            disabled={loading || !username.trim() || !password.trim()}
          >
            {loading ? (
              <span className="login-spinner" />
            ) : (
              'Sign in'
            )}
          </button>
        </form>

        <p className="login-footer">
          Built for MVSR Engineering College NAAC Accreditation
        </p>
      </div>
    </div>
  )
}

export default Login
