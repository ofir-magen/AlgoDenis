import { useMemo, useState } from 'react'
import PositionsTable from './PositionsTable.jsx'
import StatsPanel from './StatsPanel.jsx'

export default function DashboardWidget({
  defaultTab = 'stats',
  height = 560   // העליתי מ-480 כדי לתת יותר גובה לגרף
}) {
  const [tab, setTab] = useState(defaultTab)
  const h = useMemo(() => (typeof height === 'number' ? `${height}px` : String(height)), [height])

  return (
    <section id="dash" className="container" style={{ marginTop: 24 }}>
      <div className="glass" style={{ padding: 16 }}>
        <div style={{ display:'flex', justifyContent:'center', marginBottom: 12 }}>
          <div className="auth-tabs" style={{ display: 'inline-flex', gap: 8, padding: 4, margin: 0, background: 'transparent' }}>
            <button className={`auth-tab ${tab === 'positions' ? 'is-active' : ''}`} onClick={() => setTab('positions')} type="button" style={{ minWidth: 'unset' }}>
              פוזיציות אחרונות
            </button>
            <button className={`auth-tab ${tab === 'stats' ? 'is-active' : ''}`} onClick={() => setTab('stats')} type="button" style={{ minWidth: 'unset' }}>
              סטטיסטיקה
            </button>
          </div>
        </div>

        <div
          className="auth-card"
          style={{
            padding: 0,
            background: 'transparent',
            boxShadow: 'none',
            borderRadius: 16,
            border: '1px solid rgba(255,255,255,.12)',
            overflow: 'hidden',
            width: '100%',
            height: h
          }}
        >
          {tab === 'positions'
            ? <PositionsTable limit={10} height="100%" showHeader={false} borderless />
            : <div style={{ width:'100%', height:'100%' }}><StatsPanel /></div>}
        </div>
      </div>
    </section>
  )
}
