// frontend/src/pages/Dashboard.jsx
import React, { useEffect, useMemo, useState } from 'react'
import { authedGet, logout } from '../api.js'
import { useNavigate } from 'react-router-dom'

export default function Dashboard() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [partnerEmail, setPartnerEmail] = useState('')
  const [coupons, setCoupons] = useState([])
  const [columns, setColumns] = useState([]) // always from backend
  const [rows, setRows] = useState([])       // users that used partner's coupons
  const navigate = useNavigate()

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError('')
      try {
        const me = await authedGet('/me')
        if (cancelled) return
        setPartnerEmail(me.email || '')

        const data = await authedGet('/dashboard/aff-users')
        if (cancelled) return
        setCoupons(Array.isArray(data.coupons) ? data.coupons : [])
        setColumns(Array.isArray(data.columns) ? data.columns : [])
        setRows(Array.isArray(data.users) ? data.users : [])
      } catch (e) {
        setError(e.message || 'Failed loading dashboard')
        logout()
        navigate('/login')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  // If backend returned no columns (shouldn't happen), derive from first row as fallback
  const displayColumns = useMemo(() => {
    if (columns && columns.length) return columns
    if (rows && rows.length) return Object.keys(rows[0])
    return []
  }, [columns, rows])

  return (
    <div className="container">
      <div className="card" style={{width:'100%', maxWidth: 'min(1100px, 95vw)'}}>
        <h2 style={{textAlign:'center'}}>דאשבורד שותף</h2>

        <div className="helper" style={{textAlign:'center', marginBottom:12}}>
          {partnerEmail ? `שותף מחובר: ${partnerEmail}` : '...'}
        </div>
        <div className="helper" style={{textAlign:'center', marginBottom:12}}>
          {coupons.length ? `קופונים שלך: ${coupons.join(', ')}` : 'אין קופונים משויכים'}
        </div>

        {loading && <div className="helper">טוען נתונים...</div>}
        {error && <div className="helper" style={{color:'var(--danger)'}}>{error}</div>}

        {!loading && !error && (
          <div style={{overflowX:'auto'}}>
            <table style={{width:'100%', borderCollapse:'collapse'}}>
              <thead>
                <tr>
                  {displayColumns.map(col => (
                    <th key={col} style={{textAlign:'right', padding:'8px 6px', borderBottom:'1px solid var(--stroke)'}}>
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  // Empty body (headers still visible)
                  <tr>
                    <td colSpan={Math.max(1, displayColumns.length)} style={{padding:'12px 6px', textAlign:'center', color:'var(--txt-dim)'}}>
                      לא נמצאו משתמשים שהשתמשו בקופונים שלך.
                    </td>
                  </tr>
                ) : (
                  rows.map((r, i) => (
                    <tr key={i} style={{borderBottom:'1px solid var(--stroke)'}}>
                      {displayColumns.map(col => (
                        <td key={col} style={{padding:'8px 6px', fontSize:14}}>
                          {r[col] === null || r[col] === undefined ? '' : String(r[col])}
                        </td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}

        <div style={{display:'flex', gap:8, justifyContent:'center', marginTop:16}}>
          <button className="button" onClick={() => { logout(); navigate('/login'); }}>
            התנתקות
          </button>
        </div>
      </div>
    </div>
  )
}
