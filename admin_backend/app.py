# admin_backend/app.py
import json
import os
import datetime as dt
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from jose import jwt, JWTError
from dotenv import load_dotenv

from sqlalchemy import (
    create_engine, MetaData, Table, select, update, delete, text as sql_text,
    DateTime as SATime, Boolean as SABool, Integer as SAInt, Float as SAFloat
)
from sqlalchemy.orm import sessionmaker

# ================== ENV ==================
load_dotenv()  # נטען .env מאותה תיקייה שממנה מריצים או מהסביבה

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin")

JWT_SECRET = os.getenv("ADMIN_JWT_SECRET", "CHANGE_ME")
JWT_ALG = "HS256"
JWT_EXPIRE_MIN = int(os.getenv("ADMIN_JWT_EXPIRE_MIN", "240"))
SETTINGS_FILE_PATH = os.getenv("SETTINGS_FILE_PATH", "CHANGE_ME")
print("ofir_SETTINGS_FILE_PATH: ", SETTINGS_FILE_PATH)

# ================== Setting Json get/set (נתונים) ==================

def _resolve_settings_path() -> str:
    """
    פותר את SETTINGS_FILE_PATH כנתיב מוחלט יחסית למיקום של הקובץ הזה (app.py),
    כדי שההרצה לא תהיה תלויה בתקיית ה-Working Directory.
    """
    base_dir = Path(__file__).resolve().parent
    return str((base_dir / SETTINGS_FILE_PATH).resolve())

def getJsonData():
    """קוראת את קובץ ה-JSON, זורקת שגיאה אם אין גישה או שיש קובץ פגום"""
    path = _resolve_settings_path()
    if not os.path.exists(path):
        raise FileNotFoundError(f"JSON file not found at {path}")
    try:
        with open(path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON file: {e}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error reading JSON: {e}")

def setJsonData(data: dict):
    """שומרת נתונים בקובץ JSON, זורקת שגיאה אם משהו משתבש"""
    path = _resolve_settings_path()
    try:
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception as e:
        raise RuntimeError(f"Failed to write JSON file: {e}")

# (הוסר בלוק בדיקות עם הדפסות ושינוי x=99 כדי למנוע תופעות לוואי)

# ================== Users DB (צורה יחידה!) ==================
def _resolve_users_db_url_only_relative_sqlite() -> str:
    """
    מצפה לערך יחיד בסביבה:
      USERS_DB_PATH = 'sqlite:///../backend/Users.db'
    וממיר אותו לנתיב מוחלט ביחס למיקום הקובץ הזה (app.py).
    לא תומך בשום צורה אחרת.
    """
    raw = (os.getenv("USERS_DB_PATH") or "").strip()
    if not raw:
        raise RuntimeError("USERS_DB_PATH is missing in .env (expected 'sqlite:///../backend/Users.db').")
    if not raw.startswith("sqlite:///"):
        raise RuntimeError("USERS_DB_PATH must start with 'sqlite:///' and be relative like '../backend/Users.db'.")

    # שולף את החלק שאחרי 'sqlite:///' ומחשב אותו יחסית לקובץ הזה
    rel = raw[len("sqlite:///"):]  # ../backend/Users.db
    here = Path(__file__).resolve().parent
    abs_path = (here / rel).resolve()
    # ודא שהתיקייה קיימת
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    # SQLite URL עם נתיב מוחלט
    return f"sqlite:///{abs_path.as_posix()}"

USERS_DB_URL = _resolve_users_db_url_only_relative_sqlite()
is_sqlite = USERS_DB_URL.startswith("sqlite:")

engine = create_engine(
    USERS_DB_URL,
    future=True,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if is_sqlite else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
meta = MetaData()

# טבלת users מתוך מסד הנתונים (חייבת כבר להתקיים)
users = Table("users", meta, autoload_with=engine)

# ================== APP ==================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # הפשטות — הגבל בדפדוף לפרודקשן
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

# ================== Schemas ==================
class LoginIn(BaseModel):
    username: str
    password: str

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
        "%Y-%m-%dT%H:%M",    # <input type="datetime-local">
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

def allowed_columns() -> set:
    return set(c.name for c in users.columns)

IMMUTABLE = {"id", "created_at", "updated_at", "password_hash"}
EXCLUDE_IN_RESPONSE = set()  # add secrets if needed

def row_to_dict(row) -> Dict[str, Any]:
    d = dict(row._mapping)
    for k, v in list(d.items()):
        if isinstance(v, dt.datetime):
            d[k] = v.strftime("%Y-%m-%d %H:%M:%S")
    for k in EXCLUDE_IN_RESPONSE:
        d.pop(k, None)
    return d

# ================== Routes ==================
@app.get("/api/health")
def health():
    try:
        with SessionLocal() as db:
            if is_sqlite:
                try:
                    db.execute(sql_text("PRAGMA busy_timeout=5000"))
                except Exception:
                    pass
    except Exception:
        pass
    return {"ok": True, "db": USERS_DB_URL}

@app.post("/api/login")
def login(body: LoginIn):
    if body.username != ADMIN_USER or body.password != ADMIN_PASS:
        raise HTTPException(status_code=401, detail="Bad credentials")
    return {"token": create_token(body.username)}

# -------- Settings endpoints (new) --------
@app.get("/api/settings")
def get_settings(_: str = Depends(require_auth)):
    try:
        data = getJsonData()
        # נוודא שדות בסיס ונהפוך למספרים
        x = int(data.get("x"))
        y = int(data.get("y"))
        return {"x": x, "y": y}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid settings: x/y must be integers")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read settings: {e}")

@app.patch("/api/settings")
async def patch_settings(request: Request, _: str = Depends(require_auth)):
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Body must be JSON object")

        cur = getJsonData()
        if "x" in payload:
            cur["x"] = int(payload["x"])
        if "y" in payload:
            cur["y"] = int(payload["y"])

        # כתיבה ושיבה
        setJsonData(cur)
        return {"x": int(cur["x"]), "y": int(cur["y"])}
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload: x/y must be integers")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {e}")
# ------------------------------------------

