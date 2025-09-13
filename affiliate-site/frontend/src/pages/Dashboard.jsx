import React, { useEffect, useState } from 'react'
import { getMe, getDashboardData, logout } from '../api.js'
import { useNavigate } from 'react-router-dom'

export default function Dashboard() {
  const [username, setUsername] = useState('')
  const [msg, setMsg] = useState('טוען...')
  const navigate = useNavigate()

  useEffect(() => {
    Promise.all([getMe(), getDashboardData()]).then(([me, data]) => {
      setUsername(me.username)
      setMsg('מחובר! ' + (data?.message || ''))
    }).catch(() => {
      navigate('/login')
    })
  }, [])

  return (
    <div className="container">
      <div className="card" style={{textAlign:'center'}}>
        <h2>דאשבורד שותפים</h2>
        <div className="helper">{msg}</div>
        {username && <div className="helper">משתמש: {username}</div>}
        <button className="button" style={{marginTop:16}} onClick={() => { logout(); navigate('/login'); }}>
          התנתקות
        </button>
      </div>
    </div>
  )
}
