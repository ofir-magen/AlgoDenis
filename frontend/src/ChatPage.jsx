// src/ChatPage.jsx
import { useEffect, useState, useRef } from 'react'

const STORAGE_KEY = 'gptPdfAutoMessagesV1'
const MAX_MSGS = 1000

export default function ChatPage({ token, onLogout, WS_BASE }) {
  const [status, setStatus] = useState('disconnected')
  const [messages, setMessages] = useState([])
  const wsRef = useRef(null)
  const backoffRef = useRef(500)
  const seenIdsRef = useRef(new Set())

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) setMessages(parsed.slice(0, MAX_MSGS))
      }
    } catch {}
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(0, MAX_MSGS)))
    } catch {}
  }, [messages])

  useEffect(() => {
    let stopped = false
    function connect() {
      if (stopped) return
      setStatus('connecting')

      if (wsRef.current && (
        wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING
      )) return

      const ws = new WebSocket(`${WS_BASE}?token=${encodeURIComponent(token)}`)
      wsRef.current = ws

      ws.onopen = () => { setStatus('connected'); backoffRef.current = 500 }

      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data)
          const arrivedAt = new Date().toISOString()

          if (data?.id != null && seenIdsRef.current.has(data.id)) return
          if (data?.id != null) seenIdsRef.current.add(data.id)

          const isNewShape = typeof data === 'object' && data && ('answer' in data || 'sources' in data || 'timestamp' in data)
          const isOldReply = data?.type === 'reply'
          const isError = data?.type === 'error' || data?.error

          if (isError) {
            const msgText = data?.error || 'Unknown error'
            setMessages(prev => [{ role: 'system', content: 'Error: ' + msgText, arrivedAt }, ...prev].slice(0, MAX_MSGS))
            return
          }

          if (isOldReply || isNewShape) {
            const m = {
              id: data.id ?? null,
              role: 'assistant',
              content: data.answer ?? data.content ?? '',
              asked: data.asked ?? null,
              report_id: data.report_id ?? null,
              sources: Array.isArray(data.sources) ? data.sources : null,
              at: data.timestamp ?? data.at ?? null,
              arrivedAt
            }
            if (!m.content) m.content = JSON.stringify(data, null, 2)
            setMessages(prev => [m, ...prev].slice(0, MAX_MSGS))
          } else {
            setMessages(prev => [{ role: 'system', content: 'Unknown payload:\n' + JSON.stringify(data, null, 2), arrivedAt }, ...prev].slice(0, MAX_MSGS))
          }
        } catch (e) {
          console.error('Bad WS payload', e)
        }
      }

      ws.onclose = (event) => {
        setStatus('disconnected')
        if (event.code === 4401) {
          console.warn("Unauthorized WebSocket — stopping reconnect.")
          stopped = true // מונע התחברות מחדש
          return
        }
        const delay = Math.min(backoffRef.current, 5000)
        setTimeout(connect, delay)
        backoffRef.current = Math.min(backoffRef.current * 2, 5000)
      }
    }

    connect()
    return () => {
      stopped = true
      try {
        if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) wsRef.current.close()
      } catch {}
    }
  }, [token])

  function clearMessages() {
    setMessages([]); try { localStorage.removeItem(STORAGE_KEY) } catch {}
    seenIdsRef.current = new Set()
  }

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        <header style={styles.header}>
          <h1 style={styles.h1}>GPT + Sources (Auto)</h1>
          <div style={styles.statusRow}>
            <span style={{ ...styles.statusDot, background: status === 'connected' ? '#2ecc71' : status === 'connecting' ? '#f1c40f' : '#e74c3c' }} />
            <span style={styles.muted}>Status: {status}</span>
            <div style={{ flex: 1 }} />
            <button onClick={clearMessages} style={styles.clearBtn}>Clear</button>
            <button onClick={onLogout} style={{...styles.clearBtn, marginLeft:8}}>Logout</button>
          </div>
        </header>

        <section style={styles.listWrap}>
          <ul style={styles.list}>
            {messages.map((m, idx) => (
              <li key={`${m.role}-${m.at || m.arrivedAt || idx}-${idx}`} style={styles.item}>
                <div style={styles.itemHeader}>
                  <span style={{...styles.badge, background: badgeColor(m.role)}}>{labelFor(m.role)}</span>
                  {m.id != null && <span style={styles.idBadge}>#{m.id}</span>}
                  {m.report_id && <span style={styles.idBadge}>PDF:{m.report_id}</span>}
                  <span style={styles.arrivedAt}>{new Date(m.at || m.arrivedAt).toLocaleTimeString()}</span>
                </div>
                {m.asked && <div style={styles.row}><span style={styles.label}>Prompt</span><pre style={styles.pre}>{m.asked}</pre></div>}
                {Array.isArray(m.sources) && m.sources.length > 0 && <div style={styles.row}><span style={styles.label}>Sources</span><pre style={styles.pre}>{m.sources.join('\n')}</pre></div>}
                <div style={styles.row}><span style={styles.label}>Content</span><pre style={styles.pre}>{m.content}</pre></div>
              </li>
            ))}
            {messages.length === 0 && (
              <li style={{ ...styles.item, textAlign: 'center', opacity: 0.6 }}>
                ממתין לשידור מהשרת…
              </li>
            )}
          </ul>
        </section>
      </div>
    </div>
  )
}

