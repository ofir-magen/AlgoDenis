const { useEffect, useMemo, useState } = React
const API_BASE = '/api' // אותו מקור - אין צורך ב-.env לפרונט

function useAuth() {
  const [creds, setCreds] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem('admin_creds')) || null } catch { return null }
  })
  const isAuthed = !!(creds && creds.u && creds.p)
  const headers = useMemo(() => {
    if (!isAuthed) return {}
    const token = btoa(`${creds.u}:${creds.p}`)
    return { Authorization: `Basic ${token}` }
  }, [isAuthed, creds])

  async function login(u, p) {
    const token = btoa(`${u}:${p}`)
    const res = await fetch(`${API_BASE}/health`, { headers: { Authorization: `Basic ${token}` } })
    if (!res.ok) throw new Error('שם משתמש/סיסמה לא נכונים')
    const next = { u, p }
    setCreds(next)
    try { sessionStorage.setItem('admin_creds', JSON.stringify(next)) } catch {}
  }
  function logout() {
    setCreds(null)
    try { sessionStorage.removeItem('admin_creds') } catch {}
  }
  return { isAuthed, headers, login, logout }
}

async function apiFetch(path, headers, opts={}) {
  const res = await fetch(`${API_BASE}${path}`, { ...opts, headers: { ...(opts.headers||{}), ...headers } })
  if (!res.ok) {
    const txt = await res.text().catch(()=> '')
    const err = new Error(`HTTP ${res.status}: ${txt || res.statusText}`)
    err.status = res.status
    throw err
  }
  return res
}
async function getAllUsers(headers) {
  const res = await apiFetch('/users', headers)
  return res.json()
}
async function patchUser(headers, id, payload) {
  const res = await apiFetch(`/users/${id}`, headers, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  return res.json()
}

function Login({ onOk }) {
  const { login } = useAuth()
  const [u, setU] = useState('')
  const [p, setP] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(e) {
    e.preventDefault()
    setErr(''); setBusy(true)
    try { await login(u.trim(), p); onOk() }
    catch (e) { setErr(e.message || 'שגיאה בהתחברות') }
    finally { setBusy(false) }
  }
  return (
    <div className="card">
      <h2>התחברות מנהל</h2>
      <form onSubmit={submit}>
        <label className="field">
          <div>שם משתמש</div>
          <input dir="ltr" value={u} onChange={e=>setU(e.target.value)} required />
        </label>
        <label className="field">
          <div>סיסמה</div>
          <input dir="ltr" type="password" value={p} onChange={e=>setP(e.target.value)} required />
        </label>
        {err && <div className="error">{err}</div>}
        <button className="btn primary" disabled={busy}>{busy ? 'מתחבר…' : 'כניסה'}</button>
      </form>
    </div>
  )
}

function UsersTable() {
  const { headers, logout } = useAuth()
  const [data, setData] = useState({ total: 0, items: [] })
  const [busyId, setBusyId] = useState(null)
  const [err, setErr] = useState('')
  const [edit, setEdit] = useState({}) // { [id]: { field: value } }

  // חיפוש/סינון
  const [q, setQ] = useState('') // חיפוש חופשי
  const [approvedFilter, setApprovedFilter] = useState('all') // all | yes | no
  const [statusFilter, setStatusFilter] = useState('all') // all | active | expired
  const [dateFrom, setDateFrom] = useState('') // YYYY-MM-DD
  const [dateTo, setDateTo] = useState('')     // YYYY-MM-DD

  // מיון מרובה (מערך של {key, dir})
  const [sorts, setSorts] = useState([]) // dir: 'asc' | 'desc'

  async function load() {
    setErr('')
    try { setData(await getAllUsers(headers)) }
    catch (e) { setErr(e.message || 'שגיאה בטעינה') }
  }
  useEffect(() => { load() }, [])

  function onFieldChange(id, field, value) {
    setEdit(prev => ({ ...prev, [id]: { ...(prev[id]||{}), [field]: value } }))
  }

  async function onSaveRow(u) {
    const payload = { ...(edit[u.id] || {}) }
    if (payload.approved !== undefined) payload.approved = !!payload.approved
    if (payload.active_until) {
      const d = new Date(payload.active_until)
      if (!isNaN(d.getTime())) {
        payload.active_until = new Date(d.getTime() - d.getTimezoneOffset()*60000).toISOString()
      }
    }
    setBusyId(u.id)
    try {
      await patchUser(headers, u.id, payload)
      setEdit(prev => { const n = { ...prev }; delete n[u.id]; return n })
      await load()
    } catch (e) {
      alert('עדכון נכשל: ' + e.message)
    } finally { setBusyId(null) }
  }

  // ===== חישוב סינון מקומי =====
  const filteredItems = useMemo(() => {
    const now = new Date()
    const qn = normalize(q)

    const from = dateFrom ? new Date(`${dateFrom}T00:00:00`) : null
    const to   = dateTo   ? new Date(`${dateTo}T23:59:59.999`) : null

    return (data.items || []).filter(u => {
      // חיפוש חופשי
      if (qn) {
        const hay = [
          u.email || '',
          u.first_name || '',
          u.last_name || '',
          u.phone || '',
          u.telegram_username || ''
        ].map(normalize).join(' ')
        if (!hay.includes(qn)) return false
      }

      // סינון מאושר
      if (approvedFilter !== 'all') {
        const isApproved = !!u.approved
        if (approvedFilter === 'yes' && !isApproved) return false
        if (approvedFilter === 'no'  && isApproved)  return false
      }

      // סטטוס מנוי
      if (statusFilter !== 'all') {
        const au = u.active_until ? new Date(u.active_until) : null
        const isActive = !!(au && !isNaN(au.getTime()) && au >= now)
        if (statusFilter === 'active'  && !isActive) return false
        if (statusFilter === 'expired' && isActive)  return false
      }

      // טווח תאריכים לפי active_until
      if (from || to) {
        if (!u.active_until) return false
        const au = new Date(u.active_until)
        if (isNaN(au.getTime())) return false
        if (from && au < from) return false
        if (to   && au > to)   return false
      }

      return true
    })
  }, [data.items, q, approvedFilter, statusFilter, dateFrom, dateTo])

  // ===== מיון (מרובה עמודות) =====
  const sortedItems = useMemo(() => {
    if (!sorts.length) return filteredItems
    const arr = filteredItems.slice()
    arr.sort((a, b) => {
      for (const s of sorts) {
        const c = compareByKey(a, b, s.key, s.dir)
        if (c !== 0) return c
      }
      return 0
    })
    return arr
  }, [filteredItems, sorts])

  function getSortEntry(key) {
    const idx = sorts.findIndex(s => s.key === key)
    return idx === -1 ? null : { idx, ...sorts[idx] }
  }
  function toggleSort(key, multi=false) {
    setSorts(prev => {
      const existingIdx = prev.findIndex(s => s.key === key)
      let next = multi ? [...prev] : (existingIdx !== -1 ? [] : [])
      if (existingIdx === -1) {
        // לא קיים: הוסף ASC
        next.push({ key, dir: 'asc' })
      } else {
        const cur = prev[existingIdx]
        if (!multi) {
          // בסט יחיד: cycle asc->desc->remove
          if (cur.dir === 'asc') return [{ key, dir: 'desc' }]
          if (cur.dir === 'desc') return []
        } else {
          // במרובה: עדכן/הסר רק את הערך הזה
          if (cur.dir === 'asc') {
            next[existingIdx] = { key, dir: 'desc' }
          } else if (cur.dir === 'desc') {
            next.splice(existingIdx, 1) // הסרה
          }
          return next
        }
      }
      return next
    })
  }

  function sortLabel(key, title) {
    const entry = getSortEntry(key)
    if (!entry) return title
    const arrow = entry.dir === 'asc' ? '▲' : '▼'
    const order = entry.idx + 1
    return (<span>{title} <span className="sort-indicator">{arrow}<sup>{order}</sup></span></span>)
  }

  function onClearFilters() {
    setQ('')
    setApprovedFilter('all')
    setStatusFilter('all')
    setDateFrom('')
    setDateTo('')
  }

  return (
    <div className="wrap">
      <div className="toolbar">
        <h2>משתמשים</h2>
        <div className="spacer" />
        <button className="btn" onClick={logout}>התנתק</button>
      </div>

      {/* אזור סינון/חיפוש */}
      <div className="filters">
        <div className="filter-item">
          <label>חיפוש</label>
          <input
            dir="rtl"
            className="filter-input"
            placeholder="חיפוש… (מייל, שם, טלפון, טלגרם)"
            value={q}
            onChange={e=>setQ(e.target.value)}
          />
        </div>

        <div className="filter-item">
          <label>מאושר</label>
          <select className="filter-input" value={approvedFilter} onChange={e=>setApprovedFilter(e.target.value)}>
            <option value="all">הכול</option>
            <option value="yes">מאושר</option>
            <option value="no">לא מאושר</option>
          </select>
        </div>

        <div className="filter-item">
          <label>סטטוס</label>
          <select className="filter-input" value={statusFilter} onChange={e=>setStatusFilter(e.target.value)}>
            <option value="all">הכול</option>
            <option value="active">פעיל</option>
            <option value="expired">פג תוקף</option>
          </select>
        </div>

        <div className="filter-item">
          <label>תוקף מ־</label>
          <input type="date" className="filter-input" value={dateFrom} onChange={e=>setDateFrom(e.target.value)} />
        </div>

        <div className="filter-item">
          <label>תוקף עד</label>
          <input type="date" className="filter-input" value={dateTo} onChange={e=>setDateTo(e.target.value)} />
        </div>

        <div className="filters-actions">
          <div className="count">מציג {sortedItems.length} מתוך {data.total}</div>
          <div className="spacer" />
          <button className="btn" onClick={onClearFilters}>נקה סינון</button>
          <button className="btn" onClick={load} title="רענן מהשרת">רענן</button>
        </div>
      </div>

      {err && <div className="error">{err}</div>}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th className="sortable" onClick={(e)=>toggleSort('id', e.shiftKey)}>{sortLabel('id','ID')}</th>
              <th className="sortable" onClick={(e)=>toggleSort('email', e.shiftKey)}>{sortLabel('email','מייל')}</th>
              <th className="sortable" onClick={(e)=>toggleSort('first_name', e.shiftKey)}>{sortLabel('first_name','שם פרטי')}</th>
              <th className="sortable" onClick={(e)=>toggleSort('last_name', e.shiftKey)}>{sortLabel('last_name','שם משפחה')}</th>
              <th className="sortable" onClick={(e)=>toggleSort('phone', e.shiftKey)}>{sortLabel('phone','טלפון')}</th>
              <th className="sortable" onClick={(e)=>toggleSort('telegram_username', e.shiftKey)}>{sortLabel('telegram_username','טלגרם')}</th>
              <th className="sortable" onClick={(e)=>toggleSort('active_until', e.shiftKey)}>{sortLabel('active_until','תוקף')}</th>
              <th className="sortable" onClick={(e)=>toggleSort('approved', e.shiftKey)}>{sortLabel('approved','מאושר')}</th>
              <th>פעולה</th>
            </tr>
          </thead>
          <tbody>
            {sortedItems.map(u => (
              <tr key={u.id}>
                <td>{u.id}</td>
                <td dir="ltr">
                  <input className="small" defaultValue={u.email} onChange={e=>onFieldChange(u.id,'email',e.target.value)} />
                </td>
                <td>
                  <input className="small" placeholder="שם פרטי" defaultValue={u.first_name||''} onChange={e=>onFieldChange(u.id,'first_name',e.target.value)} />
                </td>
                <td>
                  <input className="small" placeholder="שם משפחה" defaultValue={u.last_name||''} onChange={e=>onFieldChange(u.id,'last_name',e.target.value)} />
                </td>
                <td dir="ltr">
                  <input className="small" defaultValue={u.phone||''} onChange={e=>onFieldChange(u.id,'phone',e.target.value)} />
                </td>
                <td dir="ltr">
                  <input className="small" defaultValue={u.telegram_username||''} onChange={e=>onFieldChange(u.id,'telegram_username',e.target.value)} />
                </td>
                <td dir="ltr">
                  <input
                    className="small"
                    type="datetime-local"
                    defaultValue={u.active_until ? toLocalInput(u.active_until) : ''}
                    onChange={e=>onFieldChange(u.id,'active_until',e.target.value)}
                  />
                </td>
                <td>
                  <input type="checkbox" defaultChecked={u.approved} onChange={e=>onFieldChange(u.id,'approved',e.target.checked)} />
                </td>
                <td>
                  <button className="btn primary" disabled={busyId===u.id} onClick={()=>onSaveRow(u)}>
                    {busyId===u.id ? 'שומר…' : 'עדכן'}
                  </button>
                </td>
              </tr>
            ))}
            {sortedItems.length === 0 && (
              <tr><td colSpan="9" style={{textAlign:'center', opacity:.7, padding:'14px'}}>אין תוצאות</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <p style={{marginTop:10, color:'var(--muted)'}}>טיפ: החזק <b>Shift</b> כדי להוסיף מיון לעמודה נוספת.</p>
    </div>
  )
}

function toLocalInput(iso) {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  const pad = n => String(n).padStart(2,'0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function normalize(s) {
  return String(s || '').toLowerCase().trim()
}

function compareByKey(a, b, key, dir='asc') {
  const av = getSortVal(a, key)
  const bv = getSortVal(b, key)

  // ערכים חסרים תמיד בסוף במיון עולה (ובתחילה במיון יורד)
  const aMissing = (av === null || av === undefined || av !== av) // NaN
  const bMissing = (bv === null || bv === undefined || bv !== bv)

  if (aMissing && bMissing) return 0
  if (aMissing) return dir === 'asc' ? 1 : -1
  if (bMissing) return dir === 'asc' ? -1 : 1

  let cmp = 0
  if (typeof av === 'number' && typeof bv === 'number') {
    cmp = av - bv
  } else if (av instanceof Date && bv instanceof Date) {
    cmp = av.getTime() - bv.getTime()
  } else {
    const as = String(av).toLowerCase()
    const bs = String(bv).toLowerCase()
    if (as > bs) cmp = 1
    else if (as < bs) cmp = -1
    else cmp = 0
  }
  return dir === 'asc' ? cmp : -cmp
}

function getSortVal(obj, key) {
  switch (key) {
    case 'id': return Number(obj.id) || 0
    case 'email': return obj.email || ''
    case 'first_name': return obj.first_name || ''
    case 'last_name': return obj.last_name || ''
    case 'phone': return obj.phone || ''
    case 'telegram_username': return obj.telegram_username || ''
    case 'approved': return obj.approved ? 1 : 0
    case 'active_until':
      if (!obj.active_until) return null
      const d = new Date(obj.active_until)
      return isNaN(d.getTime()) ? null : d
    default:
      return obj[key]
  }
}

function App() {
  const [authed, setAuthed] = useState(false)
  return authed ? <UsersTable /> : <Login onOk={()=>setAuthed(true)} />
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />)
