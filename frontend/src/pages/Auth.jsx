// frontend/src/pages/Auth.jsx
import { useNavigate } from 'react-router-dom'
import AuthPage from '../AuthPage.jsx'

export default function Auth() {
  const navigate = useNavigate()

  // Called by <AuthPage /> after login/register
  // args example:
  //   [ { access_token: '...', token_type: 'bearer' }, { email: 'x@y.com', flow: 'register' } ]
  const handleAuth = (...args) => {
    // token can be returned either as a plain string or inside an object
    const token =
      args.find(a => typeof a === 'string') ||
      (args[0] && (args[0].access_token || args[0].token))

    // meta contains email + flow: 'login' | 'register'
    const meta = args[1] || args[0] || {}
    const email = meta.email || meta.user?.email || ''
    const flow = String(meta.flow || '').toLowerCase()

    // persist auth info
    if (token) {
      try { localStorage.setItem('token', token) } catch {}
    }
    if (email) {
      try { localStorage.setItem('user_email', email) } catch {}
    }

    // navigation rules:
    // registration -> payment page
    // login -> account page
    const dest = flow === 'register' ? '/pay' : '/account'
    navigate(dest)
  }

  return <AuthPage onAuth={handleAuth} />
}
