import React, { useEffect, useState } from "react";

const API = import.meta.env.VITE_ADMIN_API;

export default function SettingsPage({ auth }) {
  const [settings, setSettings] = useState({ x: "", y: "" });
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");

  async function fetchSettings() {
    setLoading(true);
    setMsg("");
    try {
      const res = await fetch(`${API}/settings`, {
        headers: { Authorization: `Bearer ${auth}` },
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSettings({ x: data.x, y: data.y });
    } catch (e) {
      setMsg(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  async function saveSettings() {
    setMsg("");
    const payload = { x: Number(settings.x), y: Number(settings.y) };
    if (Number.isNaN(payload.x) || Number.isNaN(payload.y)) {
      setMsg("x ו-y חייבים להיות מספרים");
      return;
    }
    try {
      const res = await fetch(`${API}/settings`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${auth}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      await fetchSettings();
      setMsg("ההגדרות נשמרו בהצלחה");
    } catch (e) {
      setMsg(String(e.message || e));
    }
  }

  useEffect(() => {
    fetchSettings();
  }, []);

  return (
    <div style={{ padding: 16, maxWidth: 420 }}>
      <h2>הגדרות</h2>
      {loading && <div>טוען…</div>}
      {msg && <div className="alert" style={{ margin: "8px 0" }}>{msg}</div>}

      <label style={{ display: "block", marginBottom: 8 }}>
        x:
        <input
          type="number"
          className="input"
          value={settings.x}
          onChange={(e) => setSettings((s) => ({ ...s, x: e.target.value }))}
          style={{ marginInlineStart: 8 }}
        />
      </label>

      <label style={{ display: "block", marginBottom: 8 }}>
        y:
        <input
          type="number"
          className="input"
          value={settings.y}
          onChange={(e) => setSettings((s) => ({ ...s, y: e.target.value }))}
          style={{ marginInlineStart: 8 }}
        />
      </label>

      <button className="btn-primary" onClick={saveSettings}>שמור</button>
    </div>
  );
}
