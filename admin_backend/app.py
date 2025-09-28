# admin_backend/app.py
import json
import os
import datetime as dt
from pathlib import Path
from typing import Any, Dict, Optional, List

from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from jose import jwt, JWTError
from dotenv import load_dotenv

from sqlalchemy import (
    create_engine, MetaData, Table, select, update, delete, insert, text as sql_text,
    DateTime as SATime, Boolean as SABool, Integer as SAInt, Float as SAFloat, String as SAString
)
from sqlalchemy.orm import sessionmaker

# ================== ENV ==================
load_dotenv()

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin")

JWT_SECRET = os.getenv("ADMIN_JWT_SECRET", "CHANGE_ME")
JWT_ALG = "HS256"
JWT_EXPIRE_MIN = int(os.getenv("ADMIN_JWT_EXPIRE_MIN", "240"))

SETTINGS_FILE_PATH = os.getenv("SETTINGS_FILE_PATH", "db/settings.json")

# -------------------------------------------------------
# RESOLVERS — build absolute sqlite URLs from relative env paths
# -------------------------------------------------------
def _resolve_sqlite_url_from_env_var(env_key: str, example_rel: str) -> str:
    """
    Expects an env var value like:
      sqlite:///../backend/Users.db
    Returns an absolute sqlite URL relative to this app.py location.
    Supports only sqlite:/// scheme.
    """
    raw = (os.getenv(env_key) or "").strip()
    if not raw:
        raise RuntimeError(f"{env_key} is missing in .env (expected 'sqlite:///{example_rel}').")
    if not raw.startswith("sqlite:///"):
        raise RuntimeError(f"{env_key} must start with 'sqlite:///' and be relative like '{example_rel}'.")
    rel = raw[len("sqlite:///"):]            # e.g. ../backend/Users.db
    here = Path(__file__).resolve().parent
    abs_path = (here / rel).resolve()
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{abs_path.as_posix()}"

# Two DBs (Users and DataLog)
USERS_DB_URL   = _resolve_sqlite_url_from_env_var("USERS_DB_PATH",   "../backend/Users.db")
DATALOG_DB_URL = _resolve_sqlite_url_from_env_var("DATA_LOG_PATH",   "../backend/DataLog.db")

# ================== Users DB ==================
users_is_sqlite = USERS_DB_URL.startswith("sqlite:")
users_engine = create_engine(
    USERS_DB_URL, future=True, pool_pre_ping=True,
    connect_args={"check_same_thread": False} if users_is_sqlite else {},
)
UsersSession = sessionmaker(bind=users_engine, autoflush=False, autocommit=False, future=True)
users_meta = MetaData()
users = Table("users", users_meta, autoload_with=users_engine)

# ================== DataLog DB ==================
datalog_is_sqlite = DATALOG_DB_URL.startswith("sqlite:")
datalog_engine = create_engine(
    DATALOG_DB_URL, future=True, pool_pre_ping=True,
    connect_args={"check_same_thread": False} if datalog_is_sqlite else {},
)
DataLogSession = sessionmaker(bind=datalog_engine, autoflush=False, autocommit=False, future=True)
datalog_meta = MetaData()

