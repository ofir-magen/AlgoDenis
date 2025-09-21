// src/pages/DataLogPage.jsx
import React, { useEffect, useMemo, useRef, useState } from "react";

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

const LABELS = {
  id: "ID",
  symbol: "סימבול",
  signal_type: "סוג איתות",
  entry_time: "כניסה",
  entry_price: "מחיר כניסה",
  exit_time: "יציאה",
  exit_price: "מחיר יציאה",
  change_pct: "שינוי %",
  created_at: "נוצר",
  updated_at: "עודכן",
};
const ORDER = [
  "id",
  "symbol",
  "signal_type",
  "entry_time",
  "entry_price",
  "exit_time",
  "exit_price",
  "change_pct",
  "created_at",
  "updated_at",
];
const EXCLUDE = new Set(["assigned"]); // לא מציגים assigned
const IMMUTABLE = new Set(["id", "created_at", "updated_at", "assigned"]);

function calcChangePct(entryPrice, exitPrice) {
  const a = Number(entryPrice);
  const b = Number(exitPrice);
  if (!isFinite(a) || !isFinite(b) || a === 0) return null;
  return ((b - a) / a) * 100;
}
function calcFactor(entryPrice, exitPrice) {
  const a = Number(entryPrice);
  const b = Number(exitPrice);
  if (!isFinite(a) || !isFinite(b) || a === 0) return null;
  return b / a;
}

