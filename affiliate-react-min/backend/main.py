# backend/main.py
# FastAPI (email+password) auth against existing SQLite Users DB.
# .env (backend/.env מועדף; אחרת .env בשורש):
#   USERS_DB_PATH=sqlite:///../backend/Users.db   # או file:///abs/path.db
#   USERS_TABLE=users
#   EMAIL_COL=email
#   PASSWORD_HASH_COL=password_hash
#   ACTIVE_COL=approved   # ברירת מחדל כאן היא approved
#   HASH_SCHEME=bcrypt    # או plain
#   FRONTEND_ORIGINS=http://localhost:5180,http://127.0.0.1:5180
#   SECRET_KEY=change-me
#   API_PORT=8020

import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional
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

USERS_DB_URI       = os.getenv("USERS_DB_PATH", "sqlite:///./Users.db")  # MUST start with sqlite:/// or file://
USERS_TABLE        = os.getenv("USERS_TABLE", "users")
EMAIL_COL          = os.getenv("EMAIL_COL", os.getenv("USERNAME_COL", "email"))
PASSWORD_HASH_COL  = os.getenv("PASSWORD_HASH_COL", "password_hash")
ACTIVE_COL         = os.getenv("ACTIVE_COL", "approved")  # <— ברירת מחדל approved
HASH_SCHEME        = os.getenv("HASH_SCHEME", "bcrypt").lower()  # bcrypt | plain

def _normalize_db_uri_to_path(uri: str) -> str:
    if uri.startswith("sqlite:///"):
        raw = uri[len("sqlite:///"):]
    elif uri.startswith("file://"):
        raw = uri[len("file://"):]
    else:
        raise RuntimeError(
            "USERS_DB_PATH must start with 'sqlite:///' or 'file://'. "
            f"Got: {uri!r}"
        )
    p = Path(raw)
    if not p.is_absolute():
        p = (ENV_DIR / p).resolve()
    return str(p)

USERS_DB_PATH = _normalize_db_uri_to_path(USERS_DB_URI)

# ---------- App ----------
app = FastAPI(title="Affiliates API (email login, approved flag)")
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
    """Interpret ACTIVE_COL value. Flexible for ints/strings/booleans."""
    if v is None:
        return False
    s = str(v).strip().lower()

    inactive = {"0", "false", "pending", "disabled", "inactive", ""}
    active   = {"1", "true", "approved", "yes", "enabled", "active"}

    if s in active:
        return True
    if s in inactive:
        return False

    # Fallback: treat any non-empty, non-zero-ish value as active
    try:
        # if it's numeric string like "2" → consider active
        return float(s) != 0.0
    except Exception:
        return True  # any other non-empty string → active

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

    # Build query (include ACTIVE_COL if defined)
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
        try:
            con.close()
        except Exception:
            pass

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

# ---------- Routes ----------
@app.get("/me", response_model=UserOut)
def me(authorization: Optional[str] = Header(None)):
    email = decode_access_token(bearer_from_header(authorization))
    return UserOut(email=email)

@app.get("/dashboard/data", response_model=DashboardData)
def dashboard_data(authorization: Optional[str] = Header(None)):
    email = decode_access_token(bearer_from_header(authorization))
    return DashboardData(message="מחובר!", user=UserOut(email=email))

@app.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends()):
    # form.username מכיל את *האימייל* (שם השדה נשאר username לפי התקן)
    email = form.username
    password = form.password
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")
    if not verify_user(email, password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(subject=email)
    return Token(access_token=token)

@app.get("/me", response_model=UserOut)
def me(authorization: Optional[str] = None):
    email = decode_access_token(bearer_from_header(authorization))
    return UserOut(email=email)

@app.get("/dashboard/data", response_model=DashboardData)
def dashboard_data(authorization: Optional[str] = None):
    email = decode_access_token(bearer_from_header(authorization))
    return DashboardData(message="מחובר!", user=UserOut(email=email))
