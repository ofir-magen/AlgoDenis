# backend/main.py
from dotenv import load_dotenv
load_dotenv()  # ← חשוב! טוען .env לפני ייבוא מודולים שקוראים os.getenv בזמן import

import asyncio
from typing import Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware

# ראוטים של הרשמה/התחברות/מחיר
from auth import router as auth_router, verify_jwt

app = FastAPI(title="Algo Trade – Web API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # בפרודקשן – לצמצם לדומיין(ים) שלך
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

@app.get("/api/health")
async def health():
    return {"ok": True}

# -------- WebSocket (ללא DataLog, עם heartbeat עדין) --------
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
                # מחכים להודעה מהלקוח עד 60 שניות
                await asyncio.wait_for(ws.receive_text(), timeout=60)
            except asyncio.TimeoutError:
                # אין תעבורה – שולחים ping קטן כדי להשאיר חיבור חי
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
