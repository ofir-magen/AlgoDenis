from dotenv import load_dotenv
load_dotenv()

import os
import asyncio
import datetime as dt
from typing import Optional, Set, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# אימות קיים
from auth import router as auth_router, verify_jwt

# SQLAlchemy
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool  # <<< חשוב ל-SQLite

# ---------- DB ----------
# ניתן לקנפג ב-.env: DATA_LOG_URL=sqlite:///./DataLog.db
DATA_LOG_URL = os.getenv("DATA_LOG_URL", "sqlite:///./DataLog.db")

Engine = create_engine(
    DATA_LOG_URL,
    poolclass=NullPool if DATA_LOG_URL.startswith("sqlite") else None,  # <<< בלי pooling ב-SQLite
    connect_args={"check_same_thread": False} if DATA_LOG_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=Engine, autoflush=False, autocommit=False)

# נוודא שקיימת טבלת datalog בסכימה החדשה
with Engine.begin() as conn:
    conn.exec_driver_sql("""
    CREATE TABLE IF NOT EXISTS datalog (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      symbol TEXT NOT NULL,
      signal_type TEXT,
      entry_time   TEXT,
      entry_price  REAL,
      exit_time    TEXT,
      exit_price   REAL,
      change_pct   REAL,
      assigned     TEXT,
      created_at   TEXT DEFAULT (datetime('now')),
      updated_at   TEXT DEFAULT (datetime('now'))
    );
    """)
    # אם יש רק הטבלה הישנה 'positions' ואין כלום ב-datalog, לא נוגעים – ה-API יידע לקרוא ממנה.

def _has_table(name: str) -> bool:
    with Engine.begin() as conn:
        if DATA_LOG_URL.startswith("sqlite"):
            r = conn.exec_driver_sql(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n",
                {"n": name}
            ).fetchone()
            return bool(r)
        # DB אחרים – ניסיון select ראשון
        try:
            conn.exec_driver_sql(f"SELECT 1 FROM {name} LIMIT 1")
            return True
        except Exception:
            return False

# ---------- מודלים ל-API (השדות החדשים) ----------
class PositionOut(BaseModel):
    symbol: str
    signal_type: Optional[str] = None
    entry_time: Optional[dt.datetime] = None
    entry_price: Optional[float] = None
    exit_time: Optional[dt.datetime] = None
    exit_price: Optional[float] = None
    change_pct: Optional[float] = None  # יחושב אם חסר

