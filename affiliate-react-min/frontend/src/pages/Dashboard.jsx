// frontend/src/pages/Dashboard.jsx
import React, { useEffect, useMemo, useState } from 'react'
import { authedGet, logout, getMonthlySummary, getUsersByMonth, getCouponStats, getStatusStats } from '../api.js'
import { useNavigate } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  PieChart, Pie, Legend, Cell
} from 'recharts'

function useThemeColors() {
  // read CSS variables from :root to keep a single design system
  return useMemo(() => {
    if (typeof window === 'undefined') {
      return {
        accent1: '#6ea2ff',
        accent2: '#7cf2d6',
        txt: '#e9eefc',
        txtDim: '#a9b4d0',
        stroke: 'rgba(255,255,255,0.18)',
        panel: 'rgba(255,255,255,0.08)',
        danger: '#ff646e'
      }
    }
    const css = getComputedStyle(document.documentElement)
    const get = (name, fallback) => (css.getPropertyValue(name) || fallback).trim()
    return {
      accent1: get('--accent1', '#6ea2ff'),
      accent2: get('--accent2', '#7cf2d6'),
      txt: get('--txt', '#e9eefc'),
      txtDim: get('--txt-dim', '#a9b4d0'),
      stroke: get('--stroke', 'rgba(255,255,255,0.18)'),
      panel: get('--panel', 'rgba(255,255,255,0.08)'),
      danger: get('--danger', '#ff646e')
    }
  }, [])
}

function Card({ title, subtitle, children }) {
  return (
    <div style={{ background: 'var(--panel)', border: '1px solid var(--stroke)', borderRadius: 16, padding: 16 }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', marginBottom: 8 }}>
        <div style={{ fontWeight: 800, letterSpacing: 0.2 }}>{title}</div>
        {subtitle && <div className="badge">{subtitle}</div>}
      </div>
      {children}
    </div>
  )
}

function TinyKpi({ label, value }) {
  return (
    <div style={{
      background: 'rgba(255,255,255,0.06)',
      border: '1px solid var(--stroke)',
      borderRadius: 14,
      padding: '10px 12px',
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
      minWidth: 120
    }}>
      <div style={{ color: 'var(--txt-dim)', fontSize: 12 }}>{label}</div>
      <div style={{ fontWeight: 800, fontSize: 20 }}>{value}</div>
    </div>
  )
}

function PrettyTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null
  const p = payload[0]
  return (
    <div style={{
      background: 'rgba(12,18,36,0.96)',
      color: 'var(--txt)',
      border: '1px solid var(--stroke)',
      borderRadius: 12,
      padding: '8px 10px',
      boxShadow: '0 6px 16px rgba(0,0,0,0.25)'
    }}>
      <div style={{ fontSize: 12, color: 'var(--txt-dim)' }}>{label}</div>
      <div style={{ fontWeight: 800 }}>{p.name || 'מספר'}: {p.value}</div>
    </div>
  )
}

