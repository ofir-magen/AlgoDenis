import React, { useState } from "react";

const API = import.meta.env.VITE_ADMIN_API;

export default function LoginPage({ onLoggedIn }) {
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function login(e) {
    e.preventDefault();
    setErr("");
    setLoading(true);
    try {
      const res = await fetch(`${API}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: u, password: p }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const token = data.token;
      if (!token) throw new Error("שרת לא החזיר token");
      onLoggedIn(token);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-screen">
      <div className="bg-blobs" aria-hidden />
      <form className="auth-card" onSubmit={login}>
        <div className="brand">
          <div className="logo-dot" />
          <h1>Admin Console</h1>
          <p>ניהול משתמשים ומנויים</p>
        </div>

        <label>שם משתמש</label>
        <input
          className="input"
          placeholder="admin"
          value={u}
          onChange={(e) => setU(e.target.value)}
          dir="ltr"
          autoFocus
        />

        <label>סיסמה</label>
        <input
          className="input"
          placeholder="••••••••"
          type="password"
          value={p}
          onChange={(e) => setP(e.target.value)}
          dir="ltr"
        />

        {err ? <div className="alert">{err}</div> : null}

        <button className="btn-primary" type="submit" disabled={loading}>
          {loading ? "מתחבר…" : "כניסה"}
        </button>

        <div className="footnote">© {new Date().getFullYear()} Algo Admin</div>
      </form>
    </div>
  );
}
