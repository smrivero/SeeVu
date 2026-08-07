import { useState } from 'react'
import { loginApi } from './api.js'

export default function LoginScreen({ onLogin }) {
  const [email, setEmail]     = useState(() => localStorage.getItem('saved_email') || '')
  const [pass, setPass]       = useState(() => localStorage.getItem('saved_pass') || '')
  const [remember, setRemember] = useState(() => !!localStorage.getItem('saved_email'))
  const [showPass, setShowPass] = useState(false)
  const [error, setError]     = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      // Shorthand for the demo account: "upwork" alone expands to the full
      // address before hitting Supabase.
      const loginEmail = email.trim().toLowerCase() === 'upwork' ? 'upwork@upwork.demo' : email
      const { ok, data } = await loginApi(loginEmail, pass)
      if (ok) {
        if (remember) {
          localStorage.setItem('saved_email', email)
          localStorage.setItem('saved_pass', pass)
        } else {
          localStorage.removeItem('saved_email')
          localStorage.removeItem('saved_pass')
        }
        onLogin()
      } else {
        setError(data?.error || 'Invalid credentials')
      }
    } catch {
      setError('Connection error')
    }
    setLoading(false)
  }

  return (
    <div className="login-bg">
      <div className="login-card">
        <div className="login-logo">
          <svg viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg" style={{width:60,height:60}}>
            <defs>
              <linearGradient id="sv-lg" x1="0" y1="0" x2="60" y2="60" gradientUnits="userSpaceOnUse">
                <stop stopColor="#38C6F4"/>
                <stop offset="1" stopColor="#0B5CAD"/>
              </linearGradient>
            </defs>
            <rect width="60" height="60" rx="14" fill="url(#sv-lg)"/>
            <path d="M11 30 Q20 20 30 20 Q40 20 49 30 Q40 40 30 40 Q20 40 11 30Z" fill="white"/>
            <circle cx="30" cy="30" r="8" fill="#1EA7F2"/>
            <path d="M22 30v3.5M25.5 27v7M29 28.5v5M32.5 26v8M36 27.5v6" stroke="white" strokeWidth="2.2" strokeLinecap="round"/>
            <rect x="41" y="8" width="3.5" height="3.5" rx=".8" fill="rgba(255,255,255,.7)"/>
            <rect x="46.5" y="8" width="3.5" height="3.5" rx=".8" fill="rgba(255,255,255,.45)"/>
            <rect x="43.5" y="13" width="3" height="3" rx=".7" fill="rgba(255,255,255,.3)"/>
            <rect x="7" y="43" width="3.5" height="3.5" rx=".8" fill="rgba(255,255,255,.7)"/>
            <rect x="12.5" y="43" width="3.5" height="3.5" rx=".8" fill="rgba(255,255,255,.45)"/>
            <rect x="7" y="48.5" width="3" height="3" rx=".7" fill="rgba(255,255,255,.3)"/>
          </svg>
          <div className="login-logo-text">See<span>Vu</span></div>
          <div className="login-logo-sub">AI Call Automation</div>
        </div>
        <div className="login-divider"/>
        {error && <div className="login-error">{error}</div>}
        <form onSubmit={handleSubmit}>
          <label className="login-label" htmlFor="login-u">Email</label>
          <input
            id="login-u"
            className="login-input"
            type="text"
            inputMode="email"
            placeholder="Enter your email"
            autoComplete="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
          />
          <label className="login-label" htmlFor="login-p">Password</label>
          <div className="login-input-wrap">
            <input
              id="login-p"
              className="login-input"
              type={showPass ? 'text' : 'password'}
              placeholder="Enter your password"
              autoComplete="current-password"
              value={pass}
              onChange={e => setPass(e.target.value)}
            />
            <button
              type="button"
              className="login-eye"
              onClick={() => setShowPass(v => !v)}
              tabIndex={-1}
              aria-label={showPass ? 'Hide password' : 'Show password'}
            >
              {showPass ? (
                <svg fill="none" viewBox="0 0 20 20" stroke="currentColor" strokeWidth="1.6">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 3l14 14M10 4C5 4 1.3 10 1.3 10s1.5 2.4 4 4M7.6 7.6A3 3 0 0 0 10 13a3 3 0 0 0 2.4-1.2M12.8 8A3 3 0 0 0 10 7c-.3 0-.6 0-.9.1M15.5 11.5C17.3 9.7 18.7 10 18.7 10S15 4 10 4c-.8 0-1.6.1-2.3.4"/>
                </svg>
              ) : (
                <svg fill="none" viewBox="0 0 20 20" stroke="currentColor" strokeWidth="1.6">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M1.3 10S5 4 10 4s8.7 6 8.7 6-3.7 6-8.7 6S1.3 10 1.3 10z"/>
                  <circle cx="10" cy="10" r="3"/>
                </svg>
              )}
            </button>
          </div>
          <label className="login-remember">
            <input
              type="checkbox"
              checked={remember}
              onChange={e => setRemember(e.target.checked)}
            />
            Save credentials
          </label>
          <button className="login-btn" type="submit" disabled={loading}>
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
