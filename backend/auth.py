# backend/auth.py
import os
import sys
import datetime as dt
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from pydantic import BaseModel, EmailStr, constr
from sqlalchemy import (
    Column, Integer, String, DateTime, create_engine, select, Boolean, Float, func
)
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from passlib.context import CryptContext
from jose import jwt, JWTError, ExpiredSignatureError

# === מיילר ===
from mailer import send_on_registration

# =========================
# ENV / CONFIG
# =========================
JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_IN_ENV")
JWT_ALG = "HS256"
JWT_EXPIRE_MIN = int(os.getenv("JWT_EXPIRE_MIN", "60"))

# מחיר בסיס לתשלום (אפשר להגדיר גם VITE_SUB_PRICE_NIS לשמירה על תאימות)
BASE_PRICE_NIS = float(os.getenv("BASE_PRICE_NIS", os.getenv("VITE_SUB_PRICE_NIS", "49")))

# =========================
# Users DB (נפרד)
# =========================
# ברירת מחדל: Users.db בתיקיית backend. אפשר להגדיר ENV: DB_URL_USERS
USERS_DB_URL = os.getenv("DB_URL_USERS", "sqlite:///./Users.db")

UsersEngine = create_engine(
    USERS_DB_URL,
    connect_args={"check_same_thread": False} if USERS_DB_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=UsersEngine, autoflush=False, autocommit=False)
Base = declarative_base()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    # שדות חובה
    email = Column(String(320), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    active_until = Column(DateTime, nullable=True)

    # שדות נוספים
    first_name = Column(String(120), nullable=True)
    last_name = Column(String(120), nullable=True)
    phone = Column(String(64), nullable=True)
    telegram_username = Column(String(120), nullable=True)
    username = Column(String(120), nullable=True)
    approved = Column(Boolean, nullable=True)

    # שדה קופון שנשמר למשתמש בזמן הרשמה (לוגי בלבד; ולידציה מול DB הקופונים)
    coupon = Column(String(120), nullable=True)

    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

# יצירת טבלת המשתמשים אם לא קיימת
Base.metadata.create_all(bind=UsersEngine)

# מיגרציה עדינה: הוספת עמודת coupon אם חסרה (ב-SQLite)
def _ensure_coupon_column():
    try:
        with UsersEngine.begin() as conn:
            rows = conn.exec_driver_sql("PRAGMA table_info(users);").fetchall()
            col_names = [r[1] for r in rows]  # [cid, name, type, notnull, dflt_value, pk]
            if "coupon" not in col_names:
                conn.exec_driver_sql("ALTER TABLE users ADD COLUMN coupon TEXT;")
                print("[AUTH] Added 'coupon' column to users table")
    except Exception as e:
        print(f"[AUTH] ensure coupon column failed: {type(e).__name__}: {e}", file=sys.stderr)

_ensure_coupon_column()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# =========================
# Coupons DB (נפרד)
# =========================
# משתמש ב-ENV בשם Discount_Coupon (למשל: sqlite:///./DiscountCoupon.db)
_env_url = os.getenv("Discount_Coupon", "").strip()
if _env_url:
    COUPONS_DB_URL = _env_url
else:
    # אם לא הוגדר ENV — ברירת מחדל backend/DiscountCoupon.db (נתיב מוחלט כדי למנוע בלבול בהרצה)
    here = Path(__file__).resolve().parent
    COUPONS_DB_URL = f"sqlite:///{(here / 'DiscountCoupon.db').as_posix()}"

print(f"[COUPONS] Using DB: {COUPONS_DB_URL}")

CouponsEngine = create_engine(
    COUPONS_DB_URL,
    connect_args={"check_same_thread": False} if COUPONS_DB_URL.startswith("sqlite") else {},
)
CouponsSessionLocal = sessionmaker(bind=CouponsEngine, autoflush=False, autocommit=False)
CouponsBase = declarative_base()

class Coupon(CouponsBase):
    __tablename__ = "coupons"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, index=True, nullable=False)   # למשל "אופיר" או "SALE20"
    discount_percent = Column(Float, nullable=False, default=0.0)         # 10.0 == 10%

# יצירת טבלת הקופונים אם לא קיימת
CouponsBase.metadata.create_all(bind=CouponsEngine)

# =========================
# Pydantic Schemas
# =========================
class RegisterIn(BaseModel):
    email: EmailStr
    password: constr(min_length=6, max_length=128)

    # אופציונליים (הפרונט ממלא):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    telegram_username: Optional[str] = None
    username: Optional[str] = None
    coupon: Optional[str] = None  # קופון שהמשתמש הזין בזמן הרשמה

class LoginIn(BaseModel):
    email: EmailStr
    password: constr(min_length=6, max_length=128)

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

# =========================
# Helpers (Passwords & JWT)
# =========================
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

# =========================
# Router & Endpoints
# =========================
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
        coupon=(body.coupon or None),
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
        "coupon": user.coupon,
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

# === Pricing API (מחיר לפי קופון) ===
@router.get("/price")
def get_price(
    email: EmailStr = Query(..., description="מייל המשתמש לחישוב קופון"),
    base: Optional[float] = Query(None, description="מחיר בסיס ידני (לא חובה)"),
    db: Session = Depends(get_db),
):
    """
    מחזיר מחיר לאחר הנחת קופון (אם יש). הקופון עצמו נשמר אצל המשתמש (users.coupon),
    אך שיעור ההנחה נשלף מבסיס נתוני הקופונים (DiscountCoupon.db).
    """
    base_price = float(base) if base is not None else BASE_PRICE_NIS

    # מציאת המשתמש ב-Users DB
    user = db.execute(select(User).where(func.lower(User.email) == email.lower())).scalar_one_or_none()
    if not user or not (user.coupon or "").strip():
        return {
            "email": email,
            "base": round(base_price, 2),
            "discount_percent": 0.0,
            "final": round(base_price, 2),
            "coupon": None,
            "valid": False,
        }

    user_coupon = (user.coupon or "").strip()

    # חיפוש קופון ב-Coupons DB (נפרד)
    ddb = CouponsSessionLocal()
    try:
        coup = ddb.execute(
            select(Coupon).where(func.lower(Coupon.name) == user_coupon.lower())
        ).scalar_one_or_none()
    finally:
        ddb.close()

    if not coup:
        return {
            "email": email,
            "base": round(base_price, 2),
            "discount_percent": 0.0,
            "final": round(base_price, 2),
            "coupon": user_coupon,
            "valid": False,
        }

    discount = float(coup.discount_percent or 0.0)
    final_price = round(base_price * (1.0 - discount / 100.0), 2)

    return {
        "email": email,
        "base": round(base_price, 2),
        "discount_percent": round(discount, 2),
        "final": final_price,
        "coupon": user_coupon,
        "valid": True,
    }
