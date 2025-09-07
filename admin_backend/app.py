import os
import datetime as dt
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Depends, HTTPException, status, Body, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import create_engine, text as sql_text, Table, MetaData, select, update, delete
from sqlalchemy.orm import Session, sessionmaker
from jose import jwt

# ===== env =====
from dotenv import load_dotenv
load_dotenv()

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8010"))

USERS_DB_PATH = os.getenv("USERS_DB_PATH")  # שביל מוחלט לקובץ ה-SQLite של האתר הראשי
if not USERS_DB_PATH:
    raise RuntimeError("USERS_DB_PATH missing in .env")

if not os.path.isabs(USERS_DB_PATH):
    print(f"[DB] WARNING: USERS_DB_PATH is not absolute: {USERS_DB_PATH}")

DB_URL = f"sqlite:///{USERS_DB_PATH}"

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin")
ADMIN_JWT_SECRET = os.getenv("ADMIN_JWT_SECRET", "CHANGE_ME")
JWT_ALG = "HS256"
JWT_EXPIRE_MIN = int(os.getenv("JWT_EXPIRE_MIN", "720"))

# ===== sqlalchemy (רפלקציה) =====
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
meta = MetaData()

try:
    meta.reflect(bind=engine, only=["users"])
    USERS: Table = meta.tables["users"]
except Exception as e:
    print(f"[DB] migration failed: users ({type(e).__name__}: {e})")
    raise

# ===== fastapi =====
app = FastAPI(title="Admin API (minimal)", version="1.0.0")

# CORS (אפשר לצמצם לכתובת הפרונט של האדמין: http://45.88.104.13:5174)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],  # חשוב ל-Authorization
)

security = HTTPBearer(auto_error=True)

def create_token(sub: str) -> str:
    now = dt.datetime.utcnow()
    payload = {"sub": sub, "iat": now, "exp": now + dt.timedelta(minutes=JWT_EXPIRE_MIN)}
    return jwt.encode(payload, ADMIN_JWT_SECRET, algorithm=JWT_ALG)

def verify_token(creds: HTTPAuthorizationCredentials = Depends(security)) -> str:
    token = creds.credentials
    try:
        data = jwt.decode(token, ADMIN_JWT_SECRET, algorithms=[JWT_ALG])
        return str(data.get("sub") or "")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

def get_db():
    db: Session = SessionLocal()
    try:
        # קצת PRAGMAs ליציבות עם קבצים משותפים
        db.execute(sql_text("PRAGMA journal_mode=WAL"))
        db.execute(sql_text("PRAGMA busy_timeout=5000"))
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# ===== Schemas =====
class LoginIn(BaseModel):
    username: str
    password: str

class UserUpdate(BaseModel):
    # עדכון דינמי: נקבל dict חופשי ונסנן בצד השרת
    data: Dict[str, Any]

# ===== Routes =====
@app.get("/api/health")
def health():
    return {"ok": True}

@app.post("/api/login")
def login(body: LoginIn):
    if body.username != ADMIN_USER or body.password != ADMIN_PASS:
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = create_token(body.username)
    return {"token": token}

@app.get("/api/users")
def list_users(_: str = Depends(verify_token), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = db.execute(select(USERS)).mappings().all()
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d.pop("password_hash", None)  # לא מחזירים האש
        out.append(d)
    return out

@app.put("/api/users/{user_id}")
def update_user(
    user_id: int = Path(..., ge=1),
    body: UserUpdate = Body(...),
    _: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    if not body.data:
        raise HTTPException(status_code=400, detail="No fields to update")

    allowed_cols = set(USERS.c.keys()) - {"id", "password_hash"}
    bad = [k for k in body.data.keys() if k not in allowed_cols]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown/forbidden fields: {bad}")

    stmt = (
        update(USERS)
        .where(USERS.c.id == user_id)
        .values(**body.data)
    )
    res = db.execute(stmt)
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "updated": res.rowcount}

@app.delete("/api/users/{user_id}")
def delete_user(
    user_id: int = Path(..., ge=1),
    _: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    stmt = delete(USERS).where(USERS.c.id == user_id)
    res = db.execute(stmt)
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "deleted": res.rowcount}
