# backend/main.py
# FastAPI auth + affiliate dashboard (SQLite).
# Environment (backend/.env preferred; else nearest .env):
#   USERS_DB_PATH=sqlite:///../backend/Users.db
#   USERS_TABLE=users
#   EMAIL_COL=email
#   PASSWORD_HASH_COL=password_hash
#   ACTIVE_COL=approved
#   HASH_SCHEME=bcrypt
#   FRONTEND_ORIGINS=http://localhost:5180,http://127.0.0.1:5180
#   SECRET_KEY=change-me
#   API_PORT=8020
#
#   # Coupons DB (now with `coupon` column name):
#   COUPONS_DB_PATH=sqlite:///../backend/DiscountCoupon.db
#   COUPONS_TABLE=coupons
#   COUPON_CODE_COL=coupon
#   PARTNER_EMAIL_COL=affiliator_mail
#   USERS_COUPON_COL=coupon

import os
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import Header
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt, JWTError
from passlib.hash import bcrypt
from dotenv import load_dotenv, find_dotenv
from pydantic import BaseModel

# ---------- Load env (prefer backend/.env, else nearest .env up the tree) ----------
HERE = Path(__file__).resolve().parent
backend_env = HERE / ".env"
if backend_env.exists():
    load_dotenv(backend_env)
    ENV_DIR = backend_env.parent
else:
    env_file = find_dotenv()
    if not env_file:
        raise RuntimeError("Could not find .env (put it in backend/ or project root)")
    load_dotenv(env_file)
    ENV_DIR = Path(env_file).resolve().parent

# ---------- Settings ----------
SECRET_KEY  = os.getenv("SECRET_KEY", "dev-secret-change-me")
ALGO        = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "43200"))
FRONTEND_ORIGINS = [o.strip() for o in os.getenv("FRONTEND_ORIGINS", "http://localhost:5180").split(",") if o.strip()]
API_PORT    = int(os.getenv("API_PORT", "8020"))

USERS_DB_URI       = os.getenv("USERS_DB_PATH", "sqlite:///./Users.db")
USERS_TABLE        = os.getenv("USERS_TABLE", "users")
EMAIL_COL          = os.getenv("EMAIL_COL", os.getenv("USERNAME_COL", "email"))
PASSWORD_HASH_COL  = os.getenv("PASSWORD_HASH_COL", "password_hash")
ACTIVE_COL         = os.getenv("ACTIVE_COL", "approved")
HASH_SCHEME        = os.getenv("HASH_SCHEME", "bcrypt").lower()  # bcrypt | plain

def _normalize_db_uri_to_path(uri: str) -> str:
    if uri.startswith("sqlite:///"):
        raw = uri[len("sqlite:///"):]
    elif uri.startswith("file://"):
        raw = uri[len("file://"):]
    else:
        raise RuntimeError("USERS_DB_PATH/COUPONS_DB_PATH must start with sqlite:/// or file://")
    p = Path(raw)
    if not p.is_absolute():
        p = (ENV_DIR / p).resolve()
    return str(p)

USERS_DB_PATH = _normalize_db_uri_to_path(USERS_DB_URI)

# ---- Affiliate/Coupons settings ----
COUPONS_DB_URI      = os.getenv("COUPONS_DB_PATH", USERS_DB_URI)  # default: same DB as users unless set
COUPONS_TABLE       = os.getenv("COUPONS_TABLE", "coupons")
COUPON_CODE_COL     = os.getenv("COUPON_CODE_COL", "coupon")
PARTNER_EMAIL_COL   = os.getenv("PARTNER_EMAIL_COL", "affiliator_mail")
USERS_COUPON_COL    = os.getenv("USERS_COUPON_COL", "coupon")
COUPONS_DB_PATH     = _normalize_db_uri_to_path(COUPONS_DB_URI)