@app.get("/api/users")
def list_users(_: str = Depends(require_auth)):
    with SessionLocal() as db:
        res = db.execute(select(users).order_by(users.c.id.asc()))
        rows = [row_to_dict(r) for r in res.fetchall()]
        return rows

@app.put("/api/users/{user_id}")
async def update_user(user_id: int, request: Request, _: str = Depends(require_auth)):
    raw = await request.json()
    payload: Dict[str, Any] = raw.get("data") if isinstance(raw, dict) and "data" in raw else raw
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be JSON object")

    cols = allowed_columns()
    clean: Dict[str, Any] = {}

    for k, v in payload.items():
        if k in IMMUTABLE:
            continue
        if k not in cols:
            continue

        coltype = users.c[k].type
        # DateTime fields
        if isinstance(coltype, SATime):
            clean[k] = parse_dt(v)
        # Booleans
        elif isinstance(coltype, SABool):
            clean[k] = parse_bool(v)
        # Numeric -> allow NULL if empty
        elif isinstance(coltype, (SAInt, SAFloat)):
            clean[k] = None if v in ("", None) else v
        # Default: keep value as-is (strings, etc.)
        else:
            clean[k] = v

    # תמיד נעדכן updated_at בצד שרת
    if "updated_at" in cols:
        clean["updated_at"] = dt.datetime.utcnow()

    if not clean:
        raise HTTPException(status_code=400, detail="No updatable fields provided")

    try:
        with SessionLocal() as db:
            stmt = update(users).where(users.c.id == user_id).values(**clean)
            r = db.execute(stmt)
            if r.rowcount == 0:
                raise HTTPException(status_code=404, detail="User not found")
            db.commit()
            row = db.execute(select(users).where(users.c.id == user_id)).first()
            return row_to_dict(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Update failed: {type(e).__name__}: {e}")

@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, _: str = Depends(require_auth)):
    with SessionLocal() as db:
        r = db.execute(delete(users).where(users.c.id == user_id))
        if r.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
        db.commit()
        return {"ok": True, "deleted": user_id}
