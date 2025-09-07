import React, { useEffect, useMemo, useState } from 'react'

const API = import.meta.env.VITE_ADMIN_API

function apiFetch(path, { auth, ...init } = {}) {
  return fetch(`${API}${path}`, {
    ...init,
    headers: {
      ...(init.headers || {}),
      ...(auth ? { Authorization: `Basic ${auth}` } : {}),
      ...(init.body ? { 'Content-Type': 'application/json' } : {})
    }
  })
}

export default function App() {
  const [auth, setAuth] = useState(() => localStorage.getItem('admin_auth') || '')
  const [u, setU] = useState('')
  const [p, setP] = useState('')
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)
  const [rows, setRows] = useState([])
  const [q, setQ] = useState('')
  const [sorts, setSorts] = useState([]) // [{key:'first_name', dir:'asc'}]

  useEffect(() => {
    if (!auth) return
    load()
  }, [auth])

  async function login(e) {
    e.preventDefault()
    setErr('')
    const token = btoa(`${u}:${p}`)
    try {
      const res = await apiFetch('/health', { auth: token })
      if (res.ok) {
        localStorage.setItem('admin_auth', token)
        setAuth(token)
      } else {
        setErr('שם משתמש או סיסמה שגויים')
      }
    } catch (e) {
      setErr(String(e))
    }
  }

  function logout() {
    localStorage.removeItem('admin_auth')
    setAuth('')
    setRows([])
  }

  async function load() {
    setLoading(true); setErr('')
    try {
      const res = await apiFetch('/users', { auth })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setRows(data || [])
    } catch (e) {
      setErr(String(e))
    } finally {
      setLoading(false)
    }
  }

  async function updateRow(r) {
    try {
      const res = await apiFetch(`/users/${r.id}`, { auth, method: 'PUT', body: JSON.stringify(r) })
      if (!res.ok) throw new Error(await res.text())
    } catch (e) {
      alert('נכשל בעדכון: ' + e.message)
    }
  }

  async function deleteRow(id) {
    if (!confirm('למחוק משתמש?')) return
    try {
      const res = await apiFetch(`/users/${id}`, { auth, method: 'DELETE' })
      if (!res.ok) throw new Error(await res.text())
      setRows(rows.filter(x => x.id !== id))
    } catch (e) {
      alert('נכשל במחיקה: ' + e.message)
    }
  }

  // --- חיפוש ---
  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase()
    if (!t) return rows
    return rows.filter(r =>
      Object.values(r).some(v => String(v ?? '').toLowerCase().includes(t))
    )
  }, [rows, q])

  // --- מיון: לחץ רגיל = מיון יחיד; Shift-Click = הוספה/החלפה בשרשרת ---
  function toggleSort(key, multi) {
    setSorts(prev => {
      const idx = prev.findIndex(s => s.key === key)
      if (!multi) {
        // מיון יחיד
        if (idx === -1) return [{ key, dir: 'asc' }]
        const dir = prev[idx].dir === 'asc' ? 'desc' : 'asc'
        return [{ key, dir }]
      } else {
        // Multi-sort
        const next = [...prev]
        if (idx === -1) next.push({ key, dir: 'asc' })
        else {
          next[idx] = { key, dir: next[idx].dir === 'asc' ? 'desc' : 'asc' }
        }
        return next
      }
    })
  }

  const sorted = useMemo(() => {
    if (!sorts.length) return filtered
    const copy = [...filtered]
    copy.sort((a, b) => {
      for (const { key, dir } of sorts) {
        const av = norm(a[key]), bv = norm(b[key])
        if (av < bv) return dir === 'asc' ? -1 : 1
        if (av > bv) return dir === 'asc' ? 1 : -1
      }
      return 0
    })
    return copy
  }, [filtered, sorts])

  function norm(v) {
    if (v == null) return ''
    // תאריך למיון טבעי
    if (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}/.test(v)) return v
    return String(v).toLowerCase()
  }

  if (!auth) {
    return (
      <div className="container" style={{maxWidth: 420, paddingTop: 80}}>
        <div className="card" style={{padding: 24}}>
          <h2 style={{marginTop: 0, marginBottom: 8}}>כניסה למערכת ניהול</h2>
          <p style={{marginTop: 0, color: 'var(--muted)'}}>הזן שם משתמש וסיסמה</p>
          <form onSubmit={login} className="vstack" style={{marginTop: 12}}>
            <input className="input" placeholder="שם משתמש" value={u} onChange={e=>setU(e.target.value)} />
            <input className="input" type="password" placeholder="סיסמה" value={p} onChange={e=>setP(e.target.value)} />
            <button className="btn btn-primary" type="submit">כניסה</button>
          </form>
          {err && <p style={{color:'#ff99a3', marginTop:12}}>{err}</p>}
        </div>
      </div>
    )
  }

  return (
    <div className="container" style={{paddingTop: 22}}>
      <div className="card">
        <div className="header">
          <div className="hstack">
            <strong style={{fontSize: 18}}>טבלת משתמשים</strong>
            <span className="badge">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="#4da3ff"><path d="M19 4h-14c-1.1 0-2 .9-2 2v12a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-12a2 2 0 0 0-2-2zm0 14h-14v-9h14v9zm-9-8h-3v3h3v-3z"/></svg>
              {rows.length} משתמשים
            </span>
          </div>
          <div className="hstack">
            <input className="input" placeholder="חיפוש בכל השדות…" value={q} onChange={e=>setQ(e.target.value)} />
            <button className="btn" onClick={load} disabled={loading}>{loading ? 'טוען…' : 'רענן'}</button>
            <button className="btn btn-ghost" onClick={logout}>התנתק</button>
          </div>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {header('id','ID')}
                {header('email','מייל')}
                {header('first_name','שם פרטי')}
                {header('last_name','שם משפחה')}
                {header('phone','טלפון')}
                {header('telegram_username','טלגרם')}
                {header('active_until','תוקף')}
                {header('approved','מאושר')}
                <th>פעולות</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map(r => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <Cell value={r.email} onChange={v=>set(r,'email',v)} />
                  <Cell value={r.first_name} onChange={v=>set(r,'first_name',v)} />
                  <Cell value={r.last_name} onChange={v=>set(r,'last_name',v)} />
                  <Cell value={r.phone} onChange={v=>set(r,'phone',v)} />
                  <Cell value={r.telegram_username} onChange={v=>set(r,'telegram_username',v)} />
                  <td>
                    <input
                      className="cell-input"
                      type="date"
                      value={(r.active_until ?? '').slice(0,10)}
                      onChange={e=>set(r,'active_until',e.target.value)}
                    />
                  </td>
                  <td style={{textAlign:'center'}}>
                    <input className="checkbox" type="checkbox" checked={!!r.approved} onChange={e=>set(r,'approved',e.target.checked)} />
                  </td>
                  <td style={{whiteSpace:'nowrap'}}>
                    <button className="btn" onClick={()=>updateRow(r)}>עדכן</button>{' '}
                    <button className="btn btn-danger" onClick={()=>deleteRow(r.id)}>מחק</button>
                  </td>
                </tr>
              ))}
              {sorted.length === 0 && (
                <tr><td colSpan="9" style={{padding: 18, color:'var(--muted)', textAlign:'center'}}>אין נתונים</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div style={{padding: '10px 16px', color:'var(--muted)', fontSize: 12}}>
          טיפ: למיון לפי כמה עמודות יחד – החזק <span className="kbd">Shift</span> ולחץ על כותרת העמודה.
        </div>
      </div>
    </div>
  )

  function set(obj, k, v) {
    obj[k] = v
    setRows([...rows])
  }

  function header(key, label) {
    const active = sorts.findIndex(s => s.key === key)
    const dir = active >= 0 ? sorts[active].dir : null
    return (
      <th
        onClick={(e)=>toggleSort(key, e.shiftKey)}
        style={{cursor:'pointer', userSelect:'none'}}
        title={active>=0 ? `מיקום מיון: ${active+1} (${dir==='asc'?'עולה':'יורד'})` : 'לחץ למיון, Shift ללמיון מרובה'}
      >
        {label}
        {active>=0 && <span className="sort">{dir==='asc'?'▲':'▼'}{sorts.length>1?` ${active+1}`:''}</span>}
      </th>
    )
  }
}

function Cell({ value, onChange }) {
  return (
    <td>
      <input className="cell-input" value={value ?? ''} onChange={e=>onChange(e.target.value)} />
    </td>
  )
}