# ---------- App ----------
app = FastAPI(title="Affiliates API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Schemas ----------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserOut(BaseModel):
    email: str

class DashboardData(BaseModel):
    message: str
    user: UserOut

# ---------- Helpers ----------
def _is_active_value(v) -> bool:
    """Decide if a DB value counts as 'active'."""
    if v is None:
        return False
    s = str(v).strip().lower()
    inactive = {"0", "false", "pending", "disabled", "inactive", ""}
    active   = {"1", "true", "approved", "yes", "enabled", "active"}
    if s in active:
        return True
    if s in inactive:
        return False
    try:
        return float(s) != 0.0
    except Exception:
        return True

def _verify_password(plain: str, stored_hash: str) -> bool:
    if HASH_SCHEME == "bcrypt":
        try:
            return bcrypt.verify(plain, stored_hash)
        except Exception:
            return False
    elif HASH_SCHEME == "plain":
        return plain == stored_hash
    else:
        raise HTTPException(status_code=500, detail=f"Unsupported HASH_SCHEME: {HASH_SCHEME}")

def verify_user(email: str, password: str) -> bool:
    if not os.path.exists(USERS_DB_PATH):
        raise HTTPException(status_code=500, detail="Users DB not found. Check USERS_DB_PATH in .env")
    q = f"SELECT {PASSWORD_HASH_COL}"
    include_active = bool(ACTIVE_COL)
    if include_active:
        q += f", {ACTIVE_COL}"
    q += f" FROM {USERS_TABLE} WHERE {EMAIL_COL} = ? LIMIT 1"
    try:
        con = sqlite3.connect(USERS_DB_PATH)
        cur = con.cursor()
        cur.execute(q, (email,))
        row = cur.fetchone()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")
    finally:
        try: con.close()
        except Exception: pass
    if not row:
        return False
    if include_active:
        pwd_hash, active_val = row[0], row[1]
        if not _is_active_value(active_val):
            return False
    else:
        pwd_hash = row[0]
    return _verify_password(password, pwd_hash)

def create_access_token(subject: str, minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    exp = datetime.utcnow() + timedelta(minutes=minutes)
    payload = {"sub": subject, "exp": exp}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGO)

def decode_access_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGO])
        sub = payload.get("sub")
        if not sub:
            raise JWTError("Missing sub")
        return sub
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def bearer_from_header(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return authorization.split(" ", 1)[1].strip()

def _fetchall_dicts(con, query: str, params: tuple = ()):
    cur = con.cursor()
    cur.execute(query, params)
    cols = [c[0] for c in cur.description]
    rows = cur.fetchall()
    return [dict(zip(cols, r)) for r in rows]

def _get_users_table_columns() -> List[str]:
    """Return users table column names to always render headers on FE."""
    if not os.path.exists(USERS_DB_PATH):
        return []
    try:
        con = sqlite3.connect(USERS_DB_PATH)
        cur = con.cursor()
        cur.execute(f"PRAGMA table_info({USERS_TABLE})")
        rows = cur.fetchall()  # (cid, name, type, notnull, dflt_value, pk)
        cols = [r[1] for r in rows]
    except Exception:
        cols = []
    finally:
        try: con.close()
        except Exception: pass
    return cols

def _get_all_coupons() -> List[str]:
    """Return ALL coupon codes in system (for terminal print)."""
    if not os.path.exists(COUPONS_DB_PATH):
        print(f"[WARN] Coupons DB not found at {COUPONS_DB_PATH}")
        return []
    try:
        con = sqlite3.connect(COUPONS_DB_PATH)
        cur = con.cursor()
        x = f"SELECT {COUPON_CODE_COL} FROM {COUPONS_TABLE}"
        print("xxxxxxxxxxxxx ", x)
        cur.execute(f"SELECT {COUPON_CODE_COL} FROM {COUPONS_TABLE}")
        rows = cur.fetchall()
        coupons = [str(r[0]).strip() for r in rows if r and r[0] is not None and str(r[0]).strip()]
        coupons = sorted(set(coupons))
        return coupons
    except Exception as e:
        print(f"[ERROR] _get_all_coupons failed: {e}")
        return []
    finally:
        try: con.close()
        except Exception: pass

def _get_partner_coupons(partner_email: str) -> List[str]:
    """Return coupons that belong to this partner (by PARTNER_EMAIL_COL)."""
    if not partner_email or not os.path.exists(COUPONS_DB_PATH):
        return []
    try:
        con = sqlite3.connect(COUPONS_DB_PATH)
        cur = con.cursor()
        cur.execute(
            f"SELECT {COUPON_CODE_COL} FROM {COUPONS_TABLE} WHERE {PARTNER_EMAIL_COL} = ?",
            (partner_email,)
        )
        rows = cur.fetchall()
        coupons = [str(r[0]).strip() for r in rows if r and r[0] is not None and str(r[0]).strip()]
        return sorted(set(coupons))
    except Exception as e:
        print(f"[ERROR] _get_partner_coupons failed: {e}")
        return []
    finally:
        try: con.close()
        except Exception: pass

def _users_for_partner_by_coupons(partner_email: str) -> List[Dict[str, Any]]:
    """Fetch all users whose coupon is one of the partner's coupons."""
    coupons = _get_partner_coupons(partner_email)
    if not coupons:
        return []
    placeholders = ",".join("?" for _ in coupons)
    q = f"SELECT * FROM {USERS_TABLE} WHERE {USERS_COUPON_COL} IN ({placeholders})"
    con = None
    try:
        con = sqlite3.connect(USERS_DB_PATH)
        return _fetchall_dicts(con, q, tuple(coupons))
    except Exception as e:
        print(f"[ERROR] _users_for_partner_by_coupons failed: {e}")
        return []
    finally:
        try: con.close()
        except Exception: pass

# ---------- Date parsing helpers for metrics ----------
POSSIBLE_DATE_COLS = [
    # Prefer explicit payment columns
    "paid_at", "payment_date", "last_payment_at", "last_payment", "charged_at",
    # Common signup/creation columns as fallback
    "created_at", "signup_date", "registered_at", "created", "Date", "date"
]

def _get_existing_columns(table: str, db_path: str) -> List[str]:
    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        rows = cur.fetchall()
        return [r[1] for r in rows]
    except Exception:
        return []
    finally:
        try: con.close()
        except Exception: pass

def _guess_date_column(table: str, db_path: str) -> Optional[str]:
    cols = set(_get_existing_columns(table, db_path))
    for c in POSSIBLE_DATE_COLS:
        if c in cols:
            return c
    return None

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")

def _parse_to_ym(value: Any) -> Optional[str]:
    """
    Try to convert many shapes of date/time to 'YYYY-MM'. Returns None if can't parse.
    """
    if value is None:
        return None
    s = str(value).strip()

    # Already 'YYYY-MM' or 'YYYY-MM-DD...'
    if _ISO_RE.match(s):
        try:
            y, m = s[0:4], s[5:7]
            int(y); int(m)
            return f"{y}-{m}"
        except Exception:
            pass

    # 'DD/MM/YYYY' or 'DD-MM-YYYY'
    for sep in ("/", "-"):
        parts = s.split(sep)
        if len(parts) == 3 and len(parts[2]) == 4:
            try:
                d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                return f"{y:04d}-{m:02d}"
            except Exception:
                pass

    # Epoch seconds or ms
    try:
        num = int(float(s))
        if num > 10_000_000_000:
            num = num // 1000  # ms -> s
        dt = datetime.utcfromtimestamp(num)
        return dt.strftime("%Y-%m")
    except Exception:
        pass

    # Common strptime formats
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m")
        except Exception:
            continue

    return None

# ---------- Routes ----------
@app.get("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}

@app.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends()):
    email = form.username
    password = form.password
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")
    if not verify_user(email, password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(subject=email)
    return Token(access_token=token)

@app.get("/me", response_model=UserOut)
def me(authorization: Optional[str] = Header(None)):
    email = decode_access_token(bearer_from_header(authorization))
    return UserOut(email=email)

@app.get("/dashboard/data", response_model=DashboardData)
def dashboard_data(authorization: Optional[str] = Header(None)):
    email = decode_access_token(bearer_from_header(authorization))
    return DashboardData(message="מחובר!", user=UserOut(email=email))

@app.get("/dashboard/aff-users")
def dashboard_aff_users(authorization: Optional[str] = Header(None)):
    """
    Returns:
      - partner_email: str
      - coupons: list[str] that belong to this partner
      - columns: list[str] = all users table columns (for headers even when empty)
      - users: list[dict] = all users whose USERS_COUPON_COL is in partner coupons
    Also prints ALL coupons in system to terminal on each call.
    """
    partner_email = decode_access_token(bearer_from_header(authorization))
    print("ofir_partner_email:", partner_email)
    columns = _get_users_table_columns()

    # 1) Print ALL coupons (debug/info)
    all_coupons = _get_all_coupons()
    print(f"[INFO] ALL coupons in system ({len(all_coupons)}): {all_coupons}")

    # 2) Coupons for this partner
    coupons = _get_partner_coupons(partner_email)
    print(f"[DEBUG] Partner {partner_email} coupons ({len(coupons)}): {coupons}")

    if not coupons:
        return {
            "partner_email": partner_email,
            "coupons": [],
            "columns": columns,
            "users": [],
        }

    users = _users_for_partner_by_coupons(partner_email)

    return {
        "partner_email": partner_email,
        "coupons": coupons,
        "columns": columns,
        "users": users,
    }

# ---------- NEW: Metrics endpoints ----------

class MonthlyPoint(BaseModel):
    month: str   # 'YYYY-MM'
    count: int

class MonthlySummaryResponse(BaseModel):
    partner_email: str
    coupon_codes: List[str]
    date_column: Optional[str]
    points: List[MonthlyPoint]

@app.get("/dashboard/monthly-summary", response_model=MonthlySummaryResponse)
def monthly_summary(authorization: Optional[str] = Header(None)):
    """
    Aggregate counts by month for users who used the partner's coupons.
    Date column is auto-guessed from POSSIBLE_DATE_COLS.
    """
    partner_email = decode_access_token(bearer_from_header(authorization))
    coupons = _get_partner_coupons(partner_email)
    date_col = _guess_date_column(USERS_TABLE, USERS_DB_PATH)

    if not coupons:
        return MonthlySummaryResponse(
            partner_email=partner_email, coupon_codes=[], date_column=date_col, points=[]
        )

    users = _users_for_partner_by_coupons(partner_email)

    # aggregate to { 'YYYY-MM': count }
    buckets: Dict[str, int] = {}
    for u in users:
        raw = None
        if date_col and date_col in u:
            raw = u.get(date_col)
        else:
            # fallback: try to find any of POSSIBLE_DATE_COLS on the row
            for c in POSSIBLE_DATE_COLS:
                if c in u and u[c]:
                    raw = u[c]
                    break
        ym = _parse_to_ym(raw)
        if ym is None:
            continue
        buckets[ym] = buckets.get(ym, 0) + 1

    points = [MonthlyPoint(month=k, count=v) for k, v in sorted(buckets.items())]
    return MonthlySummaryResponse(
        partner_email=partner_email,
        coupon_codes=coupons,
        date_column=date_col,
        points=points
    )

class UsersByMonthResponse(BaseModel):
    month: str
    columns: List[str]
    users: List[dict]

@app.get("/dashboard/users-by-month", response_model=UsersByMonthResponse)
def users_by_month(month: str, authorization: Optional[str] = Header(None)):
    """
    Return the concrete users for a given 'YYYY-MM' month (based on the guessed date column).
    """
    partner_email = decode_access_token(bearer_from_header(authorization))
    date_col = _guess_date_column(USERS_TABLE, USERS_DB_PATH)
    users = _users_for_partner_by_coupons(partner_email)

    filtered: List[dict] = []
    for u in users:
        raw = u.get(date_col) if (date_col and date_col in u) else None
        if raw is None:
            for c in POSSIBLE_DATE_COLS:
                if c in u and u[c]:
                    raw = u[c]
                    break
        ym = _parse_to_ym(raw)
        if ym == month:
            filtered.append(u)

    columns = _get_users_table_columns()
    return UsersByMonthResponse(month=month, columns=columns, users=filtered)

class CouponStat(BaseModel):
    coupon: str
    count: int

class CouponStatsResponse(BaseModel):
    partner_email: str
    stats: List[CouponStat]

@app.get("/dashboard/coupon-stats", response_model=CouponStatsResponse)
def coupon_stats(authorization: Optional[str] = Header(None)):
    """
    Count users per coupon for this partner.
    """
    partner_email = decode_access_token(bearer_from_header(authorization))
    coupons = _get_partner_coupons(partner_email)
    if not coupons:
        return {"partner_email": partner_email, "stats": []}

    users = _users_for_partner_by_coupons(partner_email)
    counter: Dict[str, int] = {}
    for u in users:
        c = str(u.get(USERS_COUPON_COL, "") or "").strip()
        if not c:
            continue
        if c in coupons:
            counter[c] = counter.get(c, 0) + 1

    stats = [CouponStat(coupon=k, count=v) for k, v in sorted(counter.items())]
    return {"partner_email": partner_email, "stats": stats}

class StatusStatsResponse(BaseModel):
    field: Optional[str]
    active_count: int
    inactive_count: int

@app.get("/dashboard/status-stats", response_model=StatusStatsResponse)
def status_stats(authorization: Optional[str] = Header(None)):
    """
    Count active vs inactive using ACTIVE_COL if defined.
    If ACTIVE_COL is missing, treat all as active to avoid confusion.
    """
    partner_email = decode_access_token(bearer_from_header(authorization))
    users = _users_for_partner_by_coupons(partner_email)

    if not ACTIVE_COL:
        return {"field": None, "active_count": len(users), "inactive_count": 0}

    active, inactive = 0, 0
    for u in users:
        v = u.get(ACTIVE_COL)
        if _is_active_value(v):
            active += 1
        else:
            inactive += 1

    return {"field": ACTIVE_COL, "active_count": active, "inactive_count": inactive}
