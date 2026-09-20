from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limit import login_limiter, two_factor_limiter
from app.core.security import (
    create_access_token,
    create_mfa_token,
    decode_mfa_token,
    verify_password,
)
from app.core.two_factor import (
    new_recovery_codes,
    new_secret,
    provisioning_uri,
    qr_data_uri,
    verify_code,
)
from app.crud.user import (
    consume_recovery_code,
    create_user,
    disable_totp,
    enable_totp,
    get_user_by_email,
    record_totp_step,
    set_pending_totp,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginResponse,
    Token,
    TwoFactorCode,
    TwoFactorEnabled,
    TwoFactorLoginRequest,
    TwoFactorSetup,
)
from app.schemas.user import UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _accept_second_factor(db: Session, user: User, code: str) -> bool:
    """A current authenticator code, or (once) an unused recovery code."""
    if user.totp_secret:
        step = verify_code(user.totp_secret, code, user.totp_last_step)
        if step is not None:
            record_totp_step(db, user, step)
            return True
    return consume_recovery_code(db, user, code)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    if get_user_by_email(db, payload.email) is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    return create_user(db, email=payload.email, password=payload.password)


@router.post("/login", response_model=LoginResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> LoginResponse:
    limiter_key = f"login:{form_data.username.lower()}"
    login_limiter.check(limiter_key)

    user = get_user_by_email(db, form_data.username)
    if user is None or not verify_password(form_data.password, user.hashed_password):
        login_limiter.record(limiter_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    login_limiter.reset(limiter_key)
    if user.totp_enabled:
        return LoginResponse(mfa_required=True, mfa_token=create_mfa_token(user.email))
    return LoginResponse(access_token=create_access_token(subject=user.email))


@router.post("/login/2fa", response_model=Token)
def login_second_factor(payload: TwoFactorLoginRequest, db: Session = Depends(get_db)) -> Token:
    email = decode_mfa_token(payload.mfa_token)
    user = get_user_by_email(db, email) if email else None
    if user is None or not user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Your sign-in expired. Please log in again."
        )

    limiter_key = f"2fa:{user.id}"
    two_factor_limiter.check(limiter_key)
    if not _accept_second_factor(db, user, payload.code):
        two_factor_limiter.record(limiter_key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="That code isn't right. Try again.")

    two_factor_limiter.reset(limiter_key)
    return Token(access_token=create_access_token(subject=user.email))


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/2fa/setup", response_model=TwoFactorSetup)
def setup_two_factor(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TwoFactorSetup:
    if current_user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-factor authentication is already on")

    secret = new_secret()
    set_pending_totp(db, current_user, secret)
    uri = provisioning_uri(secret, current_user.email)
    return TwoFactorSetup(secret=secret, otpauth_uri=uri, qr_data_uri=qr_data_uri(uri))


@router.post("/2fa/enable", response_model=TwoFactorEnabled)
def enable_two_factor(
    payload: TwoFactorCode, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> TwoFactorEnabled:
    if current_user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-factor authentication is already on")
    if not current_user.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Start the setup first")

    limiter_key = f"2fa:{current_user.id}"
    two_factor_limiter.check(limiter_key)
    step = verify_code(current_user.totp_secret, payload.code, None)
    if step is None:
        two_factor_limiter.record(limiter_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="That code didn't match. Check the app and try again."
        )

    two_factor_limiter.reset(limiter_key)
    recovery_codes = new_recovery_codes()
    enable_totp(db, current_user, step, recovery_codes)
    return TwoFactorEnabled(recovery_codes=recovery_codes)


@router.post("/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
def disable_two_factor(
    payload: TwoFactorCode, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Response:
    if not current_user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-factor authentication is off")

    limiter_key = f"2fa:{current_user.id}"
    two_factor_limiter.check(limiter_key)
    if not _accept_second_factor(db, current_user, payload.code):
        two_factor_limiter.record(limiter_key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That code isn't right. Try again.")

    two_factor_limiter.reset(limiter_key)
    disable_totp(db, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
