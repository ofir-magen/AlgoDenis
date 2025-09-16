import { useMemo, useState } from 'react'
import PositionsTable from './PositionsTable.jsx'
import StatsPanel from './StatsPanel.jsx'

/**
 * DashboardWidget
 * - Tabs centered and sized like login/register buttons (no giant pill).
 * - Inner window fills full width; table fills 100% height of that window.
 */
export default function DashboardWidget({
  defaultTab = 'positions',
  height = 420
}) {
  const [tab, setTab] = useState(defaultTab) // 'positions' | 'stats'
  const h = useMemo(() => (typeof height === 'number' ? `${height}px` : String(height)), [height])

  return (
    <section id="dash" className="container" style={{ marginTop: 24 }}>
      <div className="glass" style={{ padding: 16 }}>
        {/* Tabs header — compact like AuthPage */}
        <div style={{ display:'flex', justifyContent:'center', marginBottom: 12 }}>
          {/* חשוב: עושים את ה-track עטוף כ-inline-flex כדי שלא יתמתח לרוחב מלא */}
          <div
            className="auth-tabs"
            style={{
              display: 'inline-flex',
              gap: 8,
              padding: 4,
              margin: 0,
              background: 'transparent' // מונע רקע/אליפסה רחבה
            }}
          >
            <button
              className={`auth-tab ${tab === 'positions' ? 'is-active' : ''}`}
              onClick={() => setTab('positions')}
              type="button"
              style={{ minWidth: 'unset' }} // שומר על גודל כפתור טבעי
            >
              פוזיציות אחרונות
            </button>
            <button
              className={`auth-tab ${tab === 'stats' ? 'is-active' : ''}`}
              onClick={() => setTab('stats')}
              type="button"
              style={{ minWidth: 'unset' }}
            >
              סטטיסטיקה
            </button>
          </div>
        </div>

        {/* Inner window — full width, fixed height */}
        <div
          className="auth-card"
          style={{
            padding: 0,
            background: 'transparent',
            boxShadow: 'none',
            borderRadius: 16,
            border: '1px solid rgba(255,255,255,.12)',
            overflow: 'hidden',
            width: '100%',   // נמתח לקצוות
            height: h
          }}
        >
          {tab === 'positions' ? (
            // Table fills the window completely
            <PositionsTable limit={10} height="100%" showHeader={false} borderless />
          ) : (
            <div style={{ width:'100%', height:'100%', overflow:'auto' }}>
              <div className="glass" style={{ padding: 16, borderRadius: 0, border: 0 }}>
                <h3 style={{ marginTop: 0, marginBottom: 12 }}>סטטיסטיקה</h3>
                <StatsPanel />
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
