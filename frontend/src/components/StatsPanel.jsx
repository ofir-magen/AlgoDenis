// src/components/StatsPanel.jsx
export default function StatsPanel() {
  return (
    <div style={{ display:'grid', gap:12 }}>
      <div className="field">
        <div className="field__label">דוגמה</div>
        <div className="field__control">
          <div className="auth-hint">פה נבנה בהמשך גרפים / KPI / פילוחים.</div>
        </div>
      </div>

      <div className="glass" style={{ padding: 16 }}>
        <h4 style={{ marginTop: 0 }}>סטטוס כללי</h4>
        <ul style={{ margin: 0, paddingInlineStart: '1.2em' }}>
          <li>כמות רשומות ב־DataLog: —</li>
          <li>ממוצע שינוי יומי: —</li>
          <li>Top movers: —</li>
        </ul>
      </div>
    </div>
  )
}
