import React, { FormEvent, useState } from 'react'

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
    <div className="min-h-screen bg-[#f9fafb] flex items-center justify-center p-4 font-sans text-gray-900 relative overflow-hidden">
      {/* Decorative blobs */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-100 rounded-full mix-blend-multiply filter blur-3xl opacity-50 animate-blob" aria-hidden="true" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-orange-50 rounded-full mix-blend-multiply filter blur-3xl opacity-50 animate-blob animation-delay-2000" aria-hidden="true" />

      <div className="relative w-full max-w-md bg-white rounded-2xl shadow-soft p-8 border border-gray-100 z-10">
        
        {/* Brand header */}
        <div className="flex flex-col items-center mb-8">
          <span className="bg-loginUI-bgSecondary border border-gray-200 text-gray-600 text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wider mb-4 shadow-sm">
            EduBot
          </span>
          <h1 className="text-3xl font-semibold tracking-tight text-gray-900 mb-2">EduBot</h1>
          <p className="text-sm text-gray-500 font-medium">NAAC Intelligence Platform — MVSR</p>
        </div>

        {/* Demo hint */}
        <div className="mb-8">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3 text-center">Demo accounts</p>
          <div className="flex flex-wrap justify-center gap-2">
            {[
              { u: 'admin', p: 'naac2025' },
              { u: 'faculty', p: 'mvsr@faculty' },
              { u: 'demo', p: 'demo1234' },
            ].map(({ u, p }) => (
              <button
                key={u}
                type="button"
                className="bg-gray-50 hover:bg-gray-100 text-gray-600 border border-gray-200 py-1.5 px-3 rounded-xl text-sm font-medium transition-colors duration-200"
                onClick={() => { setUsername(u); setPassword(p); setError(null) }}
              >
                {u}
              </button>
            ))}
          </div>
        </div>

        {/* Form */}
        <form className="space-y-5" onSubmit={handleSubmit} noValidate>
          <div className="flex flex-col space-y-1.5">
            <label htmlFor="login-username" className="text-sm font-medium text-gray-700">Username</label>
            <input
              id="login-username"
              type="text"
              autoComplete="username"
              placeholder="Enter your username"
              value={username}
              onChange={e => { setUsername(e.target.value); setError(null) }}
              disabled={loading}
              className="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all duration-200 placeholder-gray-400 text-gray-900 text-sm"
            />
          </div>

          <div className="flex flex-col space-y-1.5">
            <label htmlFor="login-password" className="text-sm font-medium text-gray-700">Password</label>
            <div className="relative">
              <input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                placeholder="Enter your password"
                value={password}
                onChange={e => { setPassword(e.target.value); setError(null) }}
                disabled={loading}
                className="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all duration-200 placeholder-gray-400 text-gray-900 text-sm pr-12"
              />
              <button
                type="button"
                className="absolute inset-y-0 right-0 px-4 text-gray-400 hover:text-gray-600 transition-colors"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                onClick={() => setShowPassword(v => !v)}
              >
                {showPassword ? '🙈' : '👁'}
              </button>
            </div>
          </div>

          {error && (
            <div className="p-3 bg-red-50 text-red-600 border border-red-100 rounded-xl text-sm font-medium text-center" role="alert">
              {error}
            </div>
          )}

          <button
            id="login-submit"
            type="submit"
            disabled={loading || !username.trim() || !password.trim()}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 disabled:cursor-not-allowed text-white font-medium py-3 rounded-xl shadow-sm hover:shadow-md transition-all duration-200 flex justify-center items-center h-12"
          >
            {loading ? (
              <span className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              'Sign in'
            )}
          </button>
        </form>

        <p className="mt-8 text-center text-xs text-gray-400 font-medium">
          Built for MVSR Engineering College NAAC Accreditation
        </p>
      </div>
    </div>
  )
}

export default Login
