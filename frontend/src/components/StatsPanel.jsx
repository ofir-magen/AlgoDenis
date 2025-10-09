// src/components/StatsPanel.jsx
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'

export default function StatsPanel({ apiBase }) {
  const API_BASE = useMemo(() => {
    if (apiBase) return apiBase.replace(/\/+$/, '')
    const envUrl = import.meta.env?.VITE_API_URL
    if (envUrl) return envUrl.replace(/\/+$/, '')
    const isHttps = typeof window !== 'undefined' && window.location.protocol === 'https:'
    const host = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1'
    return `${isHttps ? 'https' : 'http'}://${host}:8000/api`
  }, [apiBase])

  // form state
  const [start, setStart] = useState(defaultStartISO())
  const [capital, setCapital] = useState(10000)

  // allocation mode: 'risk' (percent of equity) OR 'fixed' (fixed amount per trade)
  const [allocMode, setAllocMode] = useState('risk')
  const [riskPct, setRiskPct] = useState(10)
  const [fixedAmount, setFixedAmount] = useState(1000)

  // data + results
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [series, setSeries] = useState([]) // [{ t: Date, v: number }]
  const [summary, setSummary] = useState(null)

  // chart refs
  const canvasRef = useRef(null)
  const chartWrapRef = useRef(null)
  const [hoverIdx, setHoverIdx] = useState(null)

  // ------- RUN ANALYSIS -------
  async function handleRun(e) {
    e.preventDefault()
    setError(''); setLoading(true); setSeries([]); setSummary(null); setHoverIdx(null)

    try {
      const res = await fetch(`${API_BASE}/positions/by-range?start=${encodeURIComponent(start)}`)
      if (!res.ok) throw new Error(`API error ${res.status}`)
      const rows = await res.json()

      // נקודת פתיחה תמידית
      const startPoint = { t: parseTs(start), v: Number(capital) }

      if (!Array.isArray(rows) || rows.length === 0) {
        setSeries([startPoint])
        setSummary({ points: 0, final: Number(capital), totalChangePct: 0 })
        return
      }

      const getEntryTs = (r) => r.entry_time ?? r.entry_date ?? r.trade_date ?? null
      rows.sort((a, b) => +parseTs(getEntryTs(a)) - +parseTs(getEntryTs(b)))

      const getChange = (r) => {
        if (isFiniteNum(r.change_pct)) return Number(r.change_pct) / 100
        const e = r.entry_price, x = r.exit_price
        if (isFiniteNum(e) && isFiniteNum(x) && Number(e) !== 0) {
          return (Number(x) - Number(e)) / Number(e)
        }
        return 0
      }

      let cur = Number(capital)
      const pts = [startPoint]

      for (const r of rows) {
        const t = parseTs(getEntryTs(r))
        const change = getChange(r)

        // הקצאה לפי מצב:
        // risk → אחוז מהתיק; fixed → סכום קבוע (לא לעבור את גודל התיק הנוכחי)
        let alloc = 0
        if (allocMode === 'risk') {
          const risk = Math.max(0, Number(riskPct)) / 100
          alloc = cur * risk
        } else {
          alloc = Math.max(0, Number(fixedAmount))
          if (!isFinite(alloc)) alloc = 0
          alloc = Math.min(alloc, cur) // שלא יחרוג מההון הנוכחי
        }

        const pnl = alloc * change
        cur += pnl
        pts.push({ t, v: cur })
      }

      setSeries(pts)
      setSummary({
        points: rows.length,
        final: cur,
        totalChangePct: safePct(((cur - Number(capital)) / Number(capital)) * 100)
      })
    } catch (err) {
      setError(String(err.message || err))
    } finally { setLoading(false) }
  }

  // Resize canvas to fill wrapper (with DPR for crispness)
  useLayoutEffect(() => {
    const c = canvasRef.current, wrap = chartWrapRef.current
    if (!c || !wrap) return
    const ro = new ResizeObserver(() => {
      const dpr = window.devicePixelRatio || 1
      const w = wrap.clientWidth, h = Math.max(220, wrap.clientHeight)
      c.width = Math.max(1, Math.floor(w * dpr))
      c.height = Math.max(1, Math.floor(h * dpr))
      c.style.width = w + 'px'
      c.style.height = h + 'px'
      const ctx = c.getContext('2d')
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)  // ציור ביחידות CSS
      drawChart(c, series, hoverIdx)
    })
    ro.observe(wrap)
    return () => ro.disconnect()
  }, [series, hoverIdx])

  useEffect(() => {
    const c = canvasRef.current; if (!c) return
    drawChart(c, series, hoverIdx)
  }, [series, hoverIdx])

  // hover tooltip mapping in CSS pixels
  useEffect(() => {
    const c = canvasRef.current; if (!c) return
    function onMove(ev){
      if (!series.length) return
      const rect = c.getBoundingClientRect()
      const x = ev.clientX - rect.left // CSS px
      const {L, R, T, B} = PAD()
      const w = rect.width
      const tMin = +new Date(series[0].t)
      const tMax = +new Date(series[series.length-1].t)
      const span = (tMax - tMin) || 1
      const xOf = t => L + (((t - tMin) / span) * (w - L - R))
      let bestI=0,bestD=Infinity
      for (let i=0;i<series.length;i++){
        const px = xOf(+new Date(series[i].t))
        const d = Math.abs(px - x)
        if (d<bestD){bestD=d;bestI=i}
      }
      setHoverIdx(bestI)
    }
    function onLeave(){ setHoverIdx(null) }
    c.addEventListener('mousemove', onMove)
    c.addEventListener('mouseleave', onLeave)
    return () => {
      c.removeEventListener('mousemove', onMove)
      c.removeEventListener('mouseleave', onLeave)
    }
  }, [series])

  // UI helpers for mutually-exclusive inputs
  const inactiveStyle = (isInactive) => isInactive ? { opacity: 0.5 } : {}
  const riskInactive  = allocMode !== 'risk'
  const fixedInactive = allocMode !== 'fixed'

  return (
    <div style={{ height:'100%', display:'flex', flexDirection:'column', gap:12 }}>
      {/* Form row */}
      <form onSubmit={handleRun} className="glass" style={{ padding: 16 }}>
        <div style={{
          display:'grid',
          gridTemplateColumns:'minmax(220px,1fr) minmax(160px,1fr) minmax(180px,1fr) minmax(200px,1fr) auto',
          gap:12, alignItems:'end'
        }}>
          <Field label="תאריך התחלה">
            <input
              type="datetime-local"
              value={localDateTimeForInput(start)}
              onChange={e=>setStart(toISOFromLocalInput(e.target.value))}
              className="input"
            />
          </Field>

          <Field label="סכום תיק (₪)">
            <input
              type="number"
              min="0"
              step="100"
              value={capital}
              onChange={e=>setCapital(e.target.value)}
              className="input"
              placeholder="10000"
            />
          </Field>

          {/* RISK % (exclusive with fixed amount) */}
          <Field label="אחוז סיכון מהתיק (%)">
            <input
              type="number"
              min="0"
              max="100"
              step="0.1"
              value={riskPct}
              onChange={e => { setRiskPct(e.target.value); setAllocMode('risk') }}
              onFocus={() => setAllocMode('risk')}
              className="input"
              placeholder="10"
              style={inactiveStyle(riskInactive)}
              title="כאשר שדה זה פעיל, החישוב לפי אחוז מהתיק בכל טרייד"
            />
          </Field>

          {/* FIXED AMOUNT (exclusive with risk %) */}
          <Field label="סכום קבוע לעסקה (₪)">
            <input
              type="number"
              min="0"
              step="50"
              value={fixedAmount}
              onChange={e => { setFixedAmount(e.target.value); setAllocMode('fixed') }}
              onFocus={() => setAllocMode('fixed')}
              className="input"
              placeholder="1000"
              style={inactiveStyle(fixedInactive)}
              title="כאשר שדה זה פעיל, ההקצאה לכל טרייד היא סכום קבוע"
            />
          </Field>

          <div style={{ display:'flex', justifyContent:'flex-end' }}>
            <button type="submit" className="btn btn--primary" disabled={loading} style={{ height:42 }}>
              הרץ ניתוח
            </button>
          </div>
        </div>

        <div style={{ marginTop: 8, display:'flex', gap:12, alignItems:'center', flexWrap:'wrap' }}>
          <ModeBadge mode={allocMode} />
          {loading && <span className="auth-hint">טוען נתונים ומחשב…</span>}
          {error && <span className="auth-error" style={{ marginInlineStart: 8 }}>{error}</span>}
        </div>
      </form>

      {/* Chart card fills remaining space */}
      <div className="glass" style={{ padding: 16, display:'grid', gridTemplateRows:'auto 1fr', minHeight:0, height:'100%' }}>
        <div style={{ display:'flex', alignItems:'baseline', gap:12 }}>
          <h3 style={{ margin:0 }}>גרף סכום התיק</h3>
          {summary && (
            <span className="auth-hint">
              נקודות: {summary.points} | שווי סופי: {fmtCurrency(summary.final)} | שינוי מצטבר: {fmtPct(summary.totalChangePct)}
            </span>
          )}
        </div>
        <div ref={chartWrapRef} style={{ width:'100%', height:'100%', minHeight:0 }}>
          <canvas ref={canvasRef}/>
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div className="field">
      <div className="field__label">{label}</div>
      <div className="field__control">{children}</div>
    </div>
  )
}

