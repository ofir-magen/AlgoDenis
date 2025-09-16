import { Link, NavLink } from 'react-router-dom'
import logoUrl from '../assets/logo.svg'

export default function Navbar() {
  return (
    <nav className="navbar">
      <div
        className="navbar__inner container"
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
      >
        {/* ימין: לוגו */}
        <Link to="/" className="navbar__brand" style={{ display:'flex', alignItems:'center', gap:8 }}>
          <img src={logoUrl} alt="Algo Trade" className="navbar__logo" />
          <span className="navbar__title">Algo Trade</span>
        </Link>

        {/* שמאל: כפתור כניסה */}
        <NavLink to="/auth" className="btn btn--primary">
          כניסה / הרשמה
        </NavLink>
      </div>
    </nav>
  )
}
