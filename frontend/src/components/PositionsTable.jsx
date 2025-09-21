// frontend/src/components/PositionsTable.jsx
import { useEffect, useMemo, useState } from 'react'

/**
 * PositionsTable
 * תואם לסכמה:
 * symbol, signal_type, entry_time, entry_price, exit_time, exit_price, change_pct
 * (תואם לאחור גם ל-entry_date/exit_date)
 */
export default function PositionsTable({
  apiBase,
  limit = 10,
  height = '100%',
  showHeader = false,
  borderless = true
}) {
  const API_BASE = useMemo(() => {
    if (apiBase) return apiBase.replace(/\/+$/, '')
    const envUrl = import.meta.env.VITE_API_URL
    if (envUrl) return envUrl.replace(/\/+$/, '')
    const isHttps = typeof window !== 'undefined' && window.location.protocol === 'https:'
    const host = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1'
    return `${isHttps ? 'https' : 'http'}://${host}:8000/api`
  }, [apiBase])

  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let abort = false
    async function load() {
      setLoading(true); setError('')
      try {
        const res = await fetch(`${API_BASE}/positions/recent?limit=${limit}`)
        if (!res.ok) throw new Error('Failed to fetch positions')
        const data = await res.json()
        if (!abort) setRows(Array.isArray(data) ? data : [])
      } catch (e) {
        if (!abort) setError(e.message || 'Load error')
      } finally {
        if (!abort) setLoading(false)
      }
    }
    load()
    return () => { abort = true }
  }, [API_BASE, limit])

  const containerStyle = {
    width: '100%',
    height,
    display: 'flex',
    flexDirection: 'column',
    ...(borderless ? {} : { padding: 12, borderRadius: 12 })
  }

  const tableWrapStyle = {
    flex: 1,
    minHeight: 0,
    overflow: 'auto',
    borderRadius: 12,
    border: '1px solid rgba(255,255,255,.12)'
  }

  return (
    <div style={containerStyle}>
      {showHeader && (
        <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:8 }}>
          <h3 style={{ margin: 0 }}>פוזיציות אחרונות</h3>
          <small style={{ opacity:.8 }}>(TOP {limit})</small>
          {loading && <span style={{ marginInlineStart: 'auto', fontSize: 12, opacity:.8 }}>טוען…</span>}
        </div>
      )}

      {error && <div className="auth-error" style={{ marginBottom: 8 }}>{error}</div>}

      <div style={tableWrapStyle}>
        <table className="table-compact" style={{ width:'100%', borderCollapse:'separate', borderSpacing:0 }}>
          <thead>
            <tr>
              <Th>סימבול</Th>
              <Th>סוג איתות</Th>
              <Th>כניסה</Th>
              <Th>מחיר כניסה</Th>
              <Th>יציאה</Th>
              <Th>מחיר יציאה</Th>
              <Th>% שינוי</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              // תאימות לשני שמות השדות
              const entryTs = r.entry_time ?? r.entry_date
              const exitTs  = r.exit_time  ?? r.exit_date
              return (
                <tr key={i} className="tr-row">
                  <Td mono>{r.symbol}</Td>
                  <Td>{labelSignal(r.signal_type)}</Td>
                  <Td>{fmtDate(entryTs)}</Td>
                  <Td align="right">{fmtNum(r.entry_price)}</Td>
                  <Td>{fmtDate(exitTs)}</Td>
                  <Td align="right">{fmtNum(r.exit_price)}</Td>
                  <Td align="right" tone={tone(r.change_pct)}>{fmtPct(r.change_pct)}</Td>
                </tr>
              )
            })}
            {!loading && rows.length === 0 && (
              <tr><Td colSpan={7} align="center" dim>אין נתונים</Td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
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

function labelSignal(s){
  const v=String(s||'').toLowerCase()
  if(v==='long') return 'לונג'
  if(v==='short') return 'שורט'
  if(v==='hold') return 'החזק'
  // אם זה BUY/SELL/NONE נשאיר כמו שהוא
  return s || '—'
}

/* פרסינג תאריך/שעה סלחני (תומך ב-"2025-09-21T15:00:00" וגם "2025-09-21 15:00") */
function fmtDate(v){
  if (v == null || v === '') return '—'
  const s = String(v).trim()
  // אם התקבל טיים-סטמפ מספרי
  if (/^\d{10,13}$/.test(s)) {
    const ms = s.length === 13 ? Number(s) : Number(s) * 1000
    const d = new Date(ms)
    return isNaN(d.getTime()) ? s : d.toLocaleString('he-IL', { hour12: false })
  }
  const withT = s.includes('T') ? s : s.replace(' ', 'T')
  const withSec = /\d{2}:\d{2}:\d{2}$/.test(withT) ? withT : (/\d{2}:\d{2}$/.test(withT) ? withT + ':00' : withT)
  const d = new Date(withSec)
  if (!isNaN(d.getTime())) return d.toLocaleString('he-IL', { hour12: false })
  return s
}

function fmtNum(v){ return (v==null || v==='') ? '—' : Number(v).toFixed(2) }
function fmtPct(v){ return (v==null || v==='') ? '—' : (Number(v)>=0?'+':'') + Number(v).toFixed(2) + '%' }
function tone(x){ if (x==null || x==='') return 'flat'; return Number(x) > 0 ? 'up' : Number(x) < 0 ? 'down' : 'flat' }
