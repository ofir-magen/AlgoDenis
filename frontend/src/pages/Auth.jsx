import { useNavigate } from 'react-router-dom'
import AuthPage from '../AuthPage.jsx'

export default function Auth() {
  const navigate = useNavigate()

  const handleAuth = (...args) => {
    const token =
      args.find(a => typeof a === 'string') ||
      (args[0] && (args[0].access_token || args[0].token))

    // אם ה-AuthPage לא שומר מייל, נשמור אותו כאן כדי שיופיע ב-/pay
    const emailObj = args[1] || args[0] || {}
    const email = emailObj.email || emailObj.user?.email || ''

    if (token) {
      try { localStorage.setItem('token', token) } catch {}
    }
    if (email) {
      try { localStorage.setItem('user_email', email) } catch {}
    }

    // אחרי הרשמה/כניסה → דף תשלום
    navigate('/pay')
  }

  return <AuthPage onAuth={handleAuth} />
}