function formatDateTime(s) {
  if (!s) return "";
  const d = new Date(String(s).replace(" ", "T"));
  if (isNaN(d)) return String(s);
  return d.toLocaleString("he-IL", { hour12: false });
}
function toDatetimeLocalValue(s) {
  if (!s) return "";
  const d = new Date(String(s).replace(" ", "T"));
  if (isNaN(d)) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** === DateTimeField: שדה עם פתיחה אוטומטית של הבורר (כמו בסטטיסטיקה) === */
function DateTimeField({ label, value, onChange, className = "search", style }) {
  const inputRef = useRef(null);
  const val = value || "";

  function openPicker() {
    const el = inputRef.current;
    if (!el) return;
    if (typeof el.showPicker === "function") {
      try { el.showPicker(); return; } catch {}
    }
    el.focus(); el.click();
  }

  return (
    <div>
      <label style={{ display: "block", fontSize: 12, opacity: 0.8, marginBottom: 4 }}>{label}</label>
      <input
        ref={inputRef}
        type="datetime-local"
        step="60"
        className={className}
        style={{ width: "100%", ...(style || {}) }}
        value={val}
        onFocus={openPicker}
        onClick={openPicker}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

/** לשימוש בתוך תא עריכה בטבלה */
function DateTimeInlineCell({ value, onChange }) {
  const [v, setV] = useState(value || "");
  const inputRef = useRef(null);
  useEffect(() => setV(value || ""), [value]);

  function openPicker() {
    const el = inputRef.current;
    if (!el) return;
    if (typeof el.showPicker === "function") {
      try { el.showPicker(); return; } catch {}
    }
    el.focus(); el.click();
  }

  return (
    <input
      ref={inputRef}
      type="datetime-local"
      step="60"
      className="cell-input"
      value={v}
      onFocus={openPicker}
      onClick={openPicker}
      onChange={(e) => { setV(e.target.value); onChange(e.target.value); }}
    />
  );
}

export default function DataLogPage() {
  const [err, setErr] = useState("");
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState("");
  const [sorters, setSorters] = useState([]);

  const [editRowId, setEditRowId] = useState(null);
  const [editDraft, setEditDraft] = useState({});

  // Add form
  const [addForm, setAddForm] = useState({
    symbol: "",
    signal_type: "",
    entry_time: "",
    entry_price: "",
    exit_time: "",
    exit_price: "",
  });
  const [adding, setAdding] = useState(false);

  async function load() {
    setErr("");
    try {
      const res = await apiFetch("/datalog");
      if (res.status === 401) {
        localStorage.removeItem("admin_token");
        window.location.href = "/login";
        return;
      }
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setRows(Array.isArray(data) ? data : []);
    } catch (e) {
      setErr(String(e.message || e));
    }
  }

  const columns = useMemo(() => {
    const present = new Set(ORDER);
    for (const r of rows) {
      for (const k of Object.keys(r || {})) {
        if (!EXCLUDE.has(k)) present.add(k);
      }
    }
    const rest = Array.from(present).filter((k) => !ORDER.includes(k));
    return [...ORDER, ...rest];
  }, [rows]);

  const filtered = useMemo(() => {
    const q = (filter || "").toLowerCase().trim();
    if (!q) return rows;
    return rows.filter((r) =>
      Object.entries(r ?? {}).some(([k, v]) => {
        if (EXCLUDE.has(k)) return false;
        return String(v ?? "").toLowerCase().includes(q);
      })
    );
  }, [rows, filter]);

  const sorted = useMemo(() => {
    if (!sorters.length) return filtered;
    const arr = [...filtered];
    arr.sort((a, b) => {
      for (const s of sorters) {
        const av = a?.[s.key];
        const bv = b?.[s.key];
        let cmp;
        if (["entry_time", "exit_time", "created_at", "updated_at"].includes(s.key)) {
          const ad = new Date(String(av || "").replace(" ", "T")).getTime() || 0;
          const bd = new Date(String(bv || "").replace(" ", "T")).getTime() || 0;
          cmp = ad === bd ? 0 : ad < bd ? -1 : 1;
        } else if (!isNaN(Number(av)) && !isNaN(Number(bv))) {
          const an = Number(av), bn = Number(bv);
          cmp = an === bn ? 0 : an < bn ? -1 : 1;
        } else {
          cmp = String(av ?? "").localeCompare(String(bv ?? ""), "he", { numeric: true, sensitivity: "base" });
        }
        if (cmp !== 0) return s.dir === "desc" ? -cmp : cmp;
      }
      return 0;
    });
    return arr;
  }, [filtered, sorters]);

  function toggleSort(key) {
    setSorters((prev) => {
      const idx = prev.findIndex((s) => s.key === key);
      if (idx === -1) return [...prev, { key, dir: "asc" }];
      const cur = prev[idx];
      if (cur.dir === "asc") {
        const n = [...prev]; n[idx] = { key, dir: "desc" }; return n;
      }
      const n = [...prev]; n.splice(idx, 1); return n;
    });
  }
  function sorterIndicator(key) {
    const i = sorters.findIndex((s) => s.key === key);
    if (i === -1) return "";
    return sorters[i].dir === "asc" ? " ↑" : " ↓";
  }

  function beginEdit(r) {
    setEditRowId(r.id);
    setEditDraft({ ...r });
  }
  function cancelEdit() {
    setEditRowId(null);
    setEditDraft({});
  }
  function changeDraft(key, val) {
    setEditDraft((d) => ({ ...d, [key]: val }));
  }

  async function saveEdit() {
    if (editRowId == null) return;
    setErr("");
    try {
      const payload = { ...editDraft };
      for (const k of Object.keys(payload)) {
        if (IMMUTABLE.has(k)) delete payload[k];
      }
      // נרמול זמנים (לפורמט DB)
      for (const k of ["entry_time", "exit_time"]) {
        if (k in payload && payload[k]) {
          const v = String(payload[k]);
          if (v.includes("T")) payload[k] = (/\d{2}:\d{2}$/.test(v) ? v + ":00" : v).replace("T", " ");
        }
      }
      // נרמול מספרים
      for (const k of ["entry_price", "exit_price"]) {
        if (k in payload) {
          const vv = String(payload[k]).trim();
          payload[k] = vv === "" ? null : Number(vv);
        }
      }
      // שינוי% אם אפשר
      const cp = calcChangePct(payload.entry_price ?? editDraft.entry_price, payload.exit_price ?? editDraft.exit_price);
      if (cp != null) payload.change_pct = Number(cp.toFixed(6));

      const res = await apiFetch(`/datalog/${editRowId}`, {
        method: "PUT",
        body: JSON.stringify({ data: payload }),
      });
      if (res.status === 401) { localStorage.removeItem("admin_token"); window.location.href = "/login"; return; }
      if (!res.ok) throw new Error(await res.text());
      await load();
      cancelEdit();
    } catch (e) {
      setErr(String(e.message || e));
    }
  }

  async function delRow(id) {
    if (!confirm("למחוק רשומה זו?")) return;
    setErr("");
    try {
      const res = await apiFetch(`/datalog/${id}`, { method: "DELETE" });
      if (res.status === 401) { localStorage.removeItem("admin_token"); window.location.href = "/login"; return; }
      if (!res.ok) throw new Error(await res.text());
      await load();
    } catch (e) {
      setErr(String(e.message || e));
    }
  }

  async function addRow() {
    setErr("");
    setAdding(true);
    try {
      const payload = { ...addForm };
      // נרמול זמנים
      for (const k of ["entry_time", "exit_time"]) {
        const v = payload[k];
        if (v && v.includes("T")) {
          // אם אין שניות – נוסיף ":00"
          payload[k] = (/\d{2}:\d{2}$/.test(v) ? v + ":00" : v).replace("T", " ");
        }
      }
      // נרמול מספרים
      ["entry_price", "exit_price"].forEach((k) => {
        const v = payload[k];
        payload[k] = v === "" || v == null ? null : Number(v);
      });
      // שינוי% אוטומטי
      const cp = calcChangePct(payload.entry_price, payload.exit_price);
      if (cp != null) payload.change_pct = Number(cp.toFixed(6));

      const res = await apiFetch("/datalog", { method: "POST", body: JSON.stringify(payload) });
      if (res.status === 401) { localStorage.removeItem("admin_token"); window.location.href = "/login"; return; }
      if (!res.ok) throw new Error(await res.text());
      setAddForm({ symbol: "", signal_type: "", entry_time: "", entry_price: "", exit_time: "", exit_price: "" });
      await load();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setAdding(false);
    }
  }

  useEffect(() => { load(); }, []);

  const addChangePct = calcChangePct(addForm.entry_price, addForm.exit_price);
  const addFactor = calcFactor(addForm.entry_price, addForm.exit_price);

  return (
    <div className="admin-shell">
      {/* סרגל עליון */}
      <div className="topbar" style={{ marginTop: 12, flexWrap: "wrap", gap: 12 }}>
        <div className="left" style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <button className="btn-secondary" onClick={load}>רענן</button>
          <input className="search" placeholder="חיפוש בכל השדות…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
        <div className="right" />
      </div>

      {/* טופס הוספת שורה */}
      <div className="topbar" style={{ marginTop: 8, flexWrap: "wrap", gap: 8, alignItems: "end" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(6, minmax(140px, 1fr)) auto", gap: 8, width: "100%" }}>
          <div>
            <label style={{ display: "block", fontSize: 12, opacity: 0.8, marginBottom: 4 }}>סימבול</label>
            <input className="search" style={{ width: "100%" }} placeholder="AAPL"
                   value={addForm.symbol}
                   onChange={(e) => setAddForm((f) => ({ ...f, symbol: e.target.value }))} />
          </div>

          <div>
            <label style={{ display: "block", fontSize: 12, opacity: 0.8, marginBottom: 4 }}>סוג איתות</label>
            <select className="search" style={{ width: "100%" }}
                    value={addForm.signal_type}
                    onChange={(e) => setAddForm((f) => ({ ...f, signal_type: e.target.value }))}>
              <option value="">—</option>
              <option value="BUY">BUY</option>
              <option value="SELL">SELL</option>
            </select>
          </div>

          <DateTimeField
            label="כניסה"
            value={addForm.entry_time}
            onChange={(v) => setAddForm((f) => ({ ...f, entry_time: v }))}
            className="search"
          />

          <div>
            <label style={{ display: "block", fontSize: 12, opacity: 0.8, marginBottom: 4 }}>מחיר כניסה</label>
            <input className="search" type="number" step="0.01" style={{ width: "100%" }}
                   placeholder="150.25"
                   value={addForm.entry_price}
                   onChange={(e) => setAddForm((f) => ({ ...f, entry_price: e.target.value }))} />
          </div>

          <DateTimeField
            label="יציאה"
            value={addForm.exit_time}
            onChange={(v) => setAddForm((f) => ({ ...f, exit_time: v }))}
            className="search"
          />

          <div>
            <label style={{ display: "block", fontSize: 12, opacity: 0.8, marginBottom: 4 }}>מחיר יציאה</label>
            <input className="search" type="number" step="0.01" style={{ width: "100%" }}
                   placeholder="180.00"
                   value={addForm.exit_price}
                   onChange={(e) => setAddForm((f) => ({ ...f, exit_price: e.target.value }))} />
          </div>

          <div style={{ display: "grid", gap: 6 }}>
            <button className="btn-outline" disabled={adding || !addForm.symbol} onClick={addRow}>
              {adding ? "מוסיף…" : "הוסף שורה"}
            </button>
            <small style={{ color: "var(--txt-dim)" }}>
              שינוי מחושב: {addChangePct == null ? "—" : `${addChangePct >= 0 ? "+" : ""}${addChangePct.toFixed(2)}%`}
              {addFactor != null ? `  (×${addFactor.toFixed(2)})` : ""}
            </small>
          </div>
        </div>
      </div>

      {err ? <div className="alert" style={{ margin: "12px auto" }}>{err}</div> : null}

      <div className="table-wrap">
        <table className="users">
          <thead>
            <tr>
              {columns.map((key) => (
                <th key={key} onClick={() => toggleSort(key)}>
                  {LABELS[key] || key}{sorterIndicator(key)}
                </th>
              ))}
              <th>פעולות</th>
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td colSpan={columns.length + 1} className="muted">אין נתונים</td>
              </tr>
            ) : (
              sorted.map((r) => {
                const isEditing = editRowId === r.id;
                return (
                  <tr key={r.id}>
                    {columns.map((key) => {
                      const val = isEditing ? editDraft?.[key] : r?.[key];

                      if (["entry_time", "exit_time", "created_at", "updated_at"].includes(key)) {
                        return (
                          <td key={key}>
                            {isEditing && (key === "entry_time" || key === "exit_time") ? (
                              <DateTimeInlineCell
                                value={toDatetimeLocalValue(val)}
                                onChange={(v) => changeDraft(key, v)}
                              />
                            ) : (
                              formatDateTime(val)
                            )}
                          </td>
                        );
                      }

                      if (["entry_price", "exit_price", "change_pct"].includes(key)) {
                        const isPct = key === "change_pct";
                        return (
                          <td key={key}>
                            {isEditing && !isPct ? (
                              <input
                                type="number"
                                step="0.01"
                                className="cell-input"
                                value={val ?? ""}
                                onChange={(e) => changeDraft(key, e.target.value)}
                              />
                            ) : isPct ? (
                              val == null ? "" : `${Number(val) >= 0 ? "+" : ""}${Number(val).toFixed(2)}%`
                            ) : (
                              val == null ? "" : String(val)
                            )}
                          </td>
                        );
                      }

                      return (
                        <td key={key}>
                          {isEditing ? (
                            IMMUTABLE.has(key) ? (
                              <span>{String(val ?? "")}</span>
                            ) : (
                              <input
                                className="cell-input"
                                value={val ?? ""}
                                onChange={(e) => changeDraft(key, e.target.value)}
                              />
                            )
                          ) : (
                            String(val ?? "")
                          )}
                        </td>
                      );
                    })}
                    <td className="actions">
                      {isEditing ? (
                        <>
                          <button className="btn-primary sm" onClick={saveEdit}>שמור</button>
                          <button className="btn-secondary sm" onClick={cancelEdit}>בטל</button>
                        </>
                      ) : (
                        <>
                          <button className="btn-primary sm" onClick={() => beginEdit(r)}>ערוך</button>
                          <button className="btn-danger sm" onClick={() => delRow(r.id)}>מחק</button>
                        </>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
