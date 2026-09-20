from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

# Issued after a correct password when the account has 2FA on. It only proves
# the first factor and can be exchanged for a real access token at /auth/login/2fa.
MFA_PURPOSE = "mfa"
MFA_TOKEN_MINUTES = 5


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))


def _encode(subject: str, expires_in: timedelta, purpose: str | None = None) -> str:
    payload = {"sub": subject, "exp": datetime.now(timezone.utc) + expires_in}
    if purpose:
        payload["purpose"] = purpose
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _decode(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def create_access_token(subject: str) -> str:
    return _encode(subject, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))


def create_mfa_token(subject: str) -> str:
    return _encode(subject, timedelta(minutes=MFA_TOKEN_MINUTES), purpose=MFA_PURPOSE)


def decode_access_token(token: str) -> str | None:
    payload = _decode(token)
    # A first-factor-only token must never work as a login.
    if payload is None or payload.get("purpose"):
        return None
    return payload.get("sub")


def decode_mfa_token(token: str) -> str | None:
    payload = _decode(token)
    if payload is None or payload.get("purpose") != MFA_PURPOSE:
        return None
    return payload.get("sub")
