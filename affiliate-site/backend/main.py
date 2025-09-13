# Comments in English as requested.
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt, JWTError
from pydantic import BaseModel
from dotenv import load_dotenv
from passlib.hash import bcrypt
from sqlalchemy.orm import Session

from .db import SessionLocal, engine, Base
from .models import User

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
ALGO = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "43200"))
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5180").split(",") if o.strip()]

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Affiliates API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserOut(BaseModel):
    username: str
    class Config:
        from_attributes = True

class DashboardData(BaseModel):
    message: str
    user: UserOut

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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def bearer_from_header(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startsWith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return authorization.split(" ", 1)[1].strip()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    if not form.username or not form.password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    user = db.query(User).filter(User.username == form.username).first()
    if not user or not user.is_active or not bcrypt.verify(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(subject=user.username)
    return Token(access_token=token)

@app.get("/me", response_model=UserOut)
def me(authorization: Optional[str] = None, db: Session = Depends(get_db)):
    token = bearer_from_header(authorization)
    username = decode_access_token(token)
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return UserOut(username=user.username)

@app.get("/dashboard/data", response_model=DashboardData)
def dashboard_data(authorization: Optional[str] = None, db: Session = Depends(get_db)):
    token = bearer_from_header(authorization)
    username = decode_access_token(token)
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return DashboardData(message="Connected - affiliate dashboard placeholder", user=UserOut(username=user.username))
