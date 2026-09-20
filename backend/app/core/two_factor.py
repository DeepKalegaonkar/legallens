"""Authenticator-app two-factor authentication (RFC 6238 TOTP).

Works with Microsoft Authenticator, Google Authenticator, Authy and any other
standard TOTP app: 6 digits, 30-second steps, SHA-1.
"""

import base64
import hashlib
import hmac
import io
import secrets
import time

import pyotp
import qrcode
from qrcode.image.svg import SvgPathImage

ISSUER = "LegalLens"
STEP_SECONDS = 30
RECOVERY_CODE_COUNT = 8


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def qr_data_uri(uri: str) -> str:
    buffer = io.BytesIO()
    qrcode.make(uri, image_factory=SvgPathImage, box_size=10).save(buffer)
    return "data:image/svg+xml;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def verify_code(secret: str, code: str, last_used_step: int | None) -> int | None:
    """Return the accepted time step, or None.

    Allows one step either side for clock drift, and refuses any step that was
    already used so a code can't be replayed.
    """
    code = code.strip().replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return None

    totp = pyotp.TOTP(secret, interval=STEP_SECONDS)
    current = int(time.time()) // STEP_SECONDS
    for step in (current - 1, current, current + 1):
        if last_used_step is not None and step <= last_used_step:
            continue
        if hmac.compare_digest(totp.at(step * STEP_SECONDS), code):
            return step
    return None


def new_recovery_codes() -> list[str]:
    return [f"{secrets.token_hex(3)}-{secrets.token_hex(3)}" for _ in range(RECOVERY_CODE_COUNT)]


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode("utf-8")).hexdigest()