export default function Dashboard() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [partnerEmail, setPartnerEmail] = useState('')
  const [coupons, setCoupons] = useState([])
  const [columns, setColumns] = useState([])
  const [rows, setRows] = useState([])

  const [monthlyPoints, setMonthlyPoints] = useState([])
  const [selectedMonth, setSelectedMonth] = useState(null)
  const [monthUsers, setMonthUsers] = useState([])

  const [couponStats, setCouponStats] = useState([])
  const [statusStats, setStatusStats] = useState({ field: null, active_count: 0, inactive_count: 0 })

  const navigate = useNavigate()
  const theme = useThemeColors()

  // Load base + charts
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

        const monthly = await getMonthlySummary()
        if (cancelled) return
        setMonthlyPoints(Array.isArray(monthly.points) ? monthly.points : [])

        const cstats = await getCouponStats()
        if (cancelled) return
        setCouponStats(Array.isArray(cstats.stats) ? cstats.stats : [])

        const sstats = await getStatusStats()
        if (cancelled) return
        setStatusStats(sstats || { field: null, active_count: 0, inactive_count: 0 })
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

  // Drill-down users by selected month
  useEffect(() => {
    let cancelled = false
    async function run() {
      if (!selectedMonth) { setMonthUsers([]); return }
      try {
        const res = await getUsersByMonth(selectedMonth)
        if (!cancelled) setMonthUsers(Array.isArray(res.users) ? res.users : [])
      } catch (_) {
        if (!cancelled) setMonthUsers([])
      }
    }
    run()
    return () => { cancelled = true }
  }, [selectedMonth])

  const displayColumns = useMemo(() => {
    if (columns && columns.length) return columns
    if (rows && rows.length) return Object.keys(rows[0])
    return []
  }, [columns, rows])

  const pieData = useMemo(() => ([
    { name: 'מאושרים', value: statusStats.active_count, color: theme.accent2 },
    { name: 'לא מאושרים', value: statusStats.inactive_count, color: theme.danger },
  ]), [statusStats, theme])

  // totals for KPIs
  const totalUsers = rows.length
  const totalMonths = monthlyPoints.length
  const topMonth = monthlyPoints.reduce((acc, p) => p.count > (acc?.count || 0) ? p : acc, null)

  return (
    <div className="container">
      <div className="card" style={{ width: '100%', maxWidth: 'min(1200px, 96vw)' }}>
        {/* Header */}
        <h2 style={{ textAlign: 'center', marginBottom: 6 }}>דאשבורד שותף</h2>
        <div className="helper" style={{ textAlign: 'center' }}>
          {partnerEmail ? `שותף מחובר: ${partnerEmail}` : '...'}
        </div>
        <div className="helper" style={{ textAlign: 'center', marginBottom: 16 }}>
          {coupons.length ? `קופונים שלך: ${coupons.join(', ')}` : 'אין קופונים משויכים'}
        </div>

        {/* KPIs */}
        {!loading && !error && (
          <div style={{ display: 'flex', flexWrap:'wrap', gap: 12, marginBottom: 16 }}>
            <TinyKpi label="סה״כ משתמשים" value={totalUsers} />
            <TinyKpi label="מס׳ חודשי פעילות" value={totalMonths} />
            <TinyKpi label="חודש שיא" value={topMonth ? `${topMonth.month} · ${topMonth.count}` : '—'} />
          </div>
        )}

        {loading && <div className="helper">טוען נתונים...</div>}
        {error && <div className="helper" style={{ color: 'var(--danger)' }}>{error}</div>}

        {!loading && !error && (
          <>
            {/* Charts */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16, marginBottom: 16 }}>
              {/* Monthly */}
              <Card
                title="תשלומים לפי חודש"
                subtitle={selectedMonth ? (
                  <span>חודש נבחר: <b>{selectedMonth}</b> · משתמשים: <b>{monthUsers.length}</b></span>
                ) : 'לחץ על עמודה כדי לראות את המשתמשים של אותו חודש'}
              >
                {/* Gradients for nicer bars */}
                <svg width="0" height="0" style={{ position:'absolute' }}>
                  <defs>
                    <linearGradient id="gradBars" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={theme.accent1} stopOpacity="1"/>
                      <stop offset="100%" stopColor={theme.accent2} stopOpacity="0.85"/>
                    </linearGradient>
                  </defs>
                </svg>

                <div style={{ width: '100%', height: 280 }}>
                  <ResponsiveContainer>
                    <BarChart data={monthlyPoints} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.14)" />
                      <XAxis dataKey="month" tick={{ fill: 'var(--txt-dim)', fontSize: 12 }} />
                      <YAxis allowDecimals={false} tick={{ fill: 'var(--txt-dim)', fontSize: 12 }} />
                      <Tooltip content={<PrettyTooltip />} />
                      <Bar
                        dataKey="count"
                        name="משתמשים"
                        fill="url(#gradBars)"
                        radius={[10, 10, 0, 0]}
                        onClick={(entry) => setSelectedMonth(entry?.month)}
                        cursor="pointer"
                        maxBarSize={48}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                {selectedMonth && (
                  <div style={{ marginTop: 8 }}>
                    <button className="chip" onClick={() => setSelectedMonth(null)}>נקה בחירה</button>
                  </div>
                )}
              </Card>

              {/* Coupons */}
              <Card title="חלוקה לפי קופון">
                <svg width="0" height="0" style={{ position:'absolute' }}>
                  <defs>
                    <linearGradient id="gradCoupons" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%" stopColor={theme.accent2} stopOpacity="1"/>
                      <stop offset="100%" stopColor={theme.accent1} stopOpacity="0.9"/>
                    </linearGradient>
                  </defs>
                </svg>

                <div style={{ width: '100%', height: 260 }}>
                  <ResponsiveContainer>
                    <BarChart data={couponStats} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.14)" />
                      <XAxis dataKey="coupon" tick={{ fill: 'var(--txt-dim)', fontSize: 12 }} />
                      <YAxis allowDecimals={false} tick={{ fill: 'var(--txt-dim)', fontSize: 12 }} />
                      <Tooltip content={<PrettyTooltip />} />
                      <Bar dataKey="count" name="משתמשים" fill="url(#gradCoupons)" radius={[10,10,0,0]} maxBarSize={48} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Card>

              {/* Status */}
              <Card title={`סטטוס משתמשים ${statusStats.field ? `(שדה: ${statusStats.field})` : ''}`}>
                <div style={{ width: '100%', height: 260 }}>
                  <ResponsiveContainer>
                    <PieChart>
                      <Tooltip content={<PrettyTooltip />} />
                      <Legend wrapperStyle={{ color: 'var(--txt-dim)' }} />
                      <Pie
                        data={pieData}
                        dataKey="value"
                        nameKey="name"
                        innerRadius={70}
                        outerRadius={100}
                        paddingAngle={3}
                        blendStroke
                        label={({ name, value }) => `${name}: ${value}`}
                      >
                        {pieData.map((entry, i) => (
                          <Cell key={`cell-${i}`} fill={entry.color} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </Card>
            </div>

            {/* Table */}
            <Card title={selectedMonth ? `משתמשים לחודש ${selectedMonth}` : 'כל המשתמשים לפי הקופונים שלך'}>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      {displayColumns.map(col => (
                        <th key={col} style={{ textAlign: 'right', padding: '10px 8px', borderBottom: '1px solid var(--stroke)', fontSize: 13, color: 'var(--txt-dim)' }}>
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(selectedMonth ? monthUsers : rows).length === 0 ? (
                      <tr>
                        <td colSpan={Math.max(1, displayColumns.length)} style={{ padding: '14px 8px', textAlign: 'center', color: 'var(--txt-dim)' }}>
                          לא נמצאו נתונים.
                        </td>
                      </tr>
                    ) : (
                      (selectedMonth ? monthUsers : rows).map((r, i) => (
                        <tr key={i} style={{ borderBottom: '1px solid var(--stroke)' }}>
                          {displayColumns.map(col => (
                            <td key={col} style={{ padding: '10px 8px', fontSize: 14 }}>
                              {r[col] === null || r[col] === undefined ? '' : String(r[col])}
                            </td>
                          ))}
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              <div style={{ display:'flex', justifyContent:'flex-end', marginTop: 12 }}>
                <button className="button" onClick={() => { logout(); navigate('/login'); }}>
                  התנתקות
                </button>
              </div>
            </Card>
          </>
        )}
      </div>
    </div>
  )
}
