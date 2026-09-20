from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    """Either a finished login, or a request for the second factor."""

    access_token: str | None = None
    token_type: str = "bearer"
    mfa_required: bool = False
    mfa_token: str | None = None


class TwoFactorLoginRequest(BaseModel):
    mfa_token: str
    code: str


class TwoFactorCode(BaseModel):
    code: str


class TwoFactorSetup(BaseModel):
    secret: str
    otpauth_uri: str
    qr_data_uri: str


class TwoFactorEnabled(BaseModel):
    recovery_codes: list[str]
