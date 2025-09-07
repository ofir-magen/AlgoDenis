# backend/auth.py
import os
import sys
import datetime as dt
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, constr
from sqlalchemy import Column, Integer, String, DateTime, create_engine, select, func, inspect, text as sql_text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from passlib.context import CryptContext
from jose import jwt, JWTError, ExpiredSignatureError

# === ENV / CONFIG ===
JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_IN_ENV")
JWT_ALG = "HS256"
JWT_EXPIRE_MIN = int(os.getenv("JWT_EXPIRE_MIN", "60"))

# DB של משתמשים (Users)
DB_URL_USERS = os.getenv("DB_URL_USERS", "sqlite:///./Users.db")
_users_connect_args = {"check_same_thread": False} if DB_URL_USERS.startswith("sqlite") else {}
UsersEngine = create_engine(DB_URL_USERS, connect_args=_users_connect_args)
UsersSessionLocal = sessionmaker(bind=UsersEngine, autoflush=False, autocommit=False)
UsersBase = declarative_base()

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# === DB Model ===
class User(UsersBase):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(320), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    active_until = Column(DateTime, nullable=False)
    # שדות נוספים:
    first_name = Column(String(120), nullable=True)
    last_name = Column(String(120), nullable=True)
    phone = Column(String(32), nullable=True)
    telegram_username = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=True)

UsersBase.metadata.create_all(bind=UsersEngine)

def _ensure_extra_columns():
    """מיגרציה עדינה: מוסיף עמודות אם חסרות (SQLite/Postgres/MySQL)."""
    try:
        insp = inspect(UsersEngine)
        cols = {c["name"] for c in insp.get_columns("users")}
        alter = []
        if "first_name" not in cols: alter.append("ADD COLUMN first_name VARCHAR(120)")
        if "last_name" not in cols: alter.append("ADD COLUMN last_name VARCHAR(120)")
        if "phone" not in cols: alter.append("ADD COLUMN phone VARCHAR(32)")
        if "telegram_username" not in cols: alter.append("ADD COLUMN telegram_username VARCHAR(64)")
        if "created_at" not in cols: alter.append("ADD COLUMN created_at DATETIME")
        if alter:
            with UsersEngine.begin() as conn:
                for stmt in alter:
                    conn.execute(sql_text(f"ALTER TABLE users {stmt}"))
            print("[AUTH][DB] users table altered:", ", ".join(s.split()[2] for s in alter))
    except Exception as e:
        print(f"[AUTH][DB] migration check failed: {type(e).__name__}: {e}", file=sys.stderr)

_ensure_extra_columns()

def get_db():
    db = UsersSessionLocal()
    try:
        yield db
    finally:
        db.close()

# === Schemas ===
class RegisterIn(BaseModel):
    first_name: constr(min_length=1, max_length=120)
    last_name: constr(min_length=1, max_length=120)
    email: EmailStr
    email_confirm: EmailStr
    password: constr(min_length=6, max_length=128)
    phone: constr(min_length=5, max_length=32)
    telegram_username: constr(min_length=2, max_length=64)

class LoginIn(BaseModel):
    email: EmailStr
    password: constr(min_length=6, max_length=128)

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

# === Helpers ===
def hash_password(pw: str) -> str:
    return pwd_ctx.hash(pw)

def verify_password(pw: str, hashed: str) -> bool:
    return pwd_ctx.verify(pw, hashed)

def create_jwt(sub: str) -> str:
    now = dt.datetime.utcnow()
    payload = {"sub": sub, "iat": now, "exp": now + dt.timedelta(minutes=JWT_EXPIRE_MIN)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def verify_jwt(token: str) -> Optional[str]:
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        return data.get("sub")
    except ExpiredSignatureError:
        print("[AUTH] token expired", file=sys.stderr); return None
    except JWTError as e:
        print(f"[AUTH] token invalid: {type(e).__name__}", file=sys.stderr); return None

# === Router ===
router = APIRouter(prefix="/api", tags=["auth"])

@router.post("/register", response_model=TokenOut)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    email_confirm = body.email_confirm.lower()
    if email != email_confirm:
        raise HTTPException(status_code=400, detail="Email confirmation does not match")

    exists = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="Email already registered")

    active_until = dt.datetime.utcnow() + dt.timedelta(days=30)
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        active_until=active_until,
        first_name=body.first_name.strip(),
        last_name=body.last_name.strip(),
        phone=body.phone.strip(),
        telegram_username=body.telegram_username.strip(),
        created_at=dt.datetime.utcnow(),
    )
    db.add(user)
    db.commit()

    token = create_jwt(user.email)
    return TokenOut(access_token=token)

@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password")
    if user.active_until < dt.datetime.utcnow():
        raise HTTPException(status_code=403, detail="Account expired. Please renew subscription.")

    token = create_jwt(user.email)
    return TokenOut(access_token=token)

# אליאסים לנוחות/תאימות אחורה אם יש קוד ישן שמייבא
engine = UsersEngine
SessionLocal = UsersSessionLocal
Base = UsersBase
