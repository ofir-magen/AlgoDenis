// src/pages/UsersPage.jsx
import React, { useEffect, useMemo, useState } from 'react'

const API = import.meta.env.VITE_ADMIN_API

function apiFetch(path, init = {}) {
  const token = localStorage.getItem('admin_token')
  return fetch(`${API}${path}`, {
    ...init,
    headers: {
      ...(init.headers || {}),
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })
}

// כותרות ידידותיות לעמודות
const LABELS = {
  id: 'ID',
  first_name: 'שם פרטי',
  last_name: 'שם משפחה',
  email: 'מייל',
  telegram_username: 'טלגרם',
  phone: 'טלפון',
  approved: 'מאושר',
  affiliator: 'שותף',
  active_until: 'תוקף',
  created_at: 'נוצר',
  updated_at: 'עודכן',
  coupon: 'קופון',
  price_nis: 'מחיר (₪)',
  affiliateor_of: 'Affiliateor Of',
}

// עמודות בסיס שיופיעו (אם קיימות במידע)
const BASE_COLUMNS = [
  'id',
  'first_name',
  'last_name',
  'email',
  'telegram_username',
  'phone',
  'approved',
  'active_until',
  'created_at',
  'updated_at',
  'coupon',
  'price_nis',
  'affiliator',
  'affiliateor_of',
]

// שדות שלא מציגים בטבלה
const EXCLUDE = new Set(['password', 'username', 'password_hash', 'token'])

// שדות שלא מעדכנים לעולם
const IMMUTABLE = new Set(['id', 'created_at', 'password_hash', 'timestamp'])

function formatDateTime(s) {
  if (!s) return ''
  const isoLike = String(s).replace(' ', 'T')
  const d = new Date(isoLike)
  if (isNaN(d.getTime())) return String(s)
  return d.toLocaleString('he-IL', { hour12: false })
}

function toDatetimeLocalValue(s) {
  if (!s) return ''
  const isoLike = String(s).replace(' ', 'T')
  const d = new Date(isoLike)
  if (isNaN(d.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  const yyyy = d.getFullYear()
  const mm = pad(d.getMonth() + 1)
  const dd = pad(d.getDate())
  const hh = pad(d.getHours())
  const mi = pad(d.getMinutes())
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}`
}

export default function UsersPage() {
  const [err, setErr] = useState('')
  const [rows, setRows] = useState([])
  const [filter, setFilter] = useState('')
  const [sorters, setSorters] = useState([])

  const [editRowId, setEditRowId] = useState(null)
  const [editDraft, setEditDraft] = useState({})

  async function load() {
    setErr('')
    try {
      const res = await apiFetch('/users')
      if (res.status === 401) {
        localStorage.removeItem('admin_token')
        window.location.href = '/login'
        return
      }
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setRows(Array.isArray(data) ? data : [])
    } catch (e) {
      setErr(String(e.message || e))
    }
  }

  const columns = useMemo(() => {
    const set = new Set(BASE_COLUMNS)
    for (const r of rows) {
      for (const k of Object.keys(r || {})) {
        if (!EXCLUDE.has(k) && !set.has(k)) set.add(k)
      }
    }
    return Array.from(set)
  }, [rows])

  const filtered = useMemo(() => {
    const q = (filter || '').toLowerCase().trim()
    if (!q) return rows
    return rows.filter(r =>
      Object.entries(r ?? {}).some(([k, v]) => {
        if (EXCLUDE.has(k)) return false
        return String(v ?? '').toLowerCase().includes(q)
      })
    )
  }, [rows, filter])

  const sorted = useMemo(() => {
    if (!sorters.length) return filtered
    const arr = [...filtered]
    arr.sort((a, b) => {
      for (const s of sorters) {
        const av = a?.[s.key]
        const bv = b?.[s.key]
        let cmp
        if (s.key === 'active_until' || s.key === 'created_at') {
          const ad = new Date(String(av || '').replace(' ', 'T')).getTime() || 0
          const bd = new Date(String(bv || '').replace(' ', 'T')).getTime() || 0
          cmp = ad === bd ? 0 : ad < bd ? -1 : 1
        } else if (!isNaN(Number(av)) && !isNaN(Number(bv))) {
          const an = Number(av), bn = Number(bv)
          cmp = an === bn ? 0 : an < bn ? -1 : 1
        } else {
          cmp = String(av ?? '').localeCompare(String(bv ?? ''), 'he', { numeric: true, sensitivity: 'base' })
        }
        if (cmp !== 0) return s.dir === 'desc' ? -cmp : cmp
      }
      return 0
    })
    return arr
  }, [filtered, sorters])

  function toggleSort(key) {
    setSorters(prev => {
      const idx = prev.findIndex(s => s.key === key)
      if (idx === -1) return [...prev, { key, dir: 'asc' }]
      const cur = prev[idx]
      if (cur.dir === 'asc') {
        const next = [...prev]; next[idx] = { key, dir: 'desc' }; return next
      }
      const next = [...prev]; next.splice(idx, 1); return next
    })
  }

  function sorterIndicator(key) {
    const i = sorters.findIndex(s => s.key === key)
    if (i === -1) return ''
    return sorters[i].dir === 'asc' ? ' ↑' : ' ↓'
  }

  function beginEdit(r) {
    setEditRowId(r.id)
    setEditDraft({ ...r })
  }
  function cancelEdit() {
    setEditRowId(null)
    setEditDraft({})
  }
  function changeDraft(key, val) {
    setEditDraft(d => ({ ...d, [key]: val }))
  }

  async function saveEdit() {
    if (editRowId == null) return
    setErr('')
    try {
      const payload = { ...editDraft }
      for (const k of Object.keys(payload)) {
        if (IMMUTABLE.has(k) || EXCLUDE.has(k)) delete payload[k]
      }

      // נרמול approved -> boolean
      if ('approved' in payload) {
        payload.approved =
          payload.approved === true ||
          payload.approved === '1' ||
          payload.approved === 1 ||
          payload.approved === 'כן'
      }

      // נרמול affiliator -> boolean
      if ('affiliator' in payload) {
        payload.affiliator =
          payload.affiliator === true ||
          payload.affiliator === '1' ||
          payload.affiliator === 1 ||
          payload.affiliator === 'כן'
      }

      // נרמול active_until לפורמט "YYYY-MM-DD HH:MM:SS"
      if ('active_until' in payload && payload.active_until) {
        const v = String(payload.active_until).trim()
        if (v.includes('T')) {
          const withSeconds = /\d{2}:\d{2}:\d{2}$/.test(v) ? v : (v + ':00')
          payload.active_until = withSeconds.replace('T', ' ')
        }
      }

      // המרה של מחרוזות ריקות ל-NULL
      for (const key of ['coupon', 'affiliateor_of', 'username', 'telegram_username', 'phone', 'first_name', 'last_name']) {
        if (key in payload && String(payload[key]).trim() === '') payload[key] = null
      }

      if ('price_nis' in payload) {
        const v = String(payload.price_nis).trim()
        payload.price_nis = v === '' ? null : Number(v)
      }

      const res = await apiFetch(`/users/${editRowId}`, {
        method: 'PUT',
        body: JSON.stringify({ data: payload }),
      })
      if (res.status === 401) {
        localStorage.removeItem('admin_token'); window.location.href = '/login'; return
      }
      if (!res.ok) throw new Error(await res.text())

      await load()
      cancelEdit()
    } catch (e) {
      setErr(String(e.message || e))
    }
  }

  async function delRow(id) {
    if (!confirm('למחוק משתמש זה?')) return
    setErr('')
    try {
      const res = await apiFetch(`/users/${id}`, { method: 'DELETE' })
      if (res.status === 401) {
        localStorage.removeItem('admin_token'); window.location.href = '/login'; return
      }
      if (!res.ok) throw new Error(await res.text())
      await load()
    } catch (e) {
      setErr(String(e.message || e))
    }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="admin-shell">
      {/* סרגל משנה לעמוד משתמשים: רענון + חיפוש + ספירה */}
      <div className="topbar" style={{ marginTop: 12 }}>
        <div className="left">
          <button className="btn-secondary" onClick={load}>רענן</button>
          <input
            className="search"
            placeholder="חיפוש בכל השדות…"
            value={filter}
            onChange={e => setFilter(e.target.value)}
          />
        </div>
        <div className="right">
          <span className="pill">סה״כ: {rows.length}</span>
        </div>
      </div>

      {err ? <div className="alert" style={{ margin: '12px auto' }}>{err}</div> : null}

      <div className="table-wrap">
        <table className="users">
          <thead>
            <tr>
              {columns.map(key => (
                <th key={key} onClick={() => toggleSort(key)}>
                  {LABELS[key] || key}{sorterIndicator(key)}
                </th>
              ))}
              <th>פעולות</th>
            </tr>
          </thead>
          <tbody>
            {(rows.length === 0) ? (
              <tr><td colSpan={columns.length + 1} className="muted">אין נתונים</td></tr>
            ) : (
              sorted.map(r => {
                const isEditing = editRowId === r.id
                return (
                  <tr key={r.id}>
                    {columns.map(key => {
                      const val = isEditing ? editDraft?.[key] : r?.[key]

                      if (key === 'approved') {
                        return (
                          <td key={key}>
                            {isEditing ? (
                              <select
                                className="cell-input"
                                value={(val ? '1' : '0')}
                                onChange={e => changeDraft('approved', e.target.value === '1')}
                              >
                                <option value="0">לא</option>
                                <option value="1">כן</option>
                              </select>
                            ) : (r.approved ? 'כן' : 'לא')}
                          </td>
                        )
                      }

                      if (key === 'affiliator') {
                        return (
                          <td key={key}>
                            {isEditing ? (
                              <select
                                className="cell-input"
                                value={(val ? '1' : '0')}
                                onChange={e => changeDraft('affiliator', e.target.value === '1')}
                              >
                                <option value="0">לא</option>
                                <option value="1">כן</option>
                              </select>
                            ) : (r.affiliator ? 'כן' : 'לא')}
                          </td>
                        )
                      }

                      if (key === 'active_until') {
                        return (
                          <td key={key}>
                            {isEditing ? (
                              <input
                                type="datetime-local"
                                className="cell-input"
                                value={toDatetimeLocalValue(val)}
                                onChange={e => changeDraft('active_until', e.target.value)}
                              />
                            ) : formatDateTime(r.active_until)}
                          </td>
                        )
                      }

                      if (key === 'price_nis') {
                        return (
                          <td key={key}>
                            {isEditing ? (
                              <input
                                type="number"
                                step="0.01"
                                min="0"
                                className="cell-input"
                                value={val ?? ''}
                                onChange={e => changeDraft('price_nis', e.target.value)}
                              />
                            ) : (val == null ? '' : String(val))}
                          </td>
                        )
                      }

                      return (
                        <td key={key}>
                          {isEditing ? (
                            IMMUTABLE.has(key) ? (
                              <span>{String(val ?? '')}</span>
                            ) : (
                              <input
                                className="cell-input"
                                value={val ?? ''}
                                onChange={e => changeDraft(key, e.target.value)}
                              />
                            )
                          ) : String(val ?? '')}
                        </td>
                      )
                    })}
                    <td className="actions">
                      {isEditing ? (
                        <>
                          <button className="btn-primary sm" onClick={saveEdit}>שמור</button>
                          <button className="btn-secondary sm" onClick={cancelEdit}>בטל</button>
                        </>
                      ) : (
                        <>
                          <button className="btn-primary sm" onClick={() => beginEdit(r)}>ערוך</button>
                          <button className="btn-danger sm" onClick={() => delRow(r.id)}>מחק</button>
                        </>
                      )}
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
