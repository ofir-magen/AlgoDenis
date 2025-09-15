import React, { useState } from "react";
import { BrowserRouter, Routes, Route, Navigate, NavLink } from "react-router-dom";
import LoginPage from "./pages/LoginPage.jsx";
import UsersPage from "./pages/UsersPage.jsx";
import LogsPage from "./pages/LogsPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";

export default function App() {
  const [auth, setAuth] = useState(() => localStorage.getItem("admin_token") || "");

  function handleLoggedIn(token) {
    localStorage.setItem("admin_token", token);
    setAuth(token);
  }

  function logout() {
    localStorage.removeItem("admin_token");
    setAuth("");
  }

  if (!auth) {
    return <LoginPage onLoggedIn={handleLoggedIn} />;
  }

  return (
    <BrowserRouter>
      <div className="admin-shell">
        {/* Top navigation bar */}
        <header className="topbar" style={{ gap: 8 }}>
          <div className="left" />
          <div className="middle" style={{ display: "flex", gap: 8, justifyContent: "center", flex: 1 }}>
            <NavLink to="/users" className={({ isActive }) => `btn-secondary ${isActive ? "active" : ""}`}>
              משתמשים
            </NavLink>
            <NavLink to="/logs" className={({ isActive }) => `btn-secondary ${isActive ? "active" : ""}`}>
              לוגים
            </NavLink>
            <NavLink to="/settings" className={({ isActive }) => `btn-secondary ${isActive ? "active" : ""}`}>
              הגדרות
            </NavLink>
          </div>
          <div className="right">
            <button className="btn-outline" onClick={logout}>התנתק</button>
          </div>
        </header>

        {/* Routes */}
        <Routes>
          <Route path="/" element={<Navigate to="/users" replace />} />
          <Route path="/users" element={<UsersPage auth={auth} />} />
          <Route path="/logs" element={<LogsPage auth={auth} />} />
          <Route path="/settings" element={<SettingsPage auth={auth} />} />
          {/* fallback */}
          <Route path="*" element={<Navigate to="/users" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
