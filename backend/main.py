# backend/main.py
from dotenv import load_dotenv
load_dotenv()

import os
import asyncio
import datetime as dt
from typing import Optional, Set, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# הראוטר/אימות הקיימים אצלך
from auth import router as auth_router, verify_jwt

# ------------------------
# חיבור ל-DataLog (SQLite)
# ------------------------
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATA_LOG_URL = os.getenv("DATA_LOG_URL", "sqlite:///./DataLog.db")

DataLogEngine = create_engine(
    DATA_LOG_URL,
    connect_args={"check_same_thread": False} if DATA_LOG_URL.startswith("sqlite") else {},
)
DataLogSession = sessionmaker(bind=DataLogEngine, autoflush=False, autocommit=False)

# --- סכמת positions החדשה + מיגרציה רכה (SQLite) ---
def _ensure_positions_schema():
    with DataLogEngine.begin() as conn:
        # צור טבלה אם לא קיימת
        conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS positions (
              id INTEGER PRIMARY KEY,
              symbol TEXT NOT NULL,
              signal_type TEXT,
              entry_date TEXT NOT NULL,
              entry_price REAL,
              exit_date TEXT,
              exit_price REAL,
              change_pct REAL
            );
            """
        )
        # הוספת עמודות חסרות אם עולה מצורך (מיגרציה סלחנית)
        rows = conn.exec_driver_sql("PRAGMA table_info(positions);").fetchall()
        cols = {r[1] for r in rows}
        wanted = {
            "symbol": "TEXT",
            "signal_type": "TEXT",
            "entry_date": "TEXT",
            "entry_price": "REAL",
            "exit_date": "TEXT",
            "exit_price": "REAL",
            "change_pct": "REAL",
        }
        for name, coltype in wanted.items():
            if name not in cols:
                conn.exec_driver_sql(f"ALTER TABLE positions ADD COLUMN {name} {coltype};")

_ensure_positions_schema()


class PositionOut(BaseModel):
    symbol: str
    signal_type: Optional[str] = None
    entry_date: dt.datetime
    entry_price: Optional[float] = None
    exit_date: Optional[dt.datetime] = None
    exit_price: Optional[float] = None
    change_pct: Optional[float] = None


# -----------
# FastAPI app
# -----------
app = FastAPI(title="Algo Trade – Web API")

# CORS — לצמצם בדומיינים שלך בפרודקשן
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# כולל את הראוטים של auth.py
app.include_router(auth_router)


# -----------------
# Endpoints כלליים
# -----------------
@app.get("/api/health")
async def health():
    return {"ok": True}


# --------------------------------------------
# Positions API — לפי הסכמה החדשה שביקשת
# --------------------------------------------

SELECT_COLS = """
symbol, signal_type, entry_date, entry_price, exit_date, exit_price, change_pct
"""

def _parse_dt(s: Optional[str]) -> Optional[dt.datetime]:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s)
    except Exception:
        try:
            return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

@app.get("/api/positions/recent", response_model=List[PositionOut])
async def recent_positions(
    limit: int = Query(10, ge=1, le=1000),
    order: str = Query("desc", pattern="^(?i)(asc|desc)$")
):
    """
    מחזיר פוזיציות אחרונות לפי entry_date (ברירת מחדל: יורד).
    """
    order_sql = "ASC" if str(order).lower() == "asc" else "DESC"
    sql = text(
        f"""
        SELECT {SELECT_COLS}
        FROM positions
        ORDER BY datetime(entry_date) {order_sql}
        LIMIT :limit
        """
    )
    with DataLogSession() as s:
        rows = s.execute(sql, {"limit": int(limit)}).all()
        out: List[PositionOut] = []
        for (symbol, signal_type, entry_date, entry_price, exit_date, exit_price, change_pct) in rows:
            out.append(PositionOut(
                symbol=symbol,
                signal_type=signal_type,
                entry_date=_parse_dt(entry_date) or dt.datetime.utcnow(),
                entry_price=entry_price,
                exit_date=_parse_dt(exit_date),
                exit_price=exit_price,
                change_pct=change_pct,
            ))
        return out


@app.get("/api/positions/by-range", response_model=List[PositionOut])
async def positions_by_range(start: str, end: Optional[str] = None):
    """
    מחזיר רשומות בין start ל-end לפי entry_date, מסודרות עולה.
    start/end בפורמט ISO, למשל: 2025-09-01T00:00:00
    """
    try:
        start_dt = dt.datetime.fromisoformat(start)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid 'start' datetime; expected ISO like 2025-09-01T00:00:00")

    if end:
        try:
            end_dt = dt.datetime.fromisoformat(end)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid 'end' datetime; expected ISO like 2025-09-10T23:59:59")
    else:
        end_dt = dt.datetime.utcnow()

    sql = text(
        f"""
        SELECT {SELECT_COLS}
        FROM positions
        WHERE datetime(entry_date) >= datetime(:start_dt)
          AND datetime(entry_date) <= datetime(:end_dt)
        ORDER BY datetime(entry_date) ASC
        """
    )
    with DataLogSession() as s:
        rows = s.execute(sql, {"start_dt": start_dt.isoformat(timespec="seconds"),
                               "end_dt": end_dt.isoformat(timespec="seconds")}).all()
        out: List[PositionOut] = []
        for (symbol, signal_type, entry_date, entry_price, exit_date, exit_price, change_pct) in rows:
            out.append(PositionOut(
                symbol=symbol,
                signal_type=signal_type,
                entry_date=_parse_dt(entry_date) or dt.datetime.utcnow(),
                entry_price=entry_price,
                exit_date=_parse_dt(exit_date),
                exit_price=exit_price,
                change_pct=change_pct,
            ))
        return out


# -------------------------
# WebSocket מאובטח עם JWT
# -------------------------
_clients: Set[WebSocket] = set()

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket, token: Optional[str] = Query(default=None)):
    # אימות JWT מהפרונט
    if not token or not verify_jwt(token):
        await ws.close(code=4401)  # Unauthorized
        return

    await ws.accept()
    _clients.add(ws)
    try:
        while True:
            try:
                # ממתין להודעת לקוח עד 60 שניות
                await asyncio.wait_for(ws.receive_text(), timeout=60)
            except asyncio.TimeoutError:
                # keep-alive
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
