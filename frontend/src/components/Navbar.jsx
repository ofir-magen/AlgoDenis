import { Link, useLocation } from 'react-router-dom'
import logoUrl from '../assets/logo.svg'

export default function Navbar() {
  const { pathname } = useLocation()

  return (
    <header className="navbar">
      <div className="container navbar__row">
        <Link to="/" className="navbar__brand">
          <img src={logoUrl} alt="Algo Trade" />
          <span>Algo&nbsp;Trade</span>
        </Link>

        <nav className="navbar__nav">
          <a href="/#features" className="nav__link">תכונות</a>
          <a href="/#how" className="nav__link">איך זה עובד</a>
          <a href="/#pricing" className="nav__link">תמחור</a>
        </nav>

        <div className="navbar__cta">
          {pathname === '/auth' ? (
            <Link to="/chat" className="btn btn--ghost">לעמוד הצ'אט</Link>
          ) : (
            <Link to="/auth" className="btn btn--primary">כניסה / הרשמה</Link>
          )}
        </div>
      </div>
    </header>
  )
}
