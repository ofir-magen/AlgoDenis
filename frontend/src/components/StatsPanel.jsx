// src/components/StatsPanel.jsx
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'

export default function StatsPanel({ apiBase }) {
  const API_BASE = useMemo(() => {
    if (apiBase) return apiBase.replace(/\/+$/, '')
    const envUrl = import.meta.env.VITE_API_URL
    if (envUrl) return envUrl.replace(/\/+$/, '')
    const isHttps = typeof window !== 'undefined' && window.location.protocol === 'https:'
    const host = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1'
    return `${isHttps ? 'https' : 'http'}://${host}:8000/api`
  }, [apiBase])

  // form state
  const [start, setStart] = useState(defaultStartISO())
  const [capital, setCapital] = useState(10000)
  const [riskPct, setRiskPct] = useState(10)

  // data + results
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [series, setSeries] = useState([])
  const [summary, setSummary] = useState(null)

  // chart refs
  const canvasRef = useRef(null)
  const chartWrapRef = useRef(null)
  const [hoverIdx, setHoverIdx] = useState(null)

  async function handleRun(e) {
    e.preventDefault()
    setError(''); setLoading(true); setSeries([]); setSummary(null); setHoverIdx(null)
    try {
      const res = await fetch(`${API_BASE}/positions/by-range?start=${encodeURIComponent(start)}`)
      if (!res.ok) throw new Error(`API error ${res.status}`)
      const rows = await res.json()
      if (!Array.isArray(rows) || rows.length === 0) {
        setSummary({ points: 0, final: Number(capital), totalChangePct: 0 }); return
      }
      rows.sort((a,b) => new Date(a.trade_date) - new Date(b.trade_date))

      // Allocation mode (A)
      let cur = Number(capital), risk = Math.max(0, Number(riskPct)) / 100
      const pts = []
      for (const r of rows) {
        const t = new Date(r.trade_date)
        const change = Number(r.change_pct || 0) / 100
        const pnl = (cur * risk) * change
        cur += pnl
        pts.push({ t, v: cur })
      }
      setSeries(pts)
      setSummary({ points: rows.length, final: cur, totalChangePct: ((cur - Number(capital))/Number(capital))*100 })
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
      const w = wrap.clientWidth, h = wrap.clientHeight
      c.width = Math.max(1, Math.floor(w * dpr))
      c.height = Math.max(1, Math.floor(h * dpr))
      c.style.width = w + 'px'
      c.style.height = h + 'px'
      const ctx = c.getContext('2d')
      // set transform ONCE: we will draw using CSS units
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
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
      const padL=60,padR=16,padT=18,padB=40
      const w = rect.width
      const tMin = +new Date(series[0].t)
      const tMax = +new Date(series[series.length-1].t)
      const xOf = t => padL + (((t - tMin) / (tMax - tMin || 1)) * (w - padL - padR))
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

  return (
    <div style={{ height:'100%', display:'flex', flexDirection:'column', gap:12 }}>
      {/* Form row */}
      <form onSubmit={handleRun} className="glass" style={{ padding: 16 }}>
        <div style={{
          display:'grid',
          gridTemplateColumns:'minmax(220px,1fr) minmax(160px,1fr) minmax(180px,1fr) auto',
          gap:12, alignItems:'end'
        }}>
          <Field label="תאריך התחלה">
            <input type="datetime-local" value={localDateTimeForInput(start)} onChange={e=>setStart(toISOFromLocalInput(e.target.value))} className="input"/>
          </Field>
          <Field label="סכום תיק (₪)">
            <input type="number" min="0" step="100" value={capital} onChange={e=>setCapital(e.target.value)} className="input" placeholder="10000"/>
          </Field>
          <Field label="אחוז סיכון מהתיק (%)">
            <input type="number" min="0" max="100" step="0.1" value={riskPct} onChange={e=>setRiskPct(e.target.value)} className="input" placeholder="10"/>
          </Field>
          <div style={{ display:'flex', justifyContent:'flex-end' }}>
            <button type="submit" className="btn btn--primary" disabled={loading} style={{ height:42 }}>הרץ ניתוח</button>
          </div>
        </div>
        <div style={{ marginTop: 8 }}>
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

// ===== Helpers =====
function defaultStartISO(){ const d=new Date(Date.now()-7*24*3600*1000); return d.toISOString().slice(0,19) }
function localDateTimeForInput(s){ try{return s.slice(0,16)}catch{return''} }
function toISOFromLocalInput(s){ return s ? s + ':00' : '' }
function fmtCurrency(v){ if(!isFinite(v))return'-'; return new Intl.NumberFormat('he-IL',{style:'currency',currency:'ILS',maximumFractionDigits:2}).format(Number(v)) }
function fmtPct(v){ if(!isFinite(v))return'-'; const n=Number(v); return (n>0?'+':'')+n.toFixed(2)+'%' }

// ===== Chart (works in CSS units; DPR handled by context transform) =====
function drawChart(canvas, series, hoverIdx=null){
  const ctx = canvas.getContext('2d')
  const dpr = window.devicePixelRatio || 1
  const w = canvas.width / dpr
  const h = canvas.height / dpr

  // DO NOT reset transform; we already setTransform(dpr,0,0,dpr,0,0) on resize
  ctx.clearRect(0,0,w,h)

  if(!series.length){
    ctx.fillStyle='rgba(255,255,255,0.7)'
    ctx.font='14px system-ui'
    ctx.fillText('אין נתונים להצגה. הרץ ניתוח.', 16, 24)
    return
  }

  const padL=60,padR=16,padT=18,padB=40
  const tMin=+new Date(series[0].t), tMax=+new Date(series[series.length-1].t)
  let vMin=Math.min(...series.map(p=>p.v)), vMax=Math.max(...series.map(p=>p.v))
  if(vMin===vMax){vMin-=1;vMax+=1}

  const x = t => padL + (((t - tMin) / (tMax - tMin || 1)) * (w - padL - padR))
  const y = v => padT + ((1 - ((v - vMin) / (vMax - vMin || 1))) * (h - padT - padB))

  // axes
  ctx.strokeStyle='rgba(255,255,255,0.25)'; ctx.lineWidth=1
  ctx.beginPath(); ctx.moveTo(padL,h-padB); ctx.lineTo(w-padR,h-padB); ctx.stroke()
  ctx.beginPath(); ctx.moveTo(padL,padT); ctx.lineTo(padL,h-padB); ctx.stroke()

  // Y ticks
  ctx.font='12px system-ui'
  for(let i=0;i<=4;i++){
    const vv=vMin+(i/4)*(vMax-vMin), yy=y(vv)
    ctx.strokeStyle='rgba(255,255,255,0.12)'
    ctx.beginPath(); ctx.moveTo(padL,yy); ctx.lineTo(w-padR,yy); ctx.stroke()
    ctx.fillStyle='rgba(255,255,255,0.75)'
    ctx.textAlign='right'; ctx.textBaseline='middle'
    ctx.fillText(fmtCurrencyShort(vv), padL-8, yy)
  }
  // Y title
  ctx.save(); ctx.translate(16,(h-padB+padT)/2); ctx.rotate(-Math.PI/2)
  ctx.fillStyle='rgba(255,255,255,0.8)'; ctx.textAlign='center'; ctx.textBaseline='bottom'
  ctx.fillText('סכום התיק (₪)',0,0); ctx.restore()

  // X ticks
  const xTicks=Math.min(6,Math.max(2,Math.floor((w-padL-padR)/160)))
  for(let i=0;i<=xTicks;i++){
    const tt=tMin+(i/xTicks)*(tMax-tMin), xx=x(tt)
    ctx.strokeStyle='rgba(255,255,255,0.12)'
    ctx.beginPath(); ctx.moveTo(xx,padT); ctx.lineTo(xx,h-padB); ctx.stroke()
    ctx.fillStyle='rgba(255,255,255,0.75)'
    ctx.textAlign='center'; ctx.textBaseline='top'
    ctx.fillText(formatTimeTick(new Date(tt)), xx, h-padB+6)
  }
  // X title
  ctx.fillStyle='rgba(255,255,255,0.8)'; ctx.textAlign='center'; ctx.textBaseline='top'
  ctx.fillText('זמן',(padL+(w-padR))/2,h-16)

  // line + fill
  ctx.strokeStyle='rgba(110,162,255,0.95)'; ctx.lineWidth=2
  ctx.beginPath()
  series.forEach((p,i)=>{ const px=x(+new Date(p.t)), py=y(p.v); i?ctx.lineTo(px,py):ctx.moveTo(px,py) })
  ctx.stroke()
  const lastX = x(+new Date(series[series.length-1].t))
  const firstX = x(+new Date(series[0].t))
  ctx.lineTo(lastX, h-padB); ctx.lineTo(firstX, h-padB); ctx.closePath()
  const grd=ctx.createLinearGradient(0,padT,0,h-padB); grd.addColorStop(0,'rgba(110,162,255,0.25)'); grd.addColorStop(1,'rgba(110,162,255,0)')
  ctx.fillStyle=grd; ctx.fill()

  // hover
  if(hoverIdx!=null && series[hoverIdx]){
    const pt=series[hoverIdx], px=x(+new Date(pt.t)), py=y(pt.v)
    ctx.strokeStyle='rgba(255,255,255,0.35)'; ctx.lineWidth=1
    ctx.beginPath(); ctx.moveTo(px,padT); ctx.lineTo(px,h-padB); ctx.stroke()
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
