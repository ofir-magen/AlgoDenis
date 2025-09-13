// frontend/src/pages/Login.jsx
import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login } from '../api.js'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const navigate = useNavigate()

  const onSubmit = async (e) => {
    e.preventDefault()
    setErr('')

    try {
      // העברת המייל בפרמטר username (תקן OAuth2PasswordRequestForm)
      await login(email, password)
      navigate('/dashboard')
    } catch (e) {
      setErr(e.message)
    }
  }

  return (
    <div className="container">
      <div className="card">
        <h2 style={{textAlign:'center'}}>התחברות</h2>
        <form onSubmit={onSubmit}>
          <input
            className="input"
            placeholder="אימייל"
            type="email"
            value={email}
            onChange={e=>setEmail(e.target.value)}
            required
          />
          <input
            className="input"
            placeholder="סיסמה"
            type="password"
            value={password}
            onChange={e=>setPassword(e.target.value)}
            required
          />
          <button className="button" type="submit">כניסה</button>
          {err && <div className="helper" style={{color:'var(--danger)'}}>{err}</div>}
        </form>
      </div>
    </div>
  )
}
