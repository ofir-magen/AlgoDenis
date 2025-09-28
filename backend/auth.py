# backend/auth.py
import os
import sys
import datetime as dt
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Header, Query
from pydantic import BaseModel, EmailStr, constr

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Float, create_engine, select, func
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import NullPool

from passlib.context import CryptContext
from jose import jwt, JWTError, ExpiredSignatureError

# === מיילר (אם יש לך אותו; אחרת אפשר להסיר את השורה ואת השימוש בו) ===
from mailer import send_on_registration

# ---------------- ENV/CONFIG ----------------
JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME")
JWT_ALG = "HS256"
JWT_EXPIRE_MIN = int(os.getenv("JWT_EXPIRE_MIN", "60"))
BASE_PRICE_NIS = float(os.getenv("BASE_PRICE_NIS", os.getenv("VITE_SUB_PRICE_NIS", "49")))
USERS_DB_URL = os.getenv("DB_URL_USERS", "sqlite:///./Users.db")

# ---------------- DB ----------------
Engine = create_engine(
    USERS_DB_URL,
    poolclass=NullPool if USERS_DB_URL.startswith("sqlite") else None,
    connect_args={"check_same_thread": False} if USERS_DB_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=Engine, autoflush=False, autocommit=False)
Base = declarative_base()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

class User(Base):
    __tablename__ = "users"
    # מזהה שורה (ייחודי לכל שורה)
    id = Column(Integer, primary_key=True)
    # מזהה-על קבוע לכל משתמש (אותו ערך בכל השורות של אותו משתמש)
    id_user = Column(Integer, index=True, nullable=True)

    # פרטי משתמש
    email = Column(String(320), index=True, nullable=False)   # לא unique (כי יש ריבוי שורות לאותו אימייל)
    password_hash = Column(String(255), nullable=False)

    # סטטוס מנוי לשורה זו
    approved = Column(Boolean, nullable=True, default=False)
    status = Column(String(32), nullable=True, default="pending")  # pending/active/...
    plan = Column(String(32), nullable=True, default="monthly")    # monthly/yearly/...
    period_start = Column(DateTime, nullable=True)
    active_until = Column(DateTime, nullable=True)

    # מידע נוסף
    first_name = Column(String(120), nullable=True)
    last_name = Column(String(120), nullable=True)
    phone = Column(String(64), nullable=True)
    telegram_username = Column(String(120), nullable=True)
    username = Column(String(120), nullable=True)
    coupon = Column(String(120), nullable=True)
    price_nis = Column(Float, nullable=True)
    affiliator = Column(Boolean, nullable=False, default=False)
    affiliateor_of = Column(String(120), nullable=True)

    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

