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

# מחיר בסיס (נשלף גם מה-ENV של הפרונט אם הוגדר שם)
BASE_PRICE_NIS = float(os.getenv("BASE_PRICE_NIS", os.getenv("VITE_SUB_PRICE_NIS", "49")))

# =========================
# Users DB (נפרד)
# =========================
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

    # קופון/מחיר
    coupon = Column(String(120), nullable=True)
    price_nis = Column(Float, nullable=True)

    # אפיליאציה
    affiliateor = Column(String(120), nullable=True)       # מי שהפנה את המשתמש
    affiliateor_of = Column(String(120), nullable=True)    # את מי המשתמש הפנה

    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


Base.metadata.create_all(bind=UsersEngine)


# === מיגרציות (SQLite) — הוספת עמודות אם חסרות ===
def _ensure_column(name: str, col_type: str):
    try:
        with UsersEngine.begin() as conn:
            rows = conn.exec_driver_sql("PRAGMA table_info(users);").fetchall()
            col_names = [r[1] for r in rows]
            if name not in col_names:
                conn.exec_driver_sql(f"ALTER TABLE users ADD COLUMN {name} {col_type};")
                print(f"[AUTH] Added '{name}' column to users table")
    except Exception as e:
        print(f"[AUTH] ensure column {name} failed: {type(e).__name__}: {e}", file=sys.stderr)


_ensure_column("coupon", "TEXT")
_ensure_column("price_nis", "REAL")
_ensure_column("affiliateor", "TEXT")
_ensure_column("affiliateor_of", "TEXT")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================
# Coupons DB (נפרד)
# =========================
_env_url = os.getenv("Discount_Coupon", "").strip()
if _env_url:
    COUPONS_DB_URL = _env_url
else:
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
    name = Column(String(120), unique=True, index=True, nullable=False)
    discount_percent = Column(Float, nullable=False, default=0.0)


CouponsBase.metadata.create_all(bind=CouponsEngine)


# =========================
# Schemas
# =========================
class RegisterIn(BaseModel):
    email: EmailStr
    password: constr(min_length=6, max_length=128)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    telegram_username: Optional[str] = None
    username: Optional[str] = None
    coupon: Optional[str] = None
    affiliateor: Optional[str] = None
    affiliateor_of: Optional[str] = None


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
# Router
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

    # חישוב מחיר לפי קופון
    base_price = BASE_PRICE_NIS
    final_price = base_price
    coupon_code = (body.coupon or "").strip()

    if coupon_code:
        cdb = CouponsSessionLocal()
        try:
            coup = cdb.execute(
                select(Coupon).where(func.lower(Coupon.name) == coupon_code.lower())
            ).scalar_one_or_none()
            if coup and coup.discount_percent > 0:
                final_price = round(base_price * (1.0 - coup.discount_percent / 100.0), 2)
        finally:
            cdb.close()

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        active_until=dt.datetime.utcnow() + dt.timedelta(days=30),
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        telegram_username=body.telegram_username,
        username=body.username,
        coupon=body.coupon,
        price_nis=final_price,
        affiliateor=body.affiliateor,
        affiliateor_of=body.affiliateor_of,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # ==== הכנת "תוקף" לפורמט קריא במייל ====
    expiry_dt = user.active_until or dt.datetime.utcnow()
    try:
        from zoneinfo import ZoneInfo  # Python 3.9+
        tz_name = os.getenv("TZ_MAIL", "Asia/Jerusalem")
        # אם נשמר ללא tzinfo נניח שזה UTC
        if expiry_dt.tzinfo is None:
            expiry_dt = expiry_dt.replace(tzinfo=dt.timezone.utc)
        expiry_local = expiry_dt.astimezone(ZoneInfo(tz_name))
    except Exception:
        expiry_local = expiry_dt  # fallback ללא המרה

    active_until_str = expiry_local.strftime("%d.%m.%Y %H:%M")
    # ========================================

    # שליחת מייל
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
        "price_nis": user.price_nis,
        "affiliateor": user.affiliateor,
        "affiliateor_of": user.affiliateor_of,
        "active_until": active_until_str,  # ← נשלח למיילר
    }
    background_tasks.add_task(send_on_registration, user_dict, extra_msg)

    return TokenOut(access_token=create_jwt(user.email))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password")
    if user.active_until and user.active_until < dt.datetime.utcnow():
        raise HTTPException(status_code=403, detail="Account expired")
    return TokenOut(access_token=create_jwt(user.email))


# === /api/price – החזרת מחיר למייל נתון ===
class PriceOut(BaseModel):
    base: float
    final: float
    discount_percent: float = 0.0
    coupon: Optional[str] = None
    valid: bool = False

@router.get("/price", response_model=PriceOut)
def get_price(email: EmailStr = Query(...), db: Session = Depends(get_db)):
    """
    מחזיר מחיר בסיס/סופי למשתמש לפי המייל.
    אם המשתמש קיים עם price_nis/coupon – נחזיר את זה.
    אם לא – נחזיר מחיר בסיס בלבד.
    """
    base = BASE_PRICE_NIS
    user = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
    if not user:
        return PriceOut(base=base, final=base, discount_percent=0.0, coupon=None, valid=False)

    final = float(user.price_nis or base)
    coup = (user.coupon or "").strip() or None
    discount = 0.0
    if coup and final < base:
        try:
            discount = round((1.0 - (final / base)) * 100.0, 2)
        except Exception:
            discount = 0.0

    return PriceOut(
        base=base,
        final=final,
        discount_percent=discount if discount > 0 else 0.0,
        coupon=coup,
        valid=bool(coup and discount > 0),
    )
