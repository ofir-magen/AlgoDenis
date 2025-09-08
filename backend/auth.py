import os
import sys
import datetime as dt
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, EmailStr, constr
from sqlalchemy import Column, Integer, String, DateTime, create_engine, select, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from passlib.context import CryptContext
from jose import jwt, JWTError, ExpiredSignatureError

# === מיילר ===
from mailer import send_on_registration

# === ENV / CONFIG ===
JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_IN_ENV")
JWT_ALG = "HS256"
JWT_EXPIRE_MIN = int(os.getenv("JWT_EXPIRE_MIN", "60"))

DB_URL = os.getenv("DB_URL", "sqlite:///./app.db")

engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# === DB Model ===
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    # שדות חובה
    email = Column(String(320), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    active_until = Column(DateTime, nullable=True)

    # שדות נוספים (אם קיימים אצלך בטבלה – זה יעבוד; אם לא קיימים, זה פשוט לא ימולא)
    first_name = Column(String(120), nullable=True)
    last_name = Column(String(120), nullable=True)
    phone = Column(String(64), nullable=True)
    telegram_username = Column(String(120), nullable=True)
    username = Column(String(120), nullable=True)  # אם אתה שומר שם משתמש
    approved = Column(Boolean, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# === Schemas ===
class RegisterIn(BaseModel):
    email: EmailStr
    password: constr(min_length=6, max_length=128)

    # אופציונליים (הפרונט ממלא):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    telegram_username: Optional[str] = None
    username: Optional[str] = None  # אם יש

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
        print("[AUTH] token expired", file=sys.stderr)
        return None
    except JWTError as e:
        print(f"[AUTH] token invalid: {type(e).__name__}", file=sys.stderr)
        return None

# === Router ===
router = APIRouter(prefix="/api", tags=["auth"])

@router.post("/register", response_model=TokenOut)
def register(
    body: RegisterIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    email = body.email.lower()
    exists = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="Email already registered")

    # תוקף ברירת מחדל 30 יום
    active_until = dt.datetime.utcnow() + dt.timedelta(days=30)

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        active_until=active_until,
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        telegram_username=body.telegram_username,
        username=body.username,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # שליחת מיילים ברקע:
    extra_msg = os.getenv("EMAIL_REG_MESSAGE", "").strip()
    user_dict = {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "telegram_username": user.telegram_username,
        "username": user.username,
        "active_until": user.active_until.strftime("%Y-%m-%d %H:%M:%S") if user.active_until else "",
        "approved": user.approved,
    }
    background_tasks.add_task(send_on_registration, user_dict, extra_msg)

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

    if user.active_until and user.active_until < dt.datetime.utcnow():
        raise HTTPException(status_code=403, detail="Account expired. Please renew subscription.")

    token = create_jwt(user.email)
    return TokenOut(access_token=token)
