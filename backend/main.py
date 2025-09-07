# backend/main.py
import os
import sys
import time
import json
import asyncio
from typing import Set, Dict, Any, Optional, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware

from ai import ask_with_sources
from telegram_listener import TelegramListener, TelegramMessenger
# שים לב: לא מייבאים כאן Base/engine/SessionLocal מתוך auth
from auth import router as auth_router, verify_jwt

from sqlalchemy import (
    Column, Integer, DateTime, Text, func, select, desc,
    inspect, text as sql_text, create_engine
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# === ENV ===
PROMPT = os.getenv("PROMPT", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
SOURCE_CHANNEL_ID = int(os.getenv("SOURCE_CHANNEL_ID", "0"))
TARGET_GROUP_ID = int(os.getenv("TARGET_GROUP_ID", "0"))
HISTORY_LIMIT = int(os.getenv("WS_HISTORY_LIMIT", "100"))

# === DataLog DB (נפרד מה-Users) ===
DB_URL_DATA = os.getenv("DB_URL_DATA", "sqlite:///./DataLog.db")
_data_connect_args = {"check_same_thread": False} if DB_URL_DATA.startswith("sqlite") else {}
DataEngine = create_engine(DB_URL_DATA, connect_args=_data_connect_args)
DataSessionLocal = sessionmaker(bind=DataEngine, autoflush=False, autocommit=False)
DataBase = declarative_base()

# === FastAPI + CORS ===
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # לשנות בפרודקשן
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)

# === ChatHistory table (persist last messages) ===
class ChatHistory(DataBase):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    item_id = Column(Integer, nullable=False)        # ה-id שאתה משדר ללקוח
    asked = Column(Text, nullable=False)
    sources_json = Column(Text, nullable=False)      # JSON של רשימת קישורים
    timestamp_str = Column(Text, nullable=False)     # הטקסט של החותמת זמן
    answer = Column(Text, nullable=False)
    matrix_text = Column(Text, nullable=True)        # מטריצה (אם קיימת)

# יצירת הטבלאות אם לא קיימות + מיגרציה עדינה לעמודה חדשה
DataBase.metadata.create_all(bind=DataEngine)

def _ensure_chat_history_matrix_column():
    try:
        insp = inspect(DataEngine)
        cols = [c["name"] for c in insp.get_columns("chat_history")]
        if "matrix_text" not in cols:
            with DataEngine.begin() as conn:
                conn.execute(sql_text("ALTER TABLE chat_history ADD COLUMN matrix_text TEXT"))
            print("[DB] Added matrix_text column to chat_history")
    except Exception as e:
        print(f"[DB] migration check failed: {type(e).__name__}: {e}", file=sys.stderr)

_ensure_chat_history_matrix_column()

def _persist_message(msg: Dict[str, Any]):
    """שומר הודעה ב-DB ומגביל ל-HISTORY_LIMIT אחרונות."""
    db: Session = DataSessionLocal()
    try:
        sources = msg.get("sources") or []
        row = ChatHistory(
            item_id=int(msg.get("id")),
            asked=str(msg.get("asked") or ""),
            sources_json=json.dumps(sources, ensure_ascii=False),
            timestamp_str=str(msg.get("timestamp") or ""),
            answer=str(msg.get("answer") or ""),
            matrix_text=str(msg.get("matrix") or "") or None,
        )
        db.add(row)
        db.commit()

        # השארת HISTORY_LIMIT אחרונות
        ids = db.execute(select(ChatHistory.id).order_by(desc(ChatHistory.id)).limit(HISTORY_LIMIT)).scalars().all()
        if ids:
            min_keep = min(ids)
            db.query(ChatHistory).filter(ChatHistory.id < min_keep).delete(synchronize_session=False)
            db.commit()
    except Exception as e:
        print(f"[DB] persist error: {type(e).__name__}: {e}", file=sys.stderr)
        db.rollback()
    finally:
        db.close()

def _load_recent_messages(limit: int = HISTORY_LIMIT) -> List[Dict[str, Any]]:
    """טוען עד limit הודעות אחרונות ומחזירן בפורמט זהה לזה שנשלח ל-Frontend."""
    db: Session = DataSessionLocal()
    try:
        rows: List[ChatHistory] = (
            db.execute(select(ChatHistory).order_by(desc(ChatHistory.id)).limit(limit))
              .scalars()
              .all()
        )
        rows = list(reversed(rows))  # מהישן לחדש
        out: List[Dict[str, Any]] = []
        for r in rows:
            try:
                sources = json.loads(r.sources_json)
            except Exception:
                sources = []
            out.append({
                "id": r.item_id,
                "asked": r.asked,
                "sources": sources,
                "timestamp": r.timestamp_str,
                "answer": r.answer,
                "matrix": r.matrix_text or "",
            })
        return out
    except Exception as e:
        print(f"[DB] load history error: {type(e).__name__}: {e}", file=sys.stderr)
        return []
    finally:
        db.close()

# === WebSocket Hub ===
from starlette.websockets import WebSocket
_clients: Set[WebSocket] = set()
_MSG_ID = 0

def _next_id() -> int:
    global _MSG_ID
    _MSG_ID += 1
    return _MSG_ID

async def broadcast(message: Dict[str, Any]):
    to_drop = []
    for ws in list(_clients):
        try:
            await ws.send_json(message)
        except Exception:
            to_drop.append(ws)
    for ws in to_drop:
        _clients.discard(ws)

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket, token: Optional[str] = Query(default=None)):
    if not token:
        print("[WS] missing token", file=sys.stderr)
        await ws.close(code=4401)
        return

    sub = verify_jwt(token)
    if not sub:
        print("[WS] token rejected (expired or invalid)", file=sys.stderr)
        await ws.close(code=4401)
        return

    await ws.accept()
    _clients.add(ws)
    try:
        # שליחת היסטוריה ללקוח חדש
        history = await asyncio.to_thread(_load_recent_messages, HISTORY_LIMIT)
        for old_msg in history:
            try:
                await ws.send_json(old_msg)
            except Exception:
                break

        while True:
            await ws.receive_text()  # אין קלט מהקליינט
    except WebSocketDisconnect:
        _clients.discard(ws)

