import { useEffect, useMemo, useState } from 'react'

/**
 * PositionsTable
 * - Fills its parent "window" (100% width/height) when height="100%" and wrapper is borderless.
 * - Use showHeader=false when parent already renders a header/tabs above.
 */
export default function PositionsTable({
  apiBase,
  limit = 10,
  height = '100%',
  showHeader = false,   // parent can hide the table's inner header
  borderless = true     // remove inner glass frame so table fills the window
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
    // fill the parent window
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
              <Th>תאריך</Th>
              <Th>מחיר</Th>
              <Th>% שינוי</Th>
              <Th>ווליום</Th>
              <Th>כיוון</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="tr-row">
                <Td mono>{r.symbol}</Td>
                <Td>{fmtDate(r.trade_date)}</Td>
                <Td align="right">{fmtNum(r.price)}</Td>
                <Td align="right" tone={tone(r.change_pct)}>{fmtPct(r.change_pct)}</Td>
                <Td align="right">{fmtInt(r.volume)}</Td>
                <Td tone={toneFromDir(r.direction)}>{labelDir(r.direction)}</Td>
              </tr>
            ))}
            {!loading && rows.length === 0 && (
              <tr><Td colSpan={6} align="center" dim>אין נתונים</Td></tr>
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

function fmtDate(v){ try{ return new Date(v).toLocaleString() }catch{ return String(v||'') } }
function fmtNum(v){ return v==null?'-': Number(v).toFixed(2) }
function fmtPct(v){ return v==null?'-': (Number(v)>=0?'+':'') + Number(v).toFixed(2) + '%' }
function fmtInt(v){ return v==null?'-': new Intl.NumberFormat().format(Number(v)) }
function tone(x){ if (x==null) return 'flat'; return Number(x) > 0 ? 'up' : Number(x) < 0 ? 'down' : 'flat' }
function toneFromDir(d){ if(!d) return 'flat'; const s=String(d).toLowerCase(); return s==='up'?'up':s==='down'?'down':'flat' }
function labelDir(d){ const t=toneFromDir(d); return t==='up'?'עליה': t==='down'?'ירידה':'—' }