function ModeBadge({ mode }) {
  const text = mode === 'risk'
    ? 'מצב חישוב: אחוז מהתיק בכל עסקה'
    : 'מצב חישוב: סכום קבוע לכל עסקה'
  return (
    <span className="auth-hint" style={{
      border:'1px solid var(--stroke)', padding:'4px 8px', borderRadius:999
    }}>{text}</span>
  )
}

// ===== Helpers =====
function defaultStartISO(){ const d=new Date(Date.now()-7*24*3600*1000); return d.toISOString().slice(0,19) }
function localDateTimeForInput(s){ try{return s.slice(0,16)}catch{return''} }
function toISOFromLocalInput(s){ return s ? s + ':00' : '' }
function fmtCurrency(v){ if(!isFinite(v))return'-'; return new Intl.NumberFormat('he-IL',{style:'currency',currency:'ILS',maximumFractionDigits:2}).format(Number(v)) }
function fmtPct(v){ if(!isFinite(v))return'-'; const n=Number(v); return (n>0?'+':'')+n.toFixed(2)+'%' }
function isFiniteNum(x){ return x !== null && x !== '' && Number.isFinite(Number(x)) }
function safePct(v){ return Number.isFinite(v) ? v : 0 }

/** פרסור עמיד לתאריכים שמגיעים מה-API */
function parseTs(v){
  if (!v && v !== 0) return new Date(NaN)
  if (v instanceof Date) return v
  if (typeof v === 'number' || (/^\d+$/.test(String(v)))) {
    const n = Number(v)
    return new Date(n < 1e12 ? n * 1000 : n)
  }
  let s = String(v).trim()
  if (!s) return new Date(NaN)
  if (s.includes(' ') && !s.includes('T')) s = s.replace(' ', 'T')
  const timePart = s.split('T')[1] || ''
  if (timePart && timePart.length <= 5) s = s + ':00'
  return new Date(s)
}