# If table datalog does not exist, create a minimal schema
with datalog_engine.begin() as conn:
    exists = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='datalog';"
    ).fetchone()
    if not exists:
        conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS datalog (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          symbol TEXT NOT NULL,
          signal_type TEXT,
          entry_time   TEXT,
          entry_price  REAL,
          exit_time    TEXT,
          exit_price   REAL,
          change_pct   REAL,
          assigned     TEXT,
          created_at   TEXT DEFAULT (datetime('now')),
          updated_at   TEXT DEFAULT (datetime('now'))
        );
        """)
datalog = Table("datalog", datalog_meta, autoload_with=datalog_engine)

# ================== APP ==================
app = FastAPI(title="Admin API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================== JWT helpers ==================
def create_token(sub: str) -> str:
    now = dt.datetime.utcnow()
    payload = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(minutes=JWT_EXPIRE_MIN)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def require_auth(authorization: Optional[str] = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1].strip()
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        return data.get("sub") or ""
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ================== Settings JSON helpers ==================
def _resolve_settings_path() -> str:
    base_dir = Path(__file__).resolve().parent
    return str((base_dir / SETTINGS_FILE_PATH).resolve())

def getJsonData():
    path = _resolve_settings_path()
    if not os.path.exists(path):
        raise FileNotFoundError(f"JSON file not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def setJsonData(data: dict):
    path = _resolve_settings_path()
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)

# ================== Utils ==================
def parse_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "y", "on", "✓", "כן"}

def parse_dt(value: Any) -> Optional[dt.datetime]:
    if value in (None, "", "null"):
        return None
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return dt.datetime.utcfromtimestamp(float(value))
        except Exception:
            pass
    s = str(value).strip()
    s = s.replace(" ,", ",").replace(", ", ",")
    fmts = [
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y,%H:%M",
        "%d/%m/%Y, %H:%M",
        "%d.%m.%Y %H:%M",
        "%d-%m-%Y %H:%M",
    ]
    for f in fmts:
        try:
            return dt.datetime.strptime(s, f)
        except Exception:
            pass
    try:
        if "T" in s and len(s.split(":")) == 2:
            s = s + ":00"
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None

def row_to_dict(row) -> Dict[str, Any]:
    d = dict(row._mapping)
    for k, v in list(d.items()):
        if isinstance(v, dt.datetime):
            d[k] = v.strftime("%Y-%m-%d %H:%M:%S")
    return d

def _calc_change_pct(entry_price, exit_price) -> Optional[float]:
    """Compute % change based on entry/exit prices; returns None if not computable."""
    try:
        a = float(entry_price)
        b = float(exit_price)
        if a == 0:
            return None
        return ((b - a) / a) * 100.0
    except Exception:
        return None

# ---- plan helpers (for user approvals) ----
def _normalize_plan(v: Optional[str]) -> str:
    if not v:
        return "monthly"
    p = str(v).strip().lower()
    if p in ("year", "yearly", "annual", "שנתי"):
        return "yearly"
    if p in ("pro",):
        return "pro"
    if p in ("basic",):
        return "basic"
    return "monthly"

def _period_days(plan_norm: str) -> int:
    return 365 if plan_norm == "yearly" else 30

# ================== Schemas ==================
class LoginIn(BaseModel):
    username: str
    password: str

class DataLogCreateIn(BaseModel):
    symbol: str
    signal_type: Optional[str] = None
    entry_time: Optional[str] = None
    entry_price: Optional[float] = None
    exit_time: Optional[str] = None
    exit_price: Optional[float] = None
    change_pct: Optional[float] = None

# ================== Routes ==================
@app.get("/api/health")
def health():
    return {
        "ok": True,
        "users_db": USERS_DB_URL,
        "datalog_db": DATALOG_DB_URL,
    }

@app.post("/api/login")
def login(body: LoginIn):
    if body.username != ADMIN_USER or body.password != ADMIN_PASS:
        raise HTTPException(status_code=401, detail="Bad credentials")
    return {"token": create_token(body.username)}

# -------- Settings --------
@app.get("/api/settings")
def get_settings(_: str = Depends(require_auth)):
    data = getJsonData()
    return {"x": int(data.get("x", 0)), "y": int(data.get("y", 0))}

@app.patch("/api/settings")
async def patch_settings(request: Request, _: str = Depends(require_auth)):
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be JSON object")
    cur = getJsonData()
    if "x" in payload: cur["x"] = int(payload["x"])
    if "y" in payload: cur["y"] = int(payload["y"])
    setJsonData(cur)
    return {"x": int(cur["x"]), "y": int(cur["y"])}

# -------- Users --------
@app.get("/api/users")
def list_users(_: str = Depends(require_auth)):
    with UsersSession() as db:
        res = db.execute(select(users).order_by(users.c.id.asc()))
        return [row_to_dict(r) for r in res.fetchall()]

@app.put("/api/users/{user_id}")
async def update_user(user_id: int, request: Request, _: str = Depends(require_auth)):
    """
    Generic update for users.
    If 'approved' changes from False/NULL to True, we:
      - compute stacking with previous active subscription (if any)
      - set period_start accordingly (either now, or previous active_until)
      - set active_until = period_start + plan period
      - set status = 'active'
    """
    raw = await request.json()
    payload: Dict[str, Any] = raw.get("data") if isinstance(raw, dict) and "data" in raw else raw
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be JSON object")

    cols = {c.name: c for c in users.columns}
    IMMUTABLE = {"id", "created_at", "updated_at", "password_hash"}
    clean: Dict[str, Any] = {}

    # Load current row to compare approval / plan
    with UsersSession() as db:
        cur_row = db.execute(select(users).where(users.c.id == user_id)).first()
        if not cur_row:
            raise HTTPException(status_code=404, detail="User not found")
        cur = dict(cur_row._mapping)

    # Type conversions
    for k, v in payload.items():
        if k in IMMUTABLE or k not in cols:
            continue
        coltype = cols[k].type
        if isinstance(coltype, SATime):
            clean[k] = parse_dt(v)
        elif isinstance(coltype, SABool):
            clean[k] = parse_bool(v)
        elif isinstance(coltype, (SAInt, SAFloat)):
            clean[k] = None if v in ("", None) else v
        else:
            clean[k] = v

    # Touch updated_at if exists
    if "updated_at" in cols:
        clean["updated_at"] = dt.datetime.utcnow()

    if not clean:
        raise HTTPException(status_code=400, detail="No updatable fields provided")

    # If approved becomes True now → set period_start/active_until/status (with stacking)
    becoming_approved = None
    if "approved" in clean:
        new_approved = bool(clean["approved"])
        old_approved = bool(cur.get("approved") or False)
        becoming_approved = (not old_approved) and new_approved

    if becoming_approved:
        # Normalize plan for the NEW row being approved
        new_plan = clean.get("plan", cur.get("plan"))
        plan_norm = _normalize_plan(new_plan)
        days = _period_days(plan_norm)

        now_utc = dt.datetime.utcnow().replace(microsecond=0)

        # ---- STACKING LOGIC ----
        # Find the latest APPROVED row for same email (not this row) that has active_until set,
        # and prefer the one with the latest active_until.
        with UsersSession() as db2:
            prev = db2.execute(
                select(users)
                .where(
                    (users.c.email == cur.get("email")) &
                    (users.c.id != user_id) &
                    (users.c.approved == True) &
                    (users.c.active_until.is_not(None))
                )
                .order_by(users.c.active_until.desc())
                .limit(1)
            ).first()

        # Default start: now
        start = now_utc
        if prev:
            prev_end = prev._mapping.get("active_until")
            try:
                prev_end_dt = prev_end if isinstance(prev_end, dt.datetime) else parse_dt(prev_end)
            except Exception:
                prev_end_dt = None

            # If previous subscription still active → start after it ends
            if prev_end_dt and prev_end_dt > now_utc:
                start = prev_end_dt.replace(microsecond=0)

        clean["plan"] = plan_norm
        clean["status"] = "active"
        clean["period_start"] = start
        clean["active_until"] = start + dt.timedelta(days=days)

    # Apply update
    with UsersSession() as db:
        stmt = update(users).where(users.c.id == user_id).values(**clean)
        r = db.execute(stmt)
        if r.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
        db.commit()
        row = db.execute(select(users).where(users.c.id == user_id)).first()
        return row_to_dict(row)

@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, _: str = Depends(require_auth)):
    with UsersSession() as db:
        r = db.execute(delete(users).where(users.c.id == user_id))
        if r.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
        db.commit()
        return {"ok": True, "deleted": user_id}

# -------- DataLog (CRUD + create with assigned='admin' & computed change_pct) --------
@app.get("/api/datalog")
def datalog_list(_: str = Depends(require_auth)):
    with DataLogSession() as db:
        res = db.execute(select(datalog).order_by(datalog.c.id.asc()))
        return [row_to_dict(r) for r in res.fetchall()]

class DataLogCreateIn(BaseModel):
    symbol: str
    signal_type: Optional[str] = None
    entry_time: Optional[str] = None
    entry_price: Optional[float] = None
    exit_time: Optional[str] = None
    exit_price: Optional[float] = None
    change_pct: Optional[float] = None

@app.post("/api/datalog")
def datalog_create(body: DataLogCreateIn, _: str = Depends(require_auth)):
    now = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    change_pct = body.change_pct
    if change_pct is None and body.entry_price is not None and body.exit_price is not None:
        calc = _calc_change_pct(body.entry_price, body.exit_price)
        if calc is not None:
            change_pct = round(calc, 6)

    values = {
        "symbol": (body.symbol or "").strip(),
        "signal_type": (body.signal_type or None),
        "entry_time": (body.entry_time or None),
        "entry_price": (body.entry_price if body.entry_price is not None else None),
        "exit_time": (body.exit_time or None),
        "exit_price": (body.exit_price if body.exit_price is not None else None),
        "change_pct": change_pct,
        "assigned": "admin",
        "created_at": now,
        "updated_at": now,
    }
    if not values["symbol"]:
        raise HTTPException(status_code=400, detail="symbol is required")

    with DataLogSession() as db:
        r = db.execute(insert(datalog).values(**values))
        db.commit()
        new_id = r.lastrowid
        row = db.execute(select(datalog).where(datalog.c.id == new_id)).first()
        return row_to_dict(row)

@app.put("/api/datalog/{row_id}")
async def datalog_update(row_id: int, request: Request, _: str = Depends(require_auth)):
    raw = await request.json()
    payload: Dict[str, Any] = raw.get("data") if isinstance(raw, dict) and "data" in raw else raw
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be JSON object")

    cols = {c.name: c for c in datalog.columns}
    IMMUTABLE = {"id", "created_at"}
    clean: Dict[str, Any] = {}

    for k, v in payload.items():
        if k in IMMUTABLE or k not in cols:
            continue
        coltype = cols[k].type
        if isinstance(coltype, (SAInt, SAFloat)):
            clean[k] = None if v in ("", None) else v
        else:
            clean[k] = v

    # compute change_pct if not provided and prices are available
    if ("change_pct" not in clean or clean["change_pct"] in (None, "")) and (
        ("entry_price" in clean and clean["entry_price"] not in (None, "")) or
        ("exit_price" in clean and clean["exit_price"] not in (None, ""))
    ):
        with DataLogSession() as db:
            cur = db.execute(select(datalog).where(datalog.c.id == row_id)).first()
            if not cur:
                raise HTTPException(status_code=404, detail="Row not found")
            cur_d = row_to_dict(cur)
            ep = clean.get("entry_price", cur_d.get("entry_price"))
            xp = clean.get("exit_price",  cur_d.get("exit_price"))
            calc = _calc_change_pct(ep, xp)
            if calc is not None:
                clean["change_pct"] = round(calc, 6)

    clean["updated_at"] = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    with DataLogSession() as db:
        r = db.execute(update(datalog).where(datalog.c.id == row_id).values(**clean))
        if r.rowcount == 0:
            raise HTTPException(status_code=404, detail="Row not found")
        db.commit()
        row = db.execute(select(datalog).where(datalog.c.id == row_id)).first()
        return row_to_dict(row)

@app.delete("/api/datalog/{row_id}")
def datalog_delete(row_id: int, _: str = Depends(require_auth)):
    with DataLogSession() as db:
        r = db.execute(delete(datalog).where(datalog.c.id == row_id))
        if r.rowcount == 0:
            raise HTTPException(status_code=404, detail="Row not found")
        db.commit()
        return {"ok": True, "deleted": row_id}
