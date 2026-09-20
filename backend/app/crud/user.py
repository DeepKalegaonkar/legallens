import hmac

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.core.two_factor import hash_recovery_code
from app.models.user import User


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def create_user(db: Session, email: str, password: str) -> User:
    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def set_pending_totp(db: Session, user: User, secret: str) -> None:
    user.totp_secret = secret
    user.totp_enabled = False
    user.totp_last_step = None
    user.recovery_code_hashes = None
    db.commit()


def enable_totp(db: Session, user: User, step: int, recovery_codes: list[str]) -> None:
    user.totp_enabled = True
    user.totp_last_step = step
    user.recovery_code_hashes = [hash_recovery_code(code) for code in recovery_codes]
    db.commit()


def disable_totp(db: Session, user: User) -> None:
    user.totp_secret = None
    user.totp_enabled = False
    user.totp_last_step = None
    user.recovery_code_hashes = None
    db.commit()


def record_totp_step(db: Session, user: User, step: int) -> None:
    user.totp_last_step = step
    db.commit()


def consume_recovery_code(db: Session, user: User, code: str) -> bool:
    """Accept a recovery code once; it is removed so it can't be used again."""
    candidate = hash_recovery_code(code)
    remaining = list(user.recovery_code_hashes or [])
    for stored in remaining:
        if hmac.compare_digest(stored, candidate):
            remaining.remove(stored)
            user.recovery_code_hashes = remaining
            db.commit()
            return True
    return False