@app.get("/api/health")
async def health():
    return {"ok": True}

# === שליח לטלגרם (קבוצה) ===
messenger: Optional[TelegramMessenger] = None

# === הצינור: URLs -> AI -> Frontend + Telegram group ===
async def process_urls(urls: List[str], question_text: str = "", link_text: str = "", matrix_text: str = ""):
    item_id = _next_id()
    ts = time.strftime("%Y-%m-%d %H:%M:%S")

    if not urls:
        err = "No URLs provided from Telegram message."
        print(f"[backend] {ts} - {err}", file=sys.stderr)
        msg = {
            "id": item_id,
            "asked": question_text,
            "sources": [],
            "timestamp": ts,
            "answer": err,
            "matrix": matrix_text or "",
        }
        await broadcast(msg)
        await asyncio.to_thread(_persist_message, msg)
        if messenger:
            try:
                parts = ["שגיאה בעיבוד הודעה מהטלגרם:", err]
                if matrix_text:
                    parts += ["", "מטריצה:", matrix_text]
                await messenger.send_text_with_button("\n".join(parts))
            except Exception as e2:
                print(f"[TG] שגיאה בשליחה לקבוצה: {e2}", file=sys.stderr)
        return

    try:
        print(f"[backend] {ts} - שולח ל-GPT עם {len(urls)} קישורים…")
        # ai.ask_with_sources טוענת את PROMPT/QUESTION מה-env; question_text לא כולל מטריצה
        answer = await asyncio.to_thread(ask_with_sources, PROMPT, question_text, urls)
        print(f"[backend] {ts} - קיבלתי תשובה מ-GPT")
    except Exception as e:
        answer = f"AI processing failed: {e}"
        print(f"[backend] {ts} - {answer}", file=sys.stderr)

    msg = {
        "id": item_id,
        "asked": question_text,
        "sources": urls,
        "timestamp": ts,
        "answer": answer,
        "matrix": matrix_text or "",
    }
    await broadcast(msg)
    await asyncio.to_thread(_persist_message, msg)
    print(f"[backend] {ts} - בוצע ✓")
    
    if messenger:
        try:
            print("[backend] שולח תשובה גם לטלגרם…")
            msg_parts = [
                "כותרת ההודעה:",
                (question_text or "(ללא כותרת)").strip(),
                "",
                "קישור שצורף:",
                (link_text or "(אין קישור)").strip(),
                "",
                "תשובה מ-AI:",
                str(answer)
            ]
            if matrix_text:
                msg_parts += ["", "מטריצה:", matrix_text.strip()]
            full_text = "\n".join(msg_parts)
            await messenger.send_text_with_button(full_text)
        except Exception as e:
            print(f"[TG] שגיאה בשליחה לקבוצה: {e}", file=sys.stderr)

# === Startup ===
@app.on_event("startup")
async def on_startup():
    loop = asyncio.get_running_loop()
    try:
        global messenger
        if BOT_TOKEN and TARGET_GROUP_ID:
            messenger = TelegramMessenger(BOT_TOKEN, TARGET_GROUP_ID)
            print(f"[TG] TelegramMessenger ready for group {TARGET_GROUP_ID}")
        else:
            print("[TG] TelegramMessenger לא הופעל (BOT_TOKEN/TARGET_GROUP_ID חסרים)")

        if not BOT_TOKEN:
            print("[TG] לא הוגדר BOT_TOKEN ב-.env — המאזין לא יופעל.", file=sys.stderr)
            return
        if not SOURCE_CHANNEL_ID:
            print("[TG] לא הוגדר SOURCE_CHANNEL_ID ב-.env — המאזין לא יופעל.", file=sys.stderr)
            return

        listener = TelegramListener(
            BOT_TOKEN,
            SOURCE_CHANNEL_ID,
            on_urls=process_urls
        )
        listener.start(loop)

    except Exception as e:
        print(f"[TG] Could not start Telegram listener: {e}", file=sys.stderr)
