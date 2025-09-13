# Simple CLI to create users: python -m backend.manage create-user --username NAME --password PASS
from passlib.hash import bcrypt
from sqlalchemy.orm import Session
from .db import Base, engine, SessionLocal
from .models import User
import argparse

def ensure_tables():
    Base.metadata.create_all(bind=engine)

def create_user(username: str, password: str):
    ensure_tables()
    with SessionLocal() as db:
        if db.query(User).filter(User.username == username).first():
            print("User already exists")
            return
        u = User(username=username, password_hash=bcrypt.hash(password), is_active=True)
        db.add(u)
        db.commit()
        print("User created:", username)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")

    cu = sub.add_parser("create-user")
    cu.add_argument("--username", required=True)
    cu.add_argument("--password", required=True)

    args = parser.parse_args()
    if args.cmd == "create-user":
        create_user(args.username, args.password)
    else:
        parser.print_help()