// ===== Chart (works in CSS units; DPR handled by context transform) =====
const PAD = () => ({ L: 60, R: 16, T: 18, B: 40 })

function drawChart(canvas, series, hoverIdx=null){
  const ctx = canvas.getContext('2d')
  const dpr = window.devicePixelRatio || 1
  const w = canvas.width / dpr
  const h = canvas.height / dpr

  ctx.clearRect(0,0,w,h)

  if(!series.length){
    ctx.fillStyle='rgba(255,255,255,0.7)'
    ctx.font='14px system-ui'
    ctx.fillText('אין נתונים להצגה. הרץ ניתוח.', 16, 24)
    return
  }

  const {L, R, T, B} = PAD()
  const tMin=+new Date(series[0].t), tMax=+new Date(series[series.length-1].t)
  let vMin=Math.min(...series.map(p=>p.v)), vMax=Math.max(...series.map(p=>p.v))
  if(vMin===vMax){vMin-=1;vMax+=1}

  const x = t => L + (((t - tMin) / (tMax - tMin || 1)) * (w - L - R))
  const y = v => T + ((1 - ((v - vMin) / (vMax - vMin || 1))) * (h - T - B))

  // axes
  ctx.strokeStyle='rgba(255,255,255,0.25)'; ctx.lineWidth=1
  ctx.beginPath(); ctx.moveTo(L,h-B); ctx.lineTo(w-R,h-B); ctx.stroke()
  ctx.beginPath(); ctx.moveTo(L,T); ctx.lineTo(L,h-B); ctx.stroke()

  // Y ticks
  ctx.font='12px system-ui'
  for(let i=0;i<=4;i++){
    const vv=vMin+(i/4)*(vMax-vMin), yy=y(vv)
    ctx.strokeStyle='rgba(255,255,255,0.12)'
    ctx.beginPath(); ctx.moveTo(L,yy); ctx.lineTo(w-R,yy); ctx.stroke()
    ctx.fillStyle='rgba(255,255,255,0.75)'
    ctx.textAlign='right'; ctx.textBaseline='middle'
    ctx.fillText(fmtCurrencyShort(vv), L-8, yy)
  }
  // Y title
  ctx.save(); ctx.translate(16,(h-B+T)/2); ctx.rotate(-Math.PI/2)
  ctx.fillStyle='rgba(255,255,255,0.8)'; ctx.textAlign='center'; ctx.textBaseline='bottom'
  ctx.fillText('סכום התיק (₪)',0,0); ctx.restore()

  // X ticks
  const xTicks=Math.min(6,Math.max(2,Math.floor((w-L-R)/160)))
  for(let i=0;i<=xTicks;i++){
    const tt=tMin+(i/xTicks)*(tMax-tMin), xx=x(tt)
    ctx.strokeStyle='rgba(255,255,255,0.12)'
    ctx.beginPath(); ctx.moveTo(xx,T); ctx.lineTo(xx,h-B); ctx.stroke()
    ctx.fillStyle='rgba(255,255,255,0.75)'
    ctx.textAlign='center'; ctx.textBaseline='top'
    ctx.fillText(formatTimeTick(new Date(tt)), xx, h-B+6)
  }
  // X title
  ctx.fillStyle='rgba(255,255,255,0.8)'; ctx.textAlign='center'; ctx.textBaseline='top'
  ctx.fillText('זמן',(L+(w-R))/2,h-16)

  // line + gradient fill
  ctx.strokeStyle='rgba(110,162,255,0.95)'; ctx.lineWidth=2
  ctx.beginPath()
  series.forEach((p,i)=>{ const px=x(+new Date(p.t)), py=y(p.v); i?ctx.lineTo(px,py):ctx.moveTo(px,py) })
  ctx.stroke()
  const lastX = x(+new Date(series[series.length-1].t))
  const firstX = x(+new Date(series[0].t))
  ctx.lineTo(lastX, h-B); ctx.lineTo(firstX, h-B); ctx.closePath()
  const grd=ctx.createLinearGradient(0,T,0,h-B); grd.addColorStop(0,'rgba(110,162,255,0.25)'); grd.addColorStop(1,'rgba(110,162,255,0)')
  ctx.fillStyle=grd; ctx.fill()

  // hover
  if(hoverIdx!=null && series[hoverIdx]){
    const pt=series[hoverIdx], px=x(+new Date(pt.t)), py=y(pt.v)
    ctx.strokeStyle='rgba(255,255,255,0.35)'; ctx.lineWidth=1
    ctx.beginPath(); ctx.moveTo(px,T); ctx.lineTo(px,h-B); ctx.stroke()
    ctx.fillStyle='#6EA2FF'; ctx.beginPath(); ctx.arc(px,py,3.5,0,Math.PI*2); ctx.fill()
    ctx.strokeStyle='rgba(255,255,255,0.8)'; ctx.beginPath(); ctx.arc(px,py,5.5,0,Math.PI*2); ctx.stroke()

    const label=`${formatTooltipTime(new Date(pt.t))}  |  ${fmtCurrency(pt.v)}`
    ctx.font='12px system-ui'
    const tw=ctx.measureText(label).width, pad=8
    let bx=px+10, by=py-28
    if(bx+tw+pad*2>w-16) bx=px-10-(tw+pad*2)
    if(by<18) by=py+12
    ctx.fillStyle='rgba(20,24,31,0.9)'; roundRect(ctx,bx,by,tw+pad*2,24,6); ctx.fill()
    ctx.strokeStyle='rgba(255,255,255,0.15)'; ctx.stroke()
    ctx.fillStyle='rgba(255,255,255,0.95)'; ctx.textAlign='left'; ctx.textBaseline='middle'
    ctx.fillText(label,bx+pad,by+12)
  }
}

function fmtCurrencyShort(v){ const n=Number(v); if(!isFinite(n))return'-'; if(Math.abs(n)>=1_000_000)return(n/1_000_000).toFixed(1)+'M'; if(Math.abs(n)>=1_000)return(n/1_000).toFixed(1)+'K'; return n.toFixed(0) }
function formatTimeTick(d){ try{ const diff=Math.abs(+d-+new Date()), day=24*3600*1000; if(diff<2*day){ return d.toLocaleTimeString('he-IL',{hour:'2-digit',minute:'2-digit'}) } return d.toLocaleString('he-IL',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) }catch{return String(d)} }
function formatTooltipTime(d){ try{ return d.toLocaleString('he-IL',{year:'2-digit',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) }catch{return String(d)} }
function roundRect(ctx,x,y,w,h,r){ ctx.beginPath(); ctx.moveTo(x+r,y); ctx.arcTo(x+w,y,x+w,y+h,r); ctx.arcTo(x+w,y+h,x,y+h,r); ctx.arcTo(x,y+h,x,y,r); ctx.arcTo(x,y,x+w,y,r); ctx.closePath() }
