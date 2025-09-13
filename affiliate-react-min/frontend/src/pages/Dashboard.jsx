import React, { useEffect, useState } from 'react'
import { authedGet, logout } from '../api.js'
import { useNavigate } from 'react-router-dom'

export default function Dashboard() {
  const [msg, setMsg] = useState('טוען...')
  const [username, setUsername] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    Promise.all([authedGet('/me'), authedGet('/dashboard/data')])
      .then(([me, data]) => {
        setUsername(me.username)
        setMsg(data.message)
      })
      .catch(() => navigate('/login'))
  }, [])

  return (
    <div className="container">
      <div className="card" style={{textAlign:'center'}}>
        <h2>דאשבורד</h2>
        <div className="helper">{msg}</div>
        {username && <div className="helper">משתמש: {username}</div>}
        <button className="button" style={{marginTop:16}} onClick={() => { logout(); navigate('/login'); }}>התנתקות</button>
      </div>
    </div>
  )
}
