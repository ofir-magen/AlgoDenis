# main.py
from dotenv import load_dotenv
load_dotenv()  # טען .env לפני שימוש ב-os.getenv

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

# ניתן להגדיר ב-.env:
# DATA_LOG_URL=sqlite:///./DataLog.db
DATA_LOG_URL = os.getenv("DATA_LOG_URL", "sqlite:///./DataLog.db")

DataLogEngine = create_engine(
    DATA_LOG_URL,
    connect_args={"check_same_thread": False} if DATA_LOG_URL.startswith("sqlite") else {},
)
DataLogSession = sessionmaker(bind=DataLogEngine, autoflush=False, autocommit=False)

# יצירת טבלת דמו אם לא קיימת (להתאים/להסיר לפי הסכימה האמיתית שלך)
with DataLogEngine.begin() as conn:
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS positions (
          id INTEGER PRIMARY KEY,
          symbol TEXT NOT NULL,
          trade_date TIMESTAMP NOT NULL,
          price REAL,
          change_pct REAL,
          volume INTEGER,
          direction TEXT  -- 'up' | 'down' | 'flat'
        );
        """
    )

class PositionOut(BaseModel):
    symbol: str
    trade_date: dt.datetime
    price: Optional[float] = None
    change_pct: Optional[float] = None
    volume: Optional[int] = None
    direction: Optional[str] = None


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
# Positions API — קריאה מה-DataLog לפי צרכים
# --------------------------------------------

@app.get("/api/positions/recent", response_model=List[PositionOut])
async def recent_positions(
    limit: int = Query(10, ge=1, le=1000),
    order: str = Query("desc", pattern="^(?i)(asc|desc)$")
):
    """
    מחזיר פוזיציות אחרונות מטבלת positions.
    שליטה בגודל הרשימה עם limit ובכיוון מיון עם order=asc|desc.
    """
    order_sql = "ASC" if str(order).lower() == "asc" else "DESC"

    sql = text(
        f"""
        SELECT symbol, trade_date, price, change_pct, volume, direction
        FROM positions
        ORDER BY trade_date {order_sql}
        LIMIT :limit
        """
    )
    with DataLogSession() as s:
        rows = s.execute(sql, {"limit": int(limit)}).all()
        out: List[PositionOut] = []
        for (symbol, trade_date, price, change_pct, volume, direction) in rows:
            if isinstance(trade_date, str):
                trade_date = _parse_dt(trade_date)
            out.append(PositionOut(
                symbol=symbol,
                trade_date=trade_date,
                price=price,
                change_pct=change_pct,
                volume=volume,
                direction=direction,
            ))
        return out


@app.get("/api/positions/by-range", response_model=List[PositionOut])
async def positions_by_range(start: str, end: Optional[str] = None):
    """
    מחזיר רשומות בין start (כולל) ל-end (ברירת מחדל: עכשיו), מסודרות לפי זמן עולה.
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
        """
        SELECT symbol, trade_date, price, change_pct, volume, direction
        FROM positions
        WHERE trade_date >= :start_dt AND trade_date <= :end_dt
        ORDER BY trade_date ASC
        """
    )
    with DataLogSession() as s:
        rows = s.execute(sql, {"start_dt": start_dt, "end_dt": end_dt}).all()
        out: List[PositionOut] = []
        for (symbol, trade_date, price, change_pct, volume, direction) in rows:
            if isinstance(trade_date, str):
                trade_date = _parse_dt(trade_date)
            out.append(PositionOut(
                symbol=symbol,
                trade_date=trade_date,
                price=price,
                change_pct=change_pct,
                volume=volume,
                direction=direction,
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


# --------------
# פונקציות עזר
# --------------
def _parse_dt(value: str) -> dt.datetime:
    """
    המרה סלחנית ממחרוזת datetime לשדה datetime.
    תומך ב-ISO בסיסי ובפורמט 'YYYY-MM-DD HH:MM:SS'.
    """
    try:
        return dt.datetime.fromisoformat(value)
    except Exception:
        try:
            return dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return dt.datetime.utcnow()
