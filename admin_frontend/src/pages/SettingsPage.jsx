// src/pages/SettingsPage.jsx
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";

const API = import.meta.env.VITE_ADMIN_API;

function apiFetch(path, init = {}) {
  const token = localStorage.getItem("admin_token");
  return fetch(`${API}${path}`, {
    ...init,
    headers: {
      ...(init.headers || {}),
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
}

export default function SettingsPage() {
  const [settings, setSettings] = useState({
    min1: "",
    max1: "",
    min2: "",
    max2: "",
  });
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");

  async function fetchSettings() {
    setLoading(true);
    setMsg("");
    try {
      const res = await apiFetch("/settings");
      if (res.status === 401) {
        localStorage.removeItem("admin_token");
        window.location.href = "/login";
        return;
      }
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();

      setSettings({
        min1: data.min1 ?? "",
        max1: data.max1 ?? "",
        min2: data.min2 ?? "",
        max2: data.max2 ?? "",
      });
    } catch (e) {
      setMsg(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  async function saveSettings() {
    setMsg("");

    const payload = {
      min1: Number(settings.min1),
      max1: Number(settings.max1),
      min2: Number(settings.min2),
      max2: Number(settings.max2),
    };

    if (
      [payload.min1, payload.max1, payload.min2, payload.max2].some((v) =>
        Number.isNaN(v)
      )
    ) {
      setMsg("כל השדות חייבים להיות מספרים");
      return;
    }

    try {
      const res = await apiFetch("/settings", {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      if (res.status === 401) {
        localStorage.removeItem("admin_token");
        window.location.href = "/login";
        return;
      }
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
    <div style={{ padding: 16, maxWidth: 600, direction: "rtl" }}>
      <h2>הגדרות</h2>
      {loading && <div>טוען…</div>}
      {msg && (
        <div className="alert" style={{ margin: "8px 0" }}>
          {msg}
        </div>
      )}

      {/* שורה 1: min1  <= (up - down) <=  max1 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 12,
        }}
      >
        <label style={{ display: "flex", flexDirection: "column" }}>
          <span>min1</span>
          <input
            type="number"
            className="input"
            value={settings.min1}
            onChange={(e) =>
              setSettings((s) => ({ ...s, min1: e.target.value }))
            }
          />
        </label>

        <span style={{ whiteSpace: "nowrap" }}>
          {"<= (up - down) <="}
        </span>

        <label style={{ display: "flex", flexDirection: "column" }}>
          <span>max1</span>
          <input
            type="number"
            className="input"
            value={settings.max1}
            onChange={(e) =>
              setSettings((s) => ({ ...s, max1: e.target.value }))
            }
          />
        </label>
      </div>

      {/* שורה 2: min2  <= (up - stable) <=  max2 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 12,
        }}
      >
        <label style={{ display: "flex", flexDirection: "column" }}>
          <span>min2</span>
          <input
            type="number"
            className="input"
            value={settings.min2}
            onChange={(e) =>
              setSettings((s) => ({ ...s, min2: e.target.value }))
            }
          />
        </label>

        <span style={{ whiteSpace: "nowrap" }}>
          {"<= (up - stable) <="}
        </span>

        <label style={{ display: "flex", flexDirection: "column" }}>
          <span>max2</span>
          <input
            type="number"
            className="input"
            value={settings.max2}
            onChange={(e) =>
              setSettings((s) => ({ ...s, max2: e.target.value }))
            }
          />
        </label>
      </div>

      <button className="btn-primary" onClick={saveSettings}>
        שמור
      </button>

      <div style={{ marginTop: 12 }}>
        <Link to="/data" className="topbtn">
          פתח Data
        </Link>
      </div>
    </div>
  );
}
