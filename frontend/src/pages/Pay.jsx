// frontend/src/pages/Pay.jsx
import { useEffect, useMemo, useState } from 'react'

export default function Pay() {
  // ENV (ערוך ב-frontend/.env)
  const DEFAULT_PRICE = import.meta.env.VITE_SUB_PRICE_NIS || '49'
  const BIT_PHONE = import.meta.env.VITE_BIT_PHONE || ''
  const QR_URL = import.meta.env.VITE_BIT_QR_URL || '/bit-qr.png'

  // אימייל לחשבון (נשמר אחרי הרשמה/כניסה)
  const email = useMemo(() => {
    try { return localStorage.getItem('user_email') || '' } catch { return '' }
  }, [])

  // API base
  const API_BASE = useMemo(() => {
    const envUrl = import.meta.env.VITE_API_URL
    if (envUrl) return envUrl.replace(/\/+$/, '')
    const isHttps = typeof window !== 'undefined' && window.location.protocol === 'https:'
    const host = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1'
    return `${isHttps ? 'https' : 'http'}://${host}:8000/api`
  }, [])

  // מצב מחיר
  const [price, setPrice] = useState({
    base: Number(DEFAULT_PRICE),
    final: Number(DEFAULT_PRICE),
    discount_percent: 0,
    coupon: null,
    valid: false,
    loading: !!email
  })
  const [copied, setCopied] = useState('')

  useEffect(() => {
    let abort = false
    async function fetchPrice() {
      if (!email) return
      try {
        setPrice(p => ({ ...p, loading: true }))
        const url = `${API_BASE}/price?email=${encodeURIComponent(email)}`
        const res = await fetch(url)
        if (!res.ok) throw new Error('Price fetch failed')
        const data = await res.json()
        if (abort) return
        setPrice({
          base: Number(data.base ?? DEFAULT_PRICE),
          final: Number(data.final ?? data.base ?? DEFAULT_PRICE),
          discount_percent: Number(data.discount_percent ?? 0),
          coupon: data.coupon ?? null,
          valid: !!data.valid,
          loading: false
        })
      } catch {
        if (abort) return
        setPrice({
          base: Number(DEFAULT_PRICE),
          final: Number(DEFAULT_PRICE),
          discount_percent: 0,
          coupon: null,
          valid: false,
          loading: false
        })
      }
    }
    fetchPrice()
    return () => { abort = true }
  }, [email, API_BASE, DEFAULT_PRICE])

  const copy = async (txt) => {
    try { await navigator.clipboard.writeText(String(txt)); setCopied(String(txt)) } catch {}
    setTimeout(() => setCopied(''), 1200)
  }

  return (
    <div className="container" style={{ maxWidth: 760, paddingBlock: 24 }}>
      <div className="glass" style={{ padding: 22 }}>
        <h2 style={{ marginTop: 0 }}>תשלום ב־bit</h2>
        <p>להשלמת ההרשמה — סרקו את קוד ה־QR לביצוע התשלום, או העתיקו ידנית את הפרטים.</p>

        {/* בלוק ה-QR */}
        <div
          style={{
            marginTop: 14,
            display: 'grid',
            gridTemplateColumns: 'minmax(220px, 320px)',
            justifyContent: 'center',
            gap: 8,
            textAlign: 'center'
          }}
        >
          {QR_URL ? (
            <a href={QR_URL} target="_blank" rel="noreferrer" title="לחיצה תפתח את קוד ה-QR בלשונית חדשה">
              <img
                src={QR_URL}
                alt="Bit payment QR"
                style={{
                  width: '100%',
                  height: 'auto',
                  borderRadius: 16,
                  boxShadow: '0 8px 30px rgba(0,0,0,.12)',
                  background: '#fff'
                }}
              />
            </a>
          ) : (
            <div className="auth-hint">⚠️ לא הוגדר QR לתשלום. הוסף VITE_BIT_QR_URL ל-.env או שים קובץ <code>public/bit-qr.png</code>.</div>
          )}
          <small style={{ opacity: .85 }}>
            סרקו באמצעות מצלמת הטלפון / אפליקציית bit. (לחיצה תפתח את התמונה בגודל מלא)
          </small>
        </div>

        {/* פרטים ידניים (העתקה מהירה) */}
        <div style={{ display: 'grid', gap: 12, marginTop: 18 }}>
          <label className="field">
            <div className="field__label">סכום לתשלום (₪)</div>
            <div className="field__control" style={{ display: 'flex', gap: 8 }}>
              <input
                type="text"
                value={price.loading ? '...' : String(price.final)}
                readOnly
                style={{ flex: 1 }}
              />
              <button type="button" className="btn" onClick={() => copy(price.loading ? DEFAULT_PRICE : price.final)}>
                העתק
              </button>
            </div>
            {price.valid && price.discount_percent > 0 && (
              <small style={{ opacity: .85 }}>
                קופון “{price.coupon}” הופעל: הנחה {price.discount_percent}% ({price.base} → {price.final})
              </small>
            )}
            {!price.valid && email && (
              <small className="auth-hint">אין קופון פעיל למשתמש זה. מחיר בסיס: ₪{price.base}</small>
            )}
          </label>

          <label className="field">
            <div className="field__label">מספר bit לקבלת התשלום</div>
            <div className="field__control" style={{ display: 'flex', gap: 8 }}>
              <input type="text" value={BIT_PHONE} readOnly style={{ flex: 1 }} />
              <button type="button" className="btn" onClick={() => copy(BIT_PHONE)}>העתק</button>
            </div>
            {!BIT_PHONE && <small className="auth-hint">⚠️ לא הוגדר מספר bit ב־.env (VITE_BIT_PHONE)</small>}
          </label>

          {email && (
            <label className="field">
              <div className="field__label">המייל בחשבון</div>
              <div className="field__control" style={{ display: 'flex', gap: 8 }}>
                <input type="text" value={email} readOnly style={{ flex: 1 }} />
                <button type="button" className="btn" onClick={() => copy(email)}>העתק</button>
              </div>
              <small style={{ opacity: .85 }}>מומלץ לציין מייל בהערות התשלום כדי לזהות במהירות.</small>
            </label>
          )}

          {copied && <div className="auth-hint">הועתק: {copied}</div>}

          <div style={{ marginTop: 6, opacity: .9, fontSize: 14 }}>
            לאחר ביצוע התשלום, האקטיבציה מתבצעת ידנית. זמן האישור לרוב קצר—תקבלו גישה מלאה מהר מאוד.
          </div>
        </div>
      </div>
    </div>
  )
}
