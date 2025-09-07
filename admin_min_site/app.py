import os
import time
import random
import datetime as dt
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
import secrets

from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, select, Column, Integer, String, DateTime, inspect, text as sql_text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError

from dotenv import load_dotenv
load_dotenv()  # קורא .env מקומי

# ========= ENV =========
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "change-me")
USERS_DB_PATH = os.getenv("USERS_DB_PATH", "./app.db")  # קובץ DB של האתר הראשי
CORS_ORIGINS = (os.getenv("CORS_ORIGINS") or "*").split(",")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8010"))
BUSY_RETRIES = int(os.getenv("BUSY_RETRIES", "7"))
BUSY_BASE_DELAY = float(os.getenv("BUSY_BASE_DELAY", "0.12"))

# ========= DB URL (תומך ברווחים) =========
db_abs = os.path.abspath(USERS_DB_PATH.strip().strip('"').strip("'"))
SQLALCHEMY_URL = URL.create(
    drivername="sqlite+pysqlite",
    database=db_abs,  # SQLAlchemy יטפל בקידוד רווחים
)

engine = create_engine(
    SQLALCHEMY_URL,
    connect_args={"check_same_thread": False, "timeout": 10.0},
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

# ========= Model תואם לטבלת users הקיימת =========
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(320), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    first_name = Column(String(120), nullable=True)
    last_name = Column(String(120), nullable=True)
    phone = Column(String(32), nullable=True)
    telegram_username = Column(String(64), nullable=True)
    active_until = Column(DateTime, nullable=True)
    approved = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)

def _init_db():
    # הודעה קריאה אם הקובץ לא קיים
    if not os.path.exists(db_abs):
        print(f"[DB] WARNING: database file not found: {db_abs}")
    # פרגמות לקונקרנציה
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
            conn.exec_driver_sql("PRAGMA synchronous=NORMAL;")
            conn.exec_driver_sql("PRAGMA busy_timeout=5000;")
    except Exception as e:
        print(f"[DB] PRAGMAs failed: {e}")

    # הוספת עמודות חסרות (מיגרציה עדינה)
    try:
        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("users")}
        to_add = []
        if "first_name" not in cols:          to_add.append("ADD COLUMN first_name TEXT")
        if "last_name" not in cols:           to_add.append("ADD COLUMN last_name TEXT")
        if "phone" not in cols:               to_add.append("ADD COLUMN phone TEXT")
        if "telegram_username" not in cols:   to_add.append("ADD COLUMN telegram_username TEXT")
        if "active_until" not in cols:        to_add.append("ADD COLUMN active_until DATETIME")
        if "approved" not in cols:            to_add.append("ADD COLUMN approved INTEGER NOT NULL DEFAULT 0")
        if "created_at" not in cols:          to_add.append("ADD COLUMN created_at DATETIME")
        if "updated_at" not in cols:          to_add.append("ADD COLUMN updated_at DATETIME")
        if to_add:
            with engine.begin() as conn:
                for stmt in to_add:
                    conn.execute(sql_text(f"ALTER TABLE users {stmt}"))
            print("[DB] users altered:", ", ".join([s.split()[2] for s in to_add]))
    except Exception as e:
        print(f"[DB] migration failed: {e}")

_init_db()

# ========= Schemas =========
class UserOut(BaseModel):
    id: int
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    telegram_username: Optional[str] = None
    active_until: Optional[dt.datetime] = None
    approved: bool = False
    created_at: Optional[dt.datetime] = None
    updated_at: Optional[dt.datetime] = None
    class Config:
        from_attributes = True

class UsersList(BaseModel):
    total: int
    items: List[UserOut]

class UserUpdateIn(BaseModel):
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    telegram_username: Optional[str] = None
    active_until: Optional[dt.datetime] = None
    approved: Optional[bool] = None

# ========= App & Auth =========
app = FastAPI(title="Minimal Users Admin", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

basic = HTTPBasic()

def require_basic(credentials: HTTPBasicCredentials = Depends(basic)):
    u_ok = secrets.compare_digest(credentials.username, ADMIN_USER)
    p_ok = secrets.compare_digest(credentials.password, ADMIN_PASS)
    if not (u_ok and p_ok):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

def get_db():
    db = SessionLocal()
    try:
        db.execute(sql_text("PRAGMA busy_timeout=5000"))
        yield db
    finally:
        db.close()

def with_retry(fn):
    for i in range(BUSY_RETRIES):
        try:
            return fn()
        except OperationalError as e:
            msg = str(e).lower()
            if "database is locked" in msg or "database is busy" in msg:
                time.sleep((0.1 + BUSY_BASE_DELAY) * (2 ** i) + random.random()*0.05)
                continue
            raise
    raise HTTPException(status_code=503, detail="Database is busy")

# ========= API =========
@app.get("/api/health", dependencies=[Depends(require_basic)])
def health():
    return {"ok": True, "db": db_abs}

@app.get("/api/users", response_model=UsersList, dependencies=[Depends(require_basic)])
def get_all_users(db: Session = Depends(get_db)):
    def _run():
        rows = db.execute(select(User).order_by(User.id.asc())).scalars().all()
        items = [UserOut(
            id=r.id, email=r.email,
            first_name=r.first_name, last_name=r.last_name,
            phone=r.phone, telegram_username=r.telegram_username,
            active_until=r.active_until, approved=bool(r.approved or 0),
            created_at=r.created_at, updated_at=r.updated_at
        ) for r in rows]
        return UsersList(total=len(items), items=items)
    return with_retry(_run)

@app.patch("/api/users/{user_id}", response_model=UserOut, dependencies=[Depends(require_basic)])
def update_user(user_id: int, body: UserUpdateIn, db: Session = Depends(get_db)):
    now = dt.datetime.utcnow()
    def _run():
        u = db.get(User, user_id)
        if not u:
            raise HTTPException(status_code=404, detail="Not found")

        if body.email is not None:               u.email = body.email.lower()
        if body.first_name is not None:          u.first_name = body.first_name
        if body.last_name is not None:           u.last_name = body.last_name
        if body.phone is not None:               u.phone = body.phone
        if body.telegram_username is not None:   u.telegram_username = body.telegram_username
        if body.active_until is not None:        u.active_until = body.active_until
        if body.approved is not None:            u.approved = 1 if body.approved else 0

        u.updated_at = now
        db.add(u)
        db.commit()
        db.refresh(u)
        return UserOut(
            id=u.id, email=u.email, first_name=u.first_name, last_name=u.last_name,
            phone=u.phone, telegram_username=u.telegram_username, active_until=u.active_until,
            approved=bool(u.approved or 0), created_at=u.created_at, updated_at=u.updated_at
        )
    return with_retry(_run)

# ========= Static Frontend =========
# מגיש את public/ כאתר: /  => index.html, ו-/api ל-API
app.mount("/", StaticFiles(directory="public", html=True), name="static")
