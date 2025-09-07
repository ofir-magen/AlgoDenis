import { useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import ChatPage from '../ChatPage.jsx'

export default function Chat() {
  const navigate = useNavigate()

  // שליפת הטוקן מה־localStorage (נשמר ב־Auth.jsx שהוספנו)
  const token = useMemo(() => {
    try { return localStorage.getItem('token') || '' } catch { return '' }
  }, [])

  // קביעת ה-WS BASE
  // אפשר לקנפג דרך VITE_WS_URL; אחרת נבנה ברירת מחדל: ws(s)://<host>:8000/ws
  const WS_BASE = useMemo(() => {
    const envUrl = import.meta.env.VITE_WS_URL
    if (envUrl) return envUrl
    const isHttps = typeof window !== 'undefined' && window.location.protocol === 'https:'
    const host = typeof window !== 'undefined' ? window.location.hostname : 'localhost'
    const port = 8000
    return `${isHttps ? 'wss' : 'ws'}://${host}:${port}/ws`
  }, [])

  // אם אין טוקן — לך לעמוד ההרשמה/כניסה
  useEffect(() => {
    if (!token) navigate('/auth', { replace: true })
  }, [token, navigate])

  const onLogout = () => {
    try { localStorage.removeItem('token') } catch {}
    navigate('/auth', { replace: true })
  }

  // אם אין טוקן, אל תרנדר כלום (ה־useEffect כבר יפנה)
  if (!token) return null

  return <ChatPage token={token} WS_BASE={WS_BASE} onLogout={onLogout} />
}
