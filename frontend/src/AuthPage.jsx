import { useMemo, useState } from 'react'
import './styles/auth.css'

export default function AuthPage({ onAuth = () => {}, initialTab = 'login' }) {
  // מצב: התחברות / הרשמה
  const [mode, setMode] = useState(initialTab)

  // שדות התחברות
  const [loginEmail, setLoginEmail] = useState('')
  const [loginPassword, setLoginPassword] = useState('')

  // שדות הרשמה
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [emailConfirm, setEmailConfirm] = useState('')
  const [password, setPassword] = useState('')
  const [phone, setPhone] = useState('')
  const [telegramUser, setTelegramUser] = useState('')
  const [coupon, setCoupon] = useState('') // ← חדש

  // סטטוס
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // API base
  const API_BASE = useMemo(() => {
    const envUrl = import.meta.env.VITE_API_URL
    if (envUrl) return envUrl.replace(/\/+$/, '')
    const isHttps = typeof window !== 'undefined' && window.location.protocol === 'https:'
    const host = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1'
    return `${isHttps ? 'https' : 'http'}://${host}:8000/api`
  }, [])

  const resetError = () => setError('')

  const handleLogin = async (e) => {
    e.preventDefault()
    resetError()
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: (loginEmail || '').trim().toLowerCase(),
          password: loginPassword
        })
      })
      if (!res.ok) {
        const txt = await res.text()
        throw new Error(parseErr(txt))
      }
      const data = await res.json()
      onAuth(data, { email: (loginEmail || '').trim().toLowerCase(), flow: 'login' })
    } catch (err) {
      setError(err.message || 'שגיאה בהתחברות')
    } finally {
      setLoading(false)
    }
  }

  const handleRegister = async (e) => {
    e.preventDefault()
    resetError()

    // ולידציות צד לקוח
    if (!firstName.trim()) return setError('שם פרטי חובה')
    if (!lastName.trim()) return setError('שם משפחה חובה')
    if (!email.trim()) return setError('מייל חובה')
    if (!isValidEmail(email)) return setError('מבנה המייל שגוי')
    if (!emailConfirm.trim()) return setError('יש להזין מייל לאישור')
    if (email.trim().toLowerCase() !== emailConfirm.trim().toLowerCase()) {
      return setError('המיילים לא תואמים')
    }
    if (!password) return setError('סיסמה חובה')
    if (password.length < 6) return setError('סיסמה חייבת להיות באורך 6 תווים לפחות')
    if (!phone.trim()) return setError('טלפון חובה')
    if (!telegramUser.trim()) return setError('שם משתמש בטלגרם חובה')

    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          email: email.trim().toLowerCase(),
          email_confirm: emailConfirm.trim().toLowerCase(),
          password,
          phone: phone.trim(),
          telegram_username: telegramUser.trim(),
          coupon: coupon.trim() || null // ← חדש
        })
      })
      if (!res.ok) {
        const txt = await res.text()
        throw new Error(parseErr(txt))
      }
      const data = await res.json()
      onAuth(data, { email: email.trim().toLowerCase(), flow: 'register' })
    } catch (err) {
      setError(err.message || 'שגיאה בהרשמה')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth container">
      <div className="auth-card glass">
        <div className="auth-tabs">
          <button
            className={`auth-tab ${mode === 'login' ? 'is-active' : ''}`}
            onClick={() => setMode('login')}
            disabled={loading}
          >
            התחברות
          </button>
          <button
            className={`auth-tab ${mode === 'register' ? 'is-active' : ''}`}
            onClick={() => setMode('register')}
            disabled={loading}
          >
            הרשמה
          </button>
        </div>

        {mode === 'login' ? (
          <form className="auth-form" onSubmit={handleLogin}>
            {/* כניסה */}
            <Field label="מייל">
              <input
                dir="ltr"
                type="email"
                autoComplete="email"
                placeholder="name@example.com"
                value={loginEmail}
                onChange={(e) => setLoginEmail(e.target.value)}
                required
              />
            </Field>
            <Field label="סיסמה">
              <input
                dir="ltr"
                type="password"
                autoComplete="current-password"
                placeholder="••••••••"
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
                required
              />
            </Field>
            {error && <div className="auth-error">{error}</div>}
            <button className="btn btn--primary auth-submit" disabled={loading}>
              {loading ? 'מתחבר…' : 'התחברות'}
            </button>
          </form>
        ) : (
          <form className="auth-form" onSubmit={handleRegister}>
            {/* הרשמה */}
            <div className="grid-2">
              <Field label="שם פרטי">
                <input value={firstName} onChange={(e) => setFirstName(e.target.value)} required />
              </Field>
              <Field label="שם משפחה">
                <input value={lastName} onChange={(e) => setLastName(e.target.value)} required />
              </Field>
            </div>
            <div className="grid-2">
              <Field label="מייל">
                <input dir="ltr" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </Field>
              <Field label="מייל לאישור">
                <input dir="ltr" type="email" value={emailConfirm} onChange={(e) => setEmailConfirm(e.target.value)} required />
              </Field>
            </div>
            <Field label="סיסמה">
              <input dir="ltr" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={6} />
            </Field>
            <div className="grid-2">
              <Field label="טלפון">
                <input dir="ltr" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} required />
              </Field>
              <Field label="שם משתמש בטלגרם">
                <input dir="ltr" type="text" value={telegramUser} onChange={(e) => setTelegramUser(e.target.value)} required />
              </Field>
            </div>

            {/* ← חדש: שדה קופון */}
            <Field label="קופון (לא חובה)">
              <input dir="ltr" type="text" value={coupon} onChange={(e) => setCoupon(e.target.value)} />
            </Field>

            {error && <div className="auth-error">{error}</div>}
            <button className="btn btn--primary auth-submit" disabled={loading}>
              {loading ? 'נרשם…' : 'הרשמה'}
            </button>
          </form>
        )}

        <div className="auth-footnote">
          פרטי ההרשמה נשמרים בבסיס הנתונים (Users): שם, טלפון, Telegram, קופון ועוד.
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }) {
  return (
    <label className="field">
      <div className="field__label">{label}</div>
      <div className="field__control">{children}</div>
    </label>
  )
}

function isValidEmail(v) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)
}

function parseErr(txt) {
  try {
    const j = JSON.parse(txt)
    return j.detail || txt
  } catch {
    return txt || 'בקשה נכשלה'
  }
}