# ---------- FastAPI ----------
app = FastAPI(title="Algo Trade – Web API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # לצמצם בפרודקשן
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

@app.get("/api/health")
async def health():
    return {"ok": True}

# ---------- Helpers ----------
def _parse_dt(value: str) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except Exception:
        try:
            return dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

def _calc_change_pct(entry_price, exit_price) -> Optional[float]:
    try:
        a = float(entry_price); b = float(exit_price)
        if a == 0: return None
        return ((b - a) / a) * 100.0
    except Exception:
        return None

# ---------- קריאה לנתונים (תאימות: datalog קודם, אחרת positions ישן) ----------
def _fetch_recent(limit: int, order_desc: bool) -> List[PositionOut]:
    with SessionLocal() as s:
        # קודם מנסים מהטבלה החדשה
        if _has_table("datalog"):
            order = "DESC" if order_desc else "ASC"
            rows = s.execute(text(f"""
                SELECT symbol, signal_type, entry_time, entry_price, exit_time, exit_price, change_pct
                FROM datalog
                ORDER BY COALESCE(entry_time, created_at) {order}
                LIMIT :limit
            """), {"limit": int(limit)}).all()
            out = []
            for r in rows:
                (symbol, signal_type, entry_time, entry_price, exit_time, exit_price, change_pct) = r
                et = _parse_dt(entry_time) if isinstance(entry_time, str) else entry_time
                xt = _parse_dt(exit_time) if isinstance(exit_time, str) else exit_time
                if change_pct is None and entry_price is not None and exit_price is not None:
                    change_pct = _calc_change_pct(entry_price, exit_price)
                out.append(PositionOut(
                    symbol=symbol,
                    signal_type=signal_type,
                    entry_time=et,
                    entry_price=entry_price,
                    exit_time=xt,
                    exit_price=exit_price,
                    change_pct=change_pct
                ))
            return out

        # נפילה אחורה: טבלה ישנה 'positions' (symbol, trade_date, price, change_pct, volume, direction)
        if _has_table("positions"):
            order = "DESC" if order_desc else "ASC"
            rows = s.execute(text(f"""
                SELECT symbol, trade_date, price, change_pct, direction
                FROM positions
                ORDER BY trade_date {order}
                LIMIT :limit
            """), {"limit": int(limit)}).all()
            out = []
            for (symbol, trade_date, price, change_pct, direction) in rows:
                t = _parse_dt(trade_date) if isinstance(trade_date, str) else trade_date
                # מיפוי לשדות החדשים:
                signal_type = (str(direction).upper() if direction else None)
                out.append(PositionOut(
                    symbol=symbol,
                    signal_type=signal_type,  # BUY/SELL/UP/DOWN וכו'
                    entry_time=t,
                    entry_price=price,
                    exit_time=None,
                    exit_price=None,
                    change_pct=change_pct
                ))
            return out

        return []  # אין טבלאות

def _fetch_by_range(start: str, end: Optional[str]) -> List[PositionOut]:
    try:
        start_dt = dt.datetime.fromisoformat(start)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid 'start' (ISO)")

    end_dt = dt.datetime.fromisoformat(end) if end else dt.datetime.utcnow()

    with SessionLocal() as s:
        if _has_table("datalog"):
            rows = s.execute(text("""
                SELECT symbol, signal_type, entry_time, entry_price, exit_time, exit_price, change_pct
                FROM datalog
                WHERE COALESCE(entry_time, created_at) >= :start_dt
                  AND COALESCE(entry_time, created_at) <= :end_dt
                ORDER BY COALESCE(entry_time, created_at) ASC
            """), {"start_dt": start_dt, "end_dt": end_dt}).all()
            out = []
            for r in rows:
                (symbol, signal_type, entry_time, entry_price, exit_time, exit_price, change_pct) = r
                et = _parse_dt(entry_time) if isinstance(entry_time, str) else entry_time
                xt = _parse_dt(exit_time) if isinstance(exit_time, str) else exit_time
                if change_pct is None and entry_price is not None and exit_price is not None:
                    change_pct = _calc_change_pct(entry_price, exit_price)
                out.append(PositionOut(
                    symbol=symbol, signal_type=signal_type,
                    entry_time=et, entry_price=entry_price,
                    exit_time=xt, exit_price=exit_price,
                    change_pct=change_pct
                ))
            return out

        if _has_table("positions"):
            rows = s.execute(text("""
                SELECT symbol, trade_date, price, change_pct, direction
                FROM positions
                WHERE trade_date >= :start_dt AND trade_date <= :end_dt
                ORDER BY trade_date ASC
            """), {"start_dt": start_dt, "end_dt": end_dt}).all()
            out = []
            for (symbol, trade_date, price, change_pct, direction) in rows:
                t = _parse_dt(trade_date) if isinstance(trade_date, str) else trade_date
                out.append(PositionOut(
                    symbol=symbol,
                    signal_type=(str(direction).upper() if direction else None),
                    entry_time=t,
                    entry_price=price,
                    exit_time=None,
                    exit_price=None,
                    change_pct=change_pct
                ))
            return out

        return []

# ---------- Endpoints לצריכת ה-Frontend ----------
@app.get("/api/positions/recent", response_model=List[PositionOut])
async def recent_positions(
    limit: int = Query(10, ge=1, le=1000),
    order: str = Query("desc", pattern="^(?i)(asc|desc)$")
):
    """מוציא פוזיציות אחרונות מהסכימה החדשה (datalog) או הישנה (positions) בתאימות לאחור."""
    return _fetch_recent(limit=limit, order_desc=(str(order).lower() != "asc"))

@app.get("/api/positions/by-range", response_model=List[PositionOut])
async def positions_by_range(start: str, end: Optional[str] = None):
    """טווח תאריכים – מחזיר בסכימה החדשה (או מיפוי מהישנה)."""
    return _fetch_by_range(start, end)

# ---------- WebSocket מאובטח (ללא שינוי) ----------
_clients: Set[WebSocket] = set()

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket, token: Optional[str] = Query(default=None)):
    if not token or not verify_jwt(token):
        await ws.close(code=4401)
        return

    await ws.accept()
    _clients.add(ws)
    try:
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=60)
            except asyncio.TimeoutError:
                try:
                    await ws.send_text('{"type":"ping"}')
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(ws)
        try:
            await ws.close()
        except Exception:
            pass
