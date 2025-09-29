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

// --- Utilities ---
const EXCLUDE = new Set(['password', 'username', 'password_hash', 'token'])
const IMMUTABLE = new Set(['id', 'created_at', 'password_hash', 'timestamp'])

function formatDateOnly(s) {
  if (!s) return ''
  // תמיכה גם ב-Date וגם במחרוזת
  const d = (s instanceof Date) ? s : new Date(String(s).replace(' ', 'T'))
  if (isNaN(d.getTime())) return String(s)
  return d.toLocaleDateString('he-IL') // תאריך בלבד
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

// חישוב “ימים שנותרו” לפי active_until המאוחד (המאוחר ביותר) מבין רשומות מאושרות
function computeUnifiedActiveUntilAndDaysLeft(rows) {
  const times = (rows || [])
    .filter(r => r.approved && r.active_until)
    .map(r => new Date(String(r.active_until).replace(' ', 'T')).getTime())
    .filter(t => Number.isFinite(t))
  if (!times.length) return { unifiedActiveUntil: null, daysLeft: 0 }
  const maxTs = Math.max(...times)
  const now = Date.now()
  const diffMs = maxTs - now
  const daysLeft = diffMs > 0 ? Math.ceil(diffMs / (1000 * 60 * 60 * 24)) : 0
  return { unifiedActiveUntil: new Date(maxTs), daysLeft }
}

// בחירה של “רשומה מסכמת אחרונה” לקידמת הבמה:
// 1) אם יש pending/approved=false -> אחרונה (לפי created_at)
// 2) אחרת הרשומה עם active_until המאוחר
// 3) אחרת לפי created_at המאוחר
function pickSummaryRow(list) {
  if (!list?.length) return null
  const byCreated = [...list].sort((a, b) => {
    const ta = new Date(String(a.created_at || a.id || 0).toString().replace(' ', 'T')).getTime() || 0
    const tb = new Date(String(b.created_at || b.id || 0).toString().replace(' ', 'T')).getTime() || 0
    return tb - ta
  })
  const pending = byCreated.find(r => r.approved === false || String(r.status || '').toLowerCase() === 'pending')
  if (pending) return pending

  const byUnified = [...list].sort((a, b) => {
    const ta = new Date(String(a.active_until || 0).toString().replace(' ', 'T')).getTime() || 0
    const tb = new Date(String(b.active_until || 0).toString().replace(' ', 'T')).getTime() || 0
    return tb - ta
  })
  if (byUnified[0]) return byUnified[0]

  return byCreated[0]
}

// סטטוס מסוכם: אם יש pending -> "ממתין"; אחרת אם daysLeft>0 -> "פעיל"; אחרת "לא פעיל"
function summarizeStatus(rows, daysLeft) {
  const hasPending = (rows || []).some(r => r.approved === false || String(r.status || '').toLowerCase() === 'pending')
  if (hasPending) return 'ממתין'
  if (daysLeft > 0) return 'פעיל'
  return 'לא פעיל'
}

// --- Component ---
export default function UsersPage() {
  const [err, setErr] = useState('')
  const [rows, setRows] = useState([])
  const [filter, setFilter] = useState('')
  const [sorters, setSorters] = useState([])
  const [expanded, setExpanded] = useState(() => new Set()) // id_user set

  // עריכה בתוך הטבלה המשנית
  const [editRowId, setEditRowId] = useState(null)
  const [editDraft, setEditDraft] = useState({})

  // עריכה מסכמת בשורה הראשית (affiliator + affiliateor_of)
  const [summaryEditIdUser, setSummaryEditIdUser] = useState(null)
  const [summaryDraft, setSummaryDraft] = useState({ affiliator: false, affiliateor_of: '' })
  const [summarySaving, setSummarySaving] = useState(false)

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
  useEffect(() => { load() }, [])

  // קיבוץ לפי id_user (fallback ל-email אם חסר) ואיסוף Summary לכל קבוצה
  const grouped = useMemo(() => {
    const by = new Map()
    for (const r of rows) {
      const key = r.id_user ?? r.email ?? `row-${r.id}`
      if (!by.has(key)) by.set(key, [])
      by.get(key).push(r)
    }
    const result = []
    for (const [id_user, list] of by.entries()) {
      const summaryRow = pickSummaryRow(list) || {}
      const { unifiedActiveUntil, daysLeft } = computeUnifiedActiveUntilAndDaysLeft(list)

      // מיפוי טלגרם לשדה אחיד “telegram”
      const telegram = summaryRow.telegram ?? summaryRow.telegram_username ?? ''

      const statusLabel = summarizeStatus(list, daysLeft)

      result.push({
        id_user,
        rows: [...list].sort((a, b) => (b.id || 0) - (a.id || 0)), // טבלה פנימית: חדש->ישן
        summary: {
          id_user,
          email: summaryRow.email || '',
          first_name: summaryRow.first_name || '',
          last_name: summaryRow.last_name || '',
          phone: summaryRow.phone || '',
          telegram: telegram || '',
          approved: Boolean(summaryRow.approved),
          status: statusLabel,
          period_start: summaryRow.period_start || null,
          // unified active_until (המאוחר ביותר מהמאושרות) — זה מה שמוצג בטבלה הראשית
          active_until: unifiedActiveUntil,
          coupon: summaryRow.coupon || '',
          affiliator: Boolean(summaryRow.affiliator),
          affiliateor_of: summaryRow.affiliateor_of || '',
          created_at: summaryRow.created_at || null,
          days_left: daysLeft,
        },
      })
    }
    return result
  }, [rows])

  // חיפוש על הסיכום של הטבלה הראשית
  const filteredGroups = useMemo(() => {
    const q = (filter || '').toLowerCase().trim()
    if (!q) return grouped
    return grouped.filter(g => {
      const s = g.summary
      const hay = [
        s.id_user, s.email, s.first_name, s.last_name, s.phone, s.telegram,
        s.status, s.coupon, s.affiliateor_of
      ].map(v => String(v ?? '').toLowerCase()).join(' ')
      return hay.includes(q)
    })
  }, [grouped, filter])

  // מיון הטבלה הראשית לפי שדות שביקשת
  const sortedGroups = useMemo(() => {
    if (!sorters.length) return filteredGroups
    const arr = [...filteredGroups]
    arr.sort((a, b) => {
      for (const s of sorters) {
        const A = a.summary
        const B = b.summary
        let av, bv
        switch (s.key) {
          case 'id_user': av = A.id_user; bv = B.id_user; break
          case 'email': av = A.email; bv = B.email; break
          case 'first_name': av = A.first_name; bv = B.first_name; break
          case 'last_name': av = A.last_name; bv = B.last_name; break
          case 'phone': av = A.phone; bv = B.phone; break
          case 'telegram': av = A.telegram; bv = B.telegram; break
          case 'approved': av = A.approved ? 1 : 0; bv = B.approved ? 1 : 0; break
          case 'status': av = A.status; bv = B.status; break
          case 'period_start':
            av = A.period_start ? new Date(String(A.period_start).replace(' ', 'T')).getTime() : 0
            bv = B.period_start ? new Date(String(B.period_start).replace(' ', 'T')).getTime() : 0
            break
          case 'active_until':
            av = A.active_until ? A.active_until.getTime() : 0
            bv = B.active_until ? B.active_until.getTime() : 0
            break
          case 'coupon': av = A.coupon; bv = B.coupon; break
          case 'affiliator': av = A.affiliator ? 1 : 0; bv = B.affiliator ? 1 : 0; break
          case 'affiliateor_of': av = A.affiliateor_of; bv = B.affiliateor_of; break
          case 'created_at':
            av = A.created_at ? new Date(String(A.created_at).replace(' ', 'T')).getTime() : 0
            bv = B.created_at ? new Date(String(B.created_at).replace(' ', 'T')).getTime() : 0
            break
          case 'days_left': av = A.days_left || 0; bv = B.days_left || 0; break
          default: av = ''; bv = ''
        }
        let cmp
        if (typeof av === 'number' && typeof bv === 'number') {
          cmp = av === bv ? 0 : av < bv ? -1 : 1
        } else {
          cmp = String(av ?? '').localeCompare(String(bv ?? ''), 'he', { numeric: true, sensitivity: 'base' })
        }
        if (cmp !== 0) return s.dir === 'desc' ? -cmp : cmp
      }
      return 0
    })
    return arr
  }, [filteredGroups, sorters])

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

  function toggleExpand(id_user) {
    setExpanded(prev => {
      const n = new Set(prev)
      if (n.has(id_user)) n.delete(id_user)
      else n.add(id_user)
      return n
    })
  }

  // ----- עריכה/מחיקה בטבלה המשנית -----
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
      if ('approved' in payload) {
        payload.approved =
          payload.approved === true ||
          payload.approved === '1' ||
          payload.approved === 1 ||
          payload.approved === 'כן'
      }
      if ('affiliator' in payload) {
        payload.affiliator =
          payload.affiliator === true ||
          payload.affiliator === '1' ||
          payload.affiliator === 1 ||
          payload.affiliator === 'כן'
      }
      if ('active_until' in payload && payload.active_until) {
        const v = String(payload.active_until).trim()
        if (v.includes('T')) {
          const withSeconds = /\d{2}:\d{2}:\d{2}$/.test(v) ? v : (v + ':00')
          payload.active_until = withSeconds.replace('T', ' ')
        }
      }

      for (const key of ['coupon', 'affiliateor_of', 'username', 'telegram_username', 'telegram', 'phone', 'first_name', 'last_name']) {
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
    if (!confirm('למחוק רשומה זו?')) return
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

  // ---- עריכה בשורה הראשית (affiliator + affiliateor_of) ----
  function beginSummaryEdit(group) {
    setSummaryEditIdUser(group.id_user)
    setSummaryDraft({
      affiliator: Boolean(group.summary.affiliator),
      affiliateor_of: group.summary.affiliateor_of || '',
    })
  }
  function cancelSummaryEdit() {
    setSummaryEditIdUser(null)
    setSummaryDraft({ affiliator: false, affiliateor_of: '' })
  }
  function changeSummaryDraft(key, val) {
    setSummaryDraft(d => ({ ...d, [key]: val }))
  }
  async function saveSummaryEdit(group) {
    setSummarySaving(true)
    setErr('')
    try {
      // מעדכן את כל הרשומות של אותו id_user
      const payload = {
        affiliator: summaryDraft.affiliator ? 1 : 0,
        affiliateor_of: String(summaryDraft.affiliateor_of || '').trim() || null,
      }
      // ריצה סידרתית כדי לשמור פשטות (אפשר גם Promise.all)
      for (const r of group.rows) {
        const res = await apiFetch(`/users/${r.id}`, {
          method: 'PUT',
          body: JSON.stringify({ data: payload }),
        })
        if (res.status === 401) {
          localStorage.removeItem('admin_token'); window.location.href = '/login'; return
        }
        if (!res.ok) throw new Error(await res.text())
      }
      await load()
      cancelSummaryEdit()
    } catch (e) {
      setErr(String(e.message || e))
    } finally {
      setSummarySaving(false)
    }
  }

  // --- Render ---
  return (
    <div className="admin-shell">
      {/* סרגל: רענון + חיפוש + ספירה */}
      <div className="topbar" style={{ marginTop: 12 }}>
        <div className="left">
          <button className="btn-secondary" onClick={load}>רענן</button>
          <input
            className="search"
            placeholder="חיפוש לפי מייל/שם/טלפון/סטטוס…"
            value={filter}
            onChange={e => setFilter(e.target.value)}
          />
        </div>
        <div className="right">
          <span className="pill">משתמשים ייחודיים: {sortedGroups.length}</span>
        </div>
      </div>

      {err ? <div className="alert" style={{ margin: '12px auto' }}>{err}</div> : null}

      <div className="table-wrap">
        <table className="users">
          <thead>
            <tr>
              <th />{/* expand */}
              <th onClick={() => toggleSort('id_user')}>id_user{sorterIndicator('id_user')}</th>
              <th onClick={() => toggleSort('email')}>email{sorterIndicator('email')}</th>
              <th onClick={() => toggleSort('first_name')}>first_name{sorterIndicator('first_name')}</th>
              <th onClick={() => toggleSort('last_name')}>last_name{sorterIndicator('last_name')}</th>
              <th onClick={() => toggleSort('phone')}>phone{sorterIndicator('phone')}</th>
              <th onClick={() => toggleSort('telegram')}>telegram{sorterIndicator('telegram')}</th>
              <th onClick={() => toggleSort('approved')}>approved{sorterIndicator('approved')}</th>
              <th onClick={() => toggleSort('status')}>status{sorterIndicator('status')}</th>
              <th onClick={() => toggleSort('period_start')}>period_start{sorterIndicator('period_start')}</th>
              <th onClick={() => toggleSort('active_until')}>active_until{sorterIndicator('active_until')}</th>
              <th onClick={() => toggleSort('coupon')}>coupon{sorterIndicator('coupon')}</th>
              <th onClick={() => toggleSort('affiliator')}>affiliator{sorterIndicator('affiliator')}</th>
              <th onClick={() => toggleSort('affiliateor_of')}>affiliateor_of{sorterIndicator('affiliateor_of')}</th>
              <th onClick={() => toggleSort('created_at')}>created_at{sorterIndicator('created_at')}</th>
              <th onClick={() => toggleSort('days_left')}>days_left{sorterIndicator('days_left')}</th>
            </tr>
          </thead>
          <tbody>
            {sortedGroups.length === 0 ? (
              <tr><td colSpan={16} className="muted">אין נתונים</td></tr>
            ) : (
              sortedGroups.map(g => {
                const s = g.summary
                const isOpen = expanded.has(g.id_user)
                const isSummaryEditing = summaryEditIdUser === g.id_user
                return (
                  <React.Fragment key={String(g.id_user)}>
                    <tr className="tr-row">
                      <td style={{ width: 72, whiteSpace: 'nowrap' }}>
                        <button
                          className="btn-secondary sm"
                          title={isOpen ? 'סגור' : 'פתח'}
                          onClick={() => toggleExpand(g.id_user)}
                          style={{ padding: '2px 8px', marginInlineEnd: 6 }}
                        >
                          {isOpen ? '▾' : '▸'}
                        </button>
                        {!isSummaryEditing ? (
                          <button
                            className="btn-primary sm"
                            onClick={() => beginSummaryEdit(g)}
                            title="ערוך אפיליאציה"
                          >
                            ערוך
                          </button>
                        ) : (
                          <>
                            <button
                              className="btn-primary sm"
                              onClick={() => saveSummaryEdit(g)}
                              disabled={summarySaving}
                              title="שמור לכל הרשומות"
                              style={{ marginInlineEnd: 4 }}
                            >
                              {summarySaving ? 'שומר…' : 'שמור'}
                            </button>
                            <button className="btn-secondary sm" onClick={cancelSummaryEdit}>בטל</button>
                          </>
                        )}
                      </td>

                      <td>{s.id_user}</td>
                      <td>{s.email || '—'}</td>
                      <td>{s.first_name || '—'}</td>
                      <td>{s.last_name || '—'}</td>
                      <td>{s.phone || '—'}</td>
                      <td>{s.telegram || '—'}</td>
                      <td>{s.approved ? 'כן' : 'לא'}</td>
                      <td>{s.status}</td>
                      <td>{s.period_start ? formatDateOnly(s.period_start) : '—'}</td>
                      <td>{s.active_until ? formatDateOnly(s.active_until) : '—'}</td>
                      <td>{s.coupon || '—'}</td>

                      {/* affiliator – ניתן לעריכה בשורה הראשית */}
                      <td>
                        {isSummaryEditing ? (
                          <select
                            className="cell-input"
                            value={summaryDraft.affiliator ? '1' : '0'}
                            onChange={(e) => changeSummaryDraft('affiliator', e.target.value === '1')}
                          >
                            <option value="0">לא</option>
                            <option value="1">כן</option>
                          </select>
                        ) : (s.affiliator ? 'כן' : 'לא')}
                      </td>

                      {/* affiliateor_of – ניתן לעריכה בשורה הראשית */}
                      <td>
                        {isSummaryEditing ? (
                          <input
                            className="cell-input"
                            value={summaryDraft.affiliateor_of ?? ''}
                            onChange={(e) => changeSummaryDraft('affiliateor_of', e.target.value)}
                          />
                        ) : (s.affiliateor_of || '—')}
                      </td>

                      <td>{s.created_at ? formatDateOnly(s.created_at) : '—'}</td>
                      <td>{s.days_left}</td>
                    </tr>

                    {isOpen && (
                      <tr>
                        <td colSpan={16} style={{ background: 'rgba(255,255,255,0.03)' }}>
                          <div style={{ padding: 8 }}>
                            <div className="glass" style={{ padding: 8 }}>
                              <table className="users" style={{ margin: 0 }}>
                                <thead>
                                  <tr>
                                    <th>ID</th>
                                    <th>approved</th>
                                    <th>status</th>
                                    <th>plan</th>
                                    <th>coupon</th>
                                    <th>period_start</th>
                                    <th>active_until</th>
                                    <th>price_nis</th>
                                    <th>created_at</th>
                                    <th>פעולות</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {g.rows.map(r => {
                                    const isEditing = editRowId === r.id
                                    return (
                                      <tr key={r.id}>
                                        <td>{r.id}</td>
                                        <td>
                                          {isEditing ? (
                                            <select
                                              className="cell-input"
                                              value={(editDraft.approved ? '1' : '0')}
                                              onChange={e => changeDraft('approved', e.target.value === '1')}
                                            >
                                              <option value="0">לא</option>
                                              <option value="1">כן</option>
                                            </select>
                                          ) : (r.approved ? 'כן' : 'לא')}
                                        </td>
                                        <td>{isEditing ? (
                                          <input className="cell-input" value={editDraft.status ?? ''} onChange={e => changeDraft('status', e.target.value)} />
                                        ) : (r.status ?? '')}</td>
                                        <td>{isEditing ? (
                                          <input className="cell-input" value={editDraft.plan ?? ''} onChange={e => changeDraft('plan', e.target.value)} />
                                        ) : (r.plan ?? '')}</td>
                                        <td>{isEditing ? (
                                          <input className="cell-input" value={editDraft.coupon ?? ''} onChange={e => changeDraft('coupon', e.target.value)} />
                                        ) : (r.coupon ?? '')}</td>
                                        <td>{formatDateOnly(r.period_start)}</td>
                                        <td>
                                          {isEditing ? (
                                            <input
                                              type="datetime-local"
                                              className="cell-input"
                                              value={toDatetimeLocalValue(editDraft.active_until ?? r.active_until)}
                                              onChange={e => changeDraft('active_until', e.target.value)}
                                            />
                                          ) : formatDateOnly(r.active_until)}
                                        </td>
                                        <td>{isEditing ? (
                                          <input
                                            type="number"
                                            step="0.01"
                                            min="0"
                                            className="cell-input"
                                            value={editDraft.price_nis ?? r.price_nis ?? ''}
                                            onChange={e => changeDraft('price_nis', e.target.value)}
                                          />
                                        ) : (r.price_nis == null ? '' : String(r.price_nis))}</td>
                                        <td>{formatDateOnly(r.created_at)}</td>
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
                                  })}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