Base.metadata.create_all(bind=Engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------- Schemas ----------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: constr(min_length=6, max_length=128)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    telegram_username: Optional[str] = None
    username: Optional[str] = None
    coupon: Optional[str] = None
    affiliateor_of: Optional[str] = None

class LoginIn(BaseModel):
    email: EmailStr
    password: constr(min_length=6, max_length=128)

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class PriceOut(BaseModel):
    base: float
    final: float
    discount_percent: float = 0.0
    coupon: Optional[str] = None
    valid: bool = False

class MeOut(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    telegram_username: Optional[str] = None
    username: Optional[str] = None
    approved: Optional[bool] = None
    status: Optional[str] = None
    plan: Optional[str] = None
    period_start: Optional[dt.datetime] = None
    active_until: Optional[dt.datetime] = None
    coupon: Optional[str] = None
    price_nis: Optional[float] = None
    id_user: Optional[int] = None

class SubOut(BaseModel):
    id: int
    plan: str
    price_nis: Optional[float] = None
    coupon: Optional[str] = None
    start_at: Optional[dt.datetime] = None
    end_at: Optional[dt.datetime] = None
    status: str
    id_user: Optional[int] = None

class RenewIn(BaseModel):
    plan: Optional[str] = "monthly"

# ---------------- Helpers ----------------
def hash_password(pw: str) -> str: return pwd_ctx.hash(pw)
def verify_password(pw: str, hashed: str) -> bool: return pwd_ctx.verify(pw, hashed)

def create_jwt(sub: str) -> str:
    now = dt.datetime.utcnow()
    payload = {"sub": sub, "iat": now, "exp": now + dt.timedelta(minutes=JWT_EXPIRE_MIN)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def verify_jwt(token: str) -> Optional[str]:
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        return data.get("sub")
    except ExpiredSignatureError:
        return None
    except JWTError:
        return None

def _normalize_plan(v: Optional[str]) -> str:
    if not v: return "monthly"
    p = str(v).strip().lower()
    if p in ("year", "yearly", "annual", "שנתי"): return "yearly"
    if p in ("pro",): return "pro"
    if p in ("basic",): return "basic"
    return "monthly"

# ---------------- Router ----------------
router = APIRouter(prefix="/api", tags=["auth"])

@router.post("/register", response_model=TokenOut)
def register(
    body: RegisterIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    email = body.email.lower()

    # חסימת רישום כפול באותו מייל (לשורת משתמש חדשה לגמרי)
    exists = db.execute(select(User).where(User.email == email)).scalars().first()
    if exists:
        raise HTTPException(status_code=400, detail="Email already registered")

    # קבע id_user חדש (מונה משתמשים ייחודיים, לא שורות)
    next_root = (db.execute(select(func.coalesce(func.max(User.id_user), 0))).scalar() or 0) + 1

    # מחיר בסיס (ללא קופונים כאן; הוסף אם צריך)
    final_price = BASE_PRICE_NIS

    user = User(
        id_user=next_root,                 # <<< זה ה-id_user הייחודי למשתמש
        email=email,
        password_hash=hash_password(body.password),
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        telegram_username=body.telegram_username,
        username=body.username,
        coupon=body.coupon,
        price_nis=final_price,
        affiliator=False,
        affiliateor_of=body.affiliateor_of,
        plan="monthly",
        status="pending",                  # ממתין לאישור אדמין
        approved=False,
        period_start=None,
        active_until=None,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # שליחת מייל – לא עוצרת את הזרימה אם נכשל
    try:
        extra_msg = os.getenv("EMAIL_REG_MESSAGE", "").strip()
        background_tasks.add_task(
            send_on_registration,
            {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "phone": user.phone,
                "telegram_username": user.telegram_username,
                "username": user.username,
                "coupon": user.coupon,
                "price_nis": user.price_nis,
                "affiliator": user.affiliator,
                "affiliateor_of": user.affiliateor_of,
                "active_until": "",  # עדיין אין תוקף
            },
            extra_msg,
        )
    except Exception as e:
        # נרשום ללוג אבל לא נפיל את הבקשה
        print(f"[register] mailer failed: {type(e).__name__}: {e}", file=sys.stderr)

    # תמיד מחזירים טוקן תקין
    token = create_jwt(user.email)
    return TokenOut(access_token=token)

@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    # מגיעים לשורה האחרונה לפי created_at/ID
    last = db.execute(
        select(User).where(User.email == email).order_by(User.created_at.desc(), User.id.desc())
    ).scalars().first()
    if not last:
        raise HTTPException(status_code=401, detail="User not found")
    if not verify_password(body.password, last.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password")
    # לא חוסמים על approved/expiry
    return TokenOut(access_token=create_jwt(last.email))

@router.get("/me", response_model=MeOut)
def me(authorization: str = Header(...), db: Session = Depends(get_db)):
    sub = _email_from_bearer(authorization)
    user = db.execute(
        select(User).where(User.email == sub).order_by(User.created_at.desc(), User.id.desc())
    ).scalars().first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return MeOut(
        email=user.email, first_name=user.first_name, last_name=user.last_name,
        phone=user.phone, telegram_username=user.telegram_username, username=user.username,
        approved=user.approved, status=user.status, plan=user.plan,
        period_start=user.period_start, active_until=user.active_until,
        coupon=user.coupon, price_nis=user.price_nis, id_user=user.id_user,
    )

@router.get("/subscriptions", response_model=list[SubOut])
def my_subscriptions(authorization: str = Header(...), db: Session = Depends(get_db)):
    sub = _email_from_bearer(authorization)
    rows = db.execute(
        select(User).where(User.email == sub).order_by(User.created_at.desc(), User.id.desc())
    ).scalars().all()
    return [
        SubOut(
            id=r.id, plan=r.plan or "monthly", price_nis=r.price_nis, coupon=r.coupon,
            start_at=r.period_start, end_at=r.active_until,
            status=r.status or ("active" if (r.approved and r.active_until and r.active_until > dt.datetime.utcnow()) else "pending"),
            id_user=r.id_user,
        ) for r in rows
    ]

@router.post("/subscriptions/renew", response_model=SubOut)
def renew_subscription(body: RenewIn, authorization: str = Header(...), db: Session = Depends(get_db)):
    """
    יוצר שורה חדשה (הזמנה) למשתמש – רק אם אין כרגע הזמנה ממתינה לאישור אדמין.
    אם השורה האחרונה היא במצב pending/לא מאושרת → נחסום (409).
    אם יש מנוי פעיל – נבקש אישור בפרונט, אבל ה־API עדיין מאפשר (אין חסימה במקרה זה).
    """
    sub = _email_from_bearer(authorization)

    # השורה האחרונה של המשתמש
    last = db.execute(
        select(User)
        .where(User.email == sub)
        .order_by(User.created_at.desc(), User.id.desc())
    ).scalars().first()

    if not last:
        raise HTTPException(status_code=404, detail="User not found")

    # אם האחרונה ממתינה לאישור (approved=False) → לא מאפשרים ליצור עוד הזמנה
    last_status = (last.status or "pending").lower()
    if (not last.approved) and (last_status == "pending"):
        raise HTTPException(status_code=409, detail="Order is pending admin approval; cannot purchase again yet")

    # אחרת – ליצור הזמנה חדשה (pending) עם אותו id_user
    plan_norm = _normalize_plan(body.plan or last.plan or "monthly")
    new_row = User(
        id_user=last.id_user or last.id,
        email=last.email,
        password_hash=last.password_hash,
        first_name=last.first_name,
        last_name=last.last_name,
        phone=last.phone,
        telegram_username=last.telegram_username,
        username=last.username,
        coupon=last.coupon,
        price_nis=last.price_nis,
        affiliator=last.affiliator,
        affiliateor_of=last.affiliateor_of,
        plan=plan_norm,
        status="pending",
        approved=False,
        period_start=None,
        active_until=None,
    )
    db.add(new_row)
    db.commit()
    db.refresh(new_row)

    return SubOut(
        id=new_row.id,
        plan=new_row.plan or "monthly",
        price_nis=new_row.price_nis,
        coupon=new_row.coupon,
        start_at=new_row.period_start,
        end_at=new_row.active_until,
        status=new_row.status or "pending",
        id_user=new_row.id_user,
    )

@router.get("/price", response_model=PriceOut)
def get_price(email: EmailStr = Query(...), db: Session = Depends(get_db)):
    base = BASE_PRICE_NIS
    user = db.execute(
        select(User).where(User.email == email.lower()).order_by(User.created_at.desc(), User.id.desc())
    ).scalars().first()
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

    return PriceOut(base=base, final=final, discount_percent=discount if discount > 0 else 0.0, coupon=coup, valid=bool(coup and discount > 0))

# ------------- helpers -------------
def _email_from_bearer(authorization: str) -> str:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(None, 1)[1]
    sub = verify_jwt(token)
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return sub
