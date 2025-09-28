// frontend/src/pages/Account.jsx
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function AccountPage() {
  const navigate = useNavigate()

  const token = useMemo(() => {
    try { return localStorage.getItem('token') || '' } catch { return '' }
  }, [])

  const API_BASE = useMemo(() => {
    const envUrl = import.meta.env.VITE_API_URL
    if (envUrl) return envUrl.replace(/\/+$/, '')
    const isHttps = typeof window !== 'undefined' && window.location.protocol === 'https:'
    const host = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1'
    return `${isHttps ? 'https' : 'http'}://${host}:8000/api`
  }, [])

  const [me, setMe] = useState(null)
  const [subs, setSubs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [plan, setPlan] = useState('monthly')
  const [renewBusy, setRenewBusy] = useState(false)

  useEffect(() => {
    if (!token) { navigate('/auth', { replace: true }); return }
    let abort = false
    async function load() {
      setLoading(true); setError('')
      try {
        const [meRes, subRes] = await Promise.all([
          fetch(`${API_BASE}/me`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_BASE}/subscriptions`, { headers: { Authorization: `Bearer ${token}` } }),
        ])
        if (!meRes.ok) throw new Error(await meRes.text())
        if (!subRes.ok) throw new Error(await subRes.text())
        const meData = await meRes.json()
        const subData = await subRes.json()
        if (abort) return
        setMe(meData)
        setSubs(Array.isArray(subData) ? subData : [])
      } catch (e) {
        if (!abort) setError(parseErr(e))
      } finally {
        if (!abort) setLoading(false)
      }
    }
    load()
    return () => { abort = true }
  }, [API_BASE, token, navigate])

  // --- מצבים ---
  const active = isActive(me?.active_until)
  const hasPendingAwaitingAdmin = useMemo(
    () => Array.isArray(subs) && subs.some(s => String(s?.status || '').toLowerCase() === 'pending'),
    [subs]
  )

  // UI state לפי הדרישות:
  const ui = useMemo(() => {
    if (hasPendingAwaitingAdmin) {
      return { status: 'ממתין לאישור אדמין', canBuy: false, hint: 'ממתין לאישור אדמין' }
    }
    if (active) {
      return { status: 'פעיל', canBuy: true, hint: '' }
    }
    return { status: 'פג תוקף', canBuy: true, hint: 'המנוי לא פעיל — יש להשלים תשלום.' }
  }, [hasPendingAwaitingAdmin, active])

  // ימים שנותרו (רק אם פעיל)
  const daysLeft = active ? remainingDays(me?.active_until) : null

  // --- רכישה/חידוש ---
  async function renew() {
    if (!token) return

    // אם יש ממתין – אל תבצע כלום (רק התראה)
    if (hasPendingAwaitingAdmin) {
      alert('יש הזמנה ממתינה לאישור אדמין. לא ניתן לבצע רכישה נוספת כרגע.')
      return
    }

    // אם פעיל – בקש אישור לצבירה
    if (active) {
      const ok = confirm('יש לך מנוי פעיל. האם להמשיך ולרכוש מנוי נוסף? (הזמן הנותר יצטבר)')
      if (!ok) return
    }

    setRenewBusy(true); setError('')
    try {
      const res = await fetch(`${API_BASE}/subscriptions/renew`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ plan }),
      })
      if (!res.ok) {
        if (res.status === 409) {
          alert('יש הזמנה ממתינה לאישור אדמין. לא ניתן לבצע רכישה נוספת כרגע.')
          return
        }
        const t = await res.text().catch(() => '')
        alert(t || `שגיאת שרת (${res.status})`)
        return
      }
      navigate('/pay', { replace: true })
    } finally {
      setRenewBusy(false)
    }
  }

  if (!token) return null

  return (
    <div className="container" style={{ paddingBlock: 24 }}>
      <div className="glass" style={{ padding: 22 }}>
        <h2 style={{ marginTop: 0 }}>איזור אישי</h2>
        {loading ? (
          <div className="auth-hint">טוען…</div>
        ) : error ? (
          <div className="auth-error">{error}</div>
        ) : (
          <>
            {/* User summary */}
            <section style={{ display:'grid', gap:12 }}>
              <h3 style={{ marginBottom: 6 }}>פרטי חשבון</h3>
              <div style={{ display:'grid', gridTemplateColumns:'repeat(2, minmax(220px, 1fr))', gap:12 }}>
                <Field label="שם">
                  {(me?.first_name || '') + ' ' + (me?.last_name || '')}
                </Field>
                <Field label="מייל">{me?.email}</Field>
                <Field label="טלפון">{me?.phone || '—'}</Field>
                <Field label="טלגרם">@{me?.telegram_username || ''}</Field>
              </div>

              <div className="glass" style={{ padding:16 }}>
                <div style={{ display:'grid', gap:10, gridTemplateColumns: 'repeat(3, minmax(180px, 1fr))' }}>
                  <Info label="סטטוס">{ui.status}</Info>
                  <Info label="תוקף">
                    {fmtDateOnly(me?.active_until)}
                    {daysLeft != null ? `  (נשארו ${daysLeft} ימים)` : ''}
                  </Info>
                  <Info label="קופון">{me?.coupon || '—'}</Info>
                </div>
              </div>
            </section>

            {/* Renew */}
            <section style={{ marginTop: 18 }}>
              <h3 style={{ marginBottom: 8 }}>חידוש מנוי</h3>
              <div className="glass" style={{ padding:16, display:'grid', gap:12 }}>
                <div style={{ display:'flex', flexWrap:'wrap', gap:12 }}>
                  <PlanRadio value="monthly" label="חודשי (30 יום)" plan={plan} setPlan={setPlan} />
                  <PlanRadio value="yearly"  label="שנתי (365 יום)" plan={plan} setPlan={setPlan} />
                  <PlanRadio value="pro"      label="Pro (חודשי)"  plan={plan} setPlan={setPlan} />
                </div>
                <div>
                  <button
                    className="btn btn--primary"
                    disabled={renewBusy || !ui.canBuy}
                    onClick={renew}
                    title={!ui.canBuy ? 'ממתין לאישור אדמין' : undefined}
                  >
                    {renewBusy ? 'יוצר חיוב…' : (active ? 'חדש מנוי' : 'רכש/חדש מנוי')}
                  </button>
                  {ui.hint && <span className="auth-hint" style={{ marginInlineStart: 12 }}>{ui.hint}</span>}
                </div>
              </div>
            </section>

            {/* History */}
            <section style={{ marginTop: 18 }}>
              <h3 style={{ marginBottom: 8 }}>היסטוריית חיובים</h3>
              <div className="glass" style={{ padding:0, overflow:'hidden', borderRadius: 12 }}>
                <table className="table-compact" style={{ width:'100%', borderCollapse:'separate', borderSpacing:0 }}>
                  <thead>
                    <tr>
                      <Th>מזהה</Th>
                      <Th>תוכנית</Th>
                      <Th>קופון</Th>
                      <Th>מחיר (₪)</Th>
                      <Th>התחלה</Th>
                      <Th>תפוגה</Th>
                      <Th>סטטוס</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {subs.map((r) => (
                      <tr key={r.id} className="tr-row">
                        <Td mono>{r.id}</Td>
                        <Td>{labelPlan(r.plan)}</Td>
                        <Td>{r.coupon || '—'}</Td>
                        <Td align="right">{fmtNum(r.price_nis)}</Td>
                        <Td>{fmtDateOnly(r.start_at)}</Td>
                        <Td>{fmtDateOnly(r.end_at)}</Td>
                        <Td>{labelStatus(r.status)}</Td>
                      </tr>
                    ))}
                    {subs.length === 0 && (
                      <tr><Td colSpan={7} align="center" dim>אין רשומות</Td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
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
function Info({ label, children }) {
  return (
    <div className="field">
      <div className="field__label">{label}</div>
      <div className="field__control">{children}</div>
    </div>
  )
}
function PlanRadio({ value, label, plan, setPlan }) {
  return (
    <label style={{ display:'inline-flex', alignItems:'center', gap:8 }}>
      <input type="radio" name="plan" value={value} checked={plan === value} onChange={() => setPlan(value)} />
      <span>{label}</span>
    </label>
  )
}
function Th({ children }) {
  return (
    <th style={{
      position:'sticky', top:0, background:'rgba(11,17,23,.8)', backdropFilter:'blur(4px)',
      textAlign:'start', padding:'10px 12px', borderBottom:'1px solid rgba(255,255,255,.12)'
    }}>{children}</th>
  )
}
function Td({ children, align='start', tone, mono, dim, colSpan }) {
  return (
    <td colSpan={colSpan} style={{
      textAlign: align, padding:'8px 12px', borderBottom:'1px solid rgba(255,255,255,.08)',
      fontFamily: mono ? 'ui-monospace, Menlo, Consolas, monospace' : undefined,
      opacity: dim ? .75 : 1,
      color: tone === 'up' ? '#2ecc71' : tone === 'down' ? '#e74c3c' : undefined
    }}>{children}</td>
  )
}

// -------- helpers --------
function labelPlan(p){ const v=String(p||'').toLowerCase(); if(v==='monthly')return'חודשי'; if(v==='yearly')return'שנתי'; if(v==='pro')return'Pro'; if(v==='basic')return'Basic'; return p||'—' }
function labelStatus(s){ const v=String(s||'').toLowerCase(); if(v==='active')return'פעיל'; if(v==='pending')return'ממתין'; if(v==='canceled')return'בוטל'; return s||'—' }

function fmtDateOnly(v){
  if(!v) return '—'
  try{
    const d = new Date(v)
    if(Number.isNaN(d.getTime())) return String(v)
    return d.toLocaleDateString('he-IL', { year:'numeric', month:'2-digit', day:'2-digit' })
  }catch{
    return String(v)
  }
}

function fmtNum(v){ return (v==null || v==='') ? '—' : Number(v).toFixed(2) }
function isActive(activeUntil){ if(!activeUntil) return false; try{ return new Date(activeUntil) > new Date() }catch{return false} }
function parseErr(e){ try{ const t = typeof e === 'string' ? e : (e.message || String(e)); const j = JSON.parse(t); return j.detail || t } catch { return e.message || String(e) } }

function remainingDays(activeUntil){
  if(!activeUntil) return null
  try{
    const end = new Date(activeUntil)
    const now = new Date()
    const ms = end.getTime() - now.getTime()
    if (ms <= 0) return 0
    return Math.floor(ms / (1000*60*60*24))
  }catch{
    return null
  }
}
