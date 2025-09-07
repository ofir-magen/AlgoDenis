// frontend/src/pages/Pay.jsx
import { useMemo, useState } from 'react'

export default function Pay() {
  // ENV (ערוך ב-frontend/.env)
  const BIT_PHONE = import.meta.env.VITE_BIT_PHONE || ''
  const PRICE_NIS = import.meta.env.VITE_SUB_PRICE_NIS || '49'
  // כתובת תמונת ה-QR: או מ-.env או מקובץ סטטי ב-public/bit-qr.png
  const QR_URL = import.meta.env.VITE_BIT_QR_URL || '/bit-qr.png'

  // אימייל לחשבון (נשמר אחרי הרשמה/כניסה)
  const email = useMemo(() => {
    try { return localStorage.getItem('user_email') || '' } catch { return '' }
  }, [])

  const [copied, setCopied] = useState('')
  const copy = async (txt) => {
    try { await navigator.clipboard.writeText(txt); setCopied(txt) } catch {}
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
              <input type="text" value={PRICE_NIS} readOnly style={{ flex: 1 }} />
              <button type="button" className="btn" onClick={() => copy(PRICE_NIS)}>העתק</button>
            </div>
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
