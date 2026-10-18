"""Admin CLI.  Usage: python -m app.cli create-admin"""
import getpass
import sys

from sqlalchemy import select

from app.db.session import Base, SessionLocal, engine
from app.models import User
from app.security.auth import hash_password, validate_password_strength


def create_admin() -> None:
    Base.metadata.create_all(engine)
    username = input("Admin username [admin]: ").strip() or "admin"
    password = getpass.getpass("Password (min 10 chars): ")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match")
    validate_password_strength(password)
    db = SessionLocal()
    try:
        if db.scalar(select(User).where(User.username == username)):
            sys.exit("User already exists")
        db.add(User(username=username, role="admin", password_hash=hash_password(password)))
        db.commit()
        print(f"Admin '{username}' created")
    finally:
        db.close()


if __name__ == "__main__":
    if sys.argv[1:] == ["create-admin"]:
        create_admin()
    else:
        sys.exit(__doc__)