function labelFor(role) {
  if (role === 'user') return 'User'
  if (role === 'assistant') return 'Assistant'
  if (role === 'system') return 'System'
  return role || 'Message'
}
function badgeColor(role) {
  if (role === 'user') return '#7ee787'
  if (role === 'assistant') return '#1f6feb'
  if (role === 'system') return '#d29922'
  return '#666'
}

const styles = {
  page: { display:'flex', alignItems:'center', justifyContent:'center', minHeight:'100vh', padding:24, background:'#0b1117', color:'#e6edf3' },
  card: { width:'100%', maxWidth:1000, background:'#0e1621', border:'1px solid #263341', borderRadius:16, padding:24 },
  header: { marginBottom: 12 },
  h1: { margin: 0, fontSize: 24, fontWeight: 700 },
  statusRow: { display: 'flex', alignItems: 'center', gap: 10, marginTop: 8 },
  statusDot: { width: 10, height: 10, borderRadius: '50%', display: 'inline-block' },
  muted: { opacity: 0.7 },
  clearBtn: { background: 'transparent', color: '#e6edf3', border: '1px solid #3b4b5c', padding: '6px 10px', borderRadius: 8, cursor: 'pointer' },
  listWrap: { marginTop: 8, maxHeight: '60vh', overflow: 'auto', borderRadius: 12, border: '1px solid #263341' },
  list: { listStyle: 'none', margin: 0, padding: 0 },
  item: { padding: 12, borderBottom: '1px solid #263341', background: 'linear-gradient(180deg, rgba(20,29,39,.6), rgba(14,22,33,.4))' },
  itemHeader: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 },
  badge: { color: 'white', borderRadius: 9999, padding: '2px 8px', fontSize: 12, fontWeight: 700 },
  idBadge: { marginLeft: 6, background: '#263341', borderRadius: 9999, padding: '1px 6px', fontSize: 11, opacity: 0.9 },
  arrivedAt: { marginLeft: 'auto', opacity: 0.7, fontSize: 12 },
  row: { display: 'flex', gap: 8, marginTop: 6, flexWrap: 'wrap' },
  label: { minWidth: 64, padding: '2px 6px', borderRadius: 6, background: '#0b1620', border: '1px solid #1d2b3a', fontSize: 12, opacity: 0.85 },
  pre: { whiteSpace: 'pre-wrap', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, Courier New, monospace', background: '#0b1620', border: '1px solid #1d2b3a', borderRadius: 6, padding: '6px 8px', margin: 0, flex: 1, fontSize: 14 }
}
