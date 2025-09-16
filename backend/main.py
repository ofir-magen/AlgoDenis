from dotenv import load_dotenv
load_dotenv()  # load .env before imports that read os.getenv

import os
import asyncio
import datetime as dt
from typing import Optional, Set, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# auth router + jwt verifier (existing)
from auth import router as auth_router, verify_jwt

# === DataLog (SQLite) setup ===
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATA_LOG_URL = os.getenv("DATA_LOG_URL", "sqlite:///./DataLog.db")
DataLogEngine = create_engine(
    DATA_LOG_URL,
    connect_args={"check_same_thread": False} if DATA_LOG_URL.startswith("sqlite") else {},
)
DataLogSession = sessionmaker(bind=DataLogEngine, autoflush=False, autocommit=False)

# Optional: create a simple demo table if not exists.
# Replace/remove according to your real DataLog schema.
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

# === FastAPI app ===
app = FastAPI(title="Algo Trade – Web API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten to your domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# include existing auth endpoints
app.include_router(auth_router)

@app.get("/api/health")
async def health():
    return {"ok": True}

# -------- Recent positions API (reads from DataLog) --------
@app.get("/api/positions/recent", response_model=List[PositionOut])
async def recent_positions(limit: int = Query(10, ge=1, le=1000),
                           order: str = Query("desc", pattern="^(?i)(asc|desc)$")):
    """
    Returns recent positions. Control size with `limit` and sorting with `order=asc|desc`.
    You can freely change the SQL below to match your real schema/filters.
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
            # normalize trade_date to datetime
            if isinstance(trade_date, str):
                try:
                    trade_date = dt.datetime.fromisoformat(trade_date)
                except Exception:
                    try:
                        trade_date = dt.datetime.strptime(trade_date, "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        trade_date = dt.datetime.utcnow()
            out.append(PositionOut(
                symbol=symbol,
                trade_date=trade_date,
                price=price,
                change_pct=change_pct,
                volume=volume,
                direction=direction,
            ))
        return out

# -------- WebSocket (keeps your original JWT-gated echo/heartbeat) --------
_clients: Set[WebSocket] = set()

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket, token: Optional[str] = Query(default=None)):
    # verify JWT from frontend
    if not token or not verify_jwt(token):
        await ws.close(code=4401)  # Unauthorized
        return

    await ws.accept()
    _clients.add(ws)
    try:
        while True:
            try:
                # wait for client message up to 60 seconds
                await asyncio.wait_for(ws.receive_text(), timeout=60)
            except asyncio.TimeoutError:
                # send keep-alive ping
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
