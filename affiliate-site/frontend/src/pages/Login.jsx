import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login } from '../api.js'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const navigate = useNavigate()

  const onSubmit = async (e) => {
    e.preventDefault()
    setErr('')
    try {
      await login(username, password)
      navigate('/dashboard')
    } catch (e) {
      setErr(e.message)
    }
  }

  return (
    <div className="container">
      <div className="card">
        <h2 style={{textAlign:'center'}}>התחברות שותפים</h2>
        <form onSubmit={onSubmit}>
          <input className="input" placeholder="שם משתמש" value={username} onChange={e=>setUsername(e.target.value)} />
          <input className="input" placeholder="סיסמה" type="password" value={password} onChange={e=>setPassword(e.target.value)} />
          <button className="button" type="submit">כניסה</button>
          {err && <div className="helper" style={{color:'var(--danger)'}}>{err}</div>}
          <div className="helper">הכנס פרטי כניסה שסופקו ע"י המנהל</div>
        </form>
      </div>
    </div>
  )
}
