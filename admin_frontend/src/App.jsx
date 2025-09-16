// src/App.jsx
import React from "react"
import { BrowserRouter, Routes, Route, Navigate, NavLink } from "react-router-dom"
import LoginPage from "./pages/LoginPage.jsx"
import UsersPage from "./pages/UsersPage.jsx"
import LogsPage from "./pages/LogsPage.jsx"
import SettingsPage from "./pages/SettingsPage.jsx"

function RequireAuth({ children }) {
  const token = localStorage.getItem("admin_token")   // ← משתמשים במפתח הקיים
  return token ? children : <Navigate to="/login" replace />
}

export default function App() {
  const logout = () => {
    localStorage.removeItem("admin_token")            // ← מוחקים את המפתח הקיים
    window.location.href = "/login"
  }

  // יעבור ל-LoginPage ויקבל את ה-token מהשרת
  const handleLoggedIn = (token) => {
    if (token) localStorage.setItem("admin_token", token)
    window.location.href = "/users"
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/users" replace />} />
        <Route path="/login" element={<LoginPage onLoggedIn={handleLoggedIn} />} /> {/* ← מעבירים onLoggedIn */}
        <Route
          path="/users"
          element={
            <RequireAuth>
              <Header logout={logout} />
              <UsersPage />
            </RequireAuth>
          }
        />
        <Route
          path="/logs"
          element={
            <RequireAuth>
              <Header logout={logout} />
              <LogsPage />
            </RequireAuth>
          }
        />
        <Route
          path="/settings"
          element={
            <RequireAuth>
              <Header logout={logout} />
              <SettingsPage />
            </RequireAuth>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}

function Header({ logout }) {
  return (
    <header className="topbar" style={{ gap: 8 }}>
      <div className="left" />
      <div className="middle" style={{ flex: 1, display: "flex", justifyContent: "center" }}>
        <nav className="segmented">
          <NavLink to="/users" className={({isActive}) => `segmented__btn ${isActive ? "active" : ""}`}>משתמשים</NavLink>
          <NavLink to="/logs" className={({isActive}) => `segmented__btn ${isActive ? "active" : ""}`}>לוגים</NavLink>
          <NavLink to="/settings" className={({isActive}) => `segmented__btn ${isActive ? "active" : ""}`}>הגדרות</NavLink>
        </nav>
      </div>
      <div className="right">
        <button className="btn-outline" onClick={logout}>התנתק</button>
      </div>
    </header>
  )
}
