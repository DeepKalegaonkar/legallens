import itertools
import time

import pyotp
import pytest
from fastapi.testclient import TestClient

from app.main import app

PASSWORD = "hunter2pass"
_counter = itertools.count()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def make_account(client) -> str:
    email = f"twofactor{next(_counter)}@example.com"
    assert client.post("/auth/register", json={"email": email, "password": PASSWORD}).status_code == 201
    return email


def password_login(client, email: str, password: str = PASSWORD):
    return client.post("/auth/login", data={"username": email, "password": password})


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def account_with_2fa(client):
    """A registered account with 2FA switched on; returns (email, totp, recovery_codes)."""
    email = make_account(client)
    headers = bearer(password_login(client, email).json()["access_token"])
    secret = client.post("/auth/2fa/setup", headers=headers).json()["secret"]
    totp = pyotp.TOTP(secret)
    enabled = client.post("/auth/2fa/enable", headers=headers, json={"code": totp.now()})
    assert enabled.status_code == 200
    return email, totp, enabled.json()["recovery_codes"]


def next_step_code(totp: pyotp.TOTP) -> str:
    """A valid code from the next 30-second step, so it can't collide with the one used to enable 2FA."""
    return totp.at(time.time() + 30)


def test_login_without_2fa_returns_an_access_token_directly(client):
    body = password_login(client, make_account(client)).json()

    assert body["access_token"]
    assert body["mfa_required"] is False


def test_setup_returns_a_secret_a_provisioning_uri_and_a_qr_image(client):
    email = make_account(client)
    headers = bearer(password_login(client, email).json()["access_token"])

    setup = client.post("/auth/2fa/setup", headers=headers).json()

    assert setup["otpauth_uri"].startswith("otpauth://totp/LegalLens:")
    assert f"secret={setup['secret']}" in setup["otpauth_uri"]
    assert "issuer=LegalLens" in setup["otpauth_uri"]
    assert setup["qr_data_uri"].startswith("data:image/svg+xml;base64,")
    assert client.get("/auth/me", headers=headers).json()["two_factor_enabled"] is False


def test_enabling_needs_a_correct_code_and_returns_recovery_codes_once(client):
    email = make_account(client)
    headers = bearer(password_login(client, email).json()["access_token"])
    totp = pyotp.TOTP(client.post("/auth/2fa/setup", headers=headers).json()["secret"])

    assert client.post("/auth/2fa/enable", headers=headers, json={"code": "000000"}).status_code == 400
    enabled = client.post("/auth/2fa/enable", headers=headers, json={"code": totp.now()})

    assert enabled.status_code == 200
    assert len(enabled.json()["recovery_codes"]) == 8
    assert client.get("/auth/me", headers=headers).json()["two_factor_enabled"] is True


def test_password_login_then_asks_for_the_second_factor(client):
    email, totp, _ = account_with_2fa(client)

    body = password_login(client, email).json()

    assert body["mfa_required"] is True
    assert body["access_token"] is None
    assert body["mfa_token"]


def test_the_first_factor_token_is_not_a_login(client):
    email, _, _ = account_with_2fa(client)
    mfa_token = password_login(client, email).json()["mfa_token"]

    assert client.get("/auth/me", headers=bearer(mfa_token)).status_code == 401


def test_correct_code_completes_login_and_cannot_be_replayed(client):
    email, totp, _ = account_with_2fa(client)
    code = next_step_code(totp)

    first = client.post("/auth/login/2fa", json={"mfa_token": password_login(client, email).json()["mfa_token"], "code": code})
    replay = client.post("/auth/login/2fa", json={"mfa_token": password_login(client, email).json()["mfa_token"], "code": code})

    assert first.status_code == 200
    assert client.get("/auth/me", headers=bearer(first.json()["access_token"])).json()["email"] == email
    assert replay.status_code == 401


def test_wrong_code_is_rejected_and_repeated_failures_are_locked_out(client):
    email, totp, _ = account_with_2fa(client)
    mfa_token = password_login(client, email).json()["mfa_token"]

    statuses = [client.post("/auth/login/2fa", json={"mfa_token": mfa_token, "code": "111111"}).status_code for _ in range(6)]

    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429
    assert client.post("/auth/login/2fa", json={"mfa_token": mfa_token, "code": next_step_code(totp)}).status_code == 429


def test_a_recovery_code_works_exactly_once(client):
    email, _, recovery_codes = account_with_2fa(client)

    def sign_in_with(code):
        mfa_token = password_login(client, email).json()["mfa_token"]
        return client.post("/auth/login/2fa", json={"mfa_token": mfa_token, "code": code})

    assert sign_in_with(recovery_codes[0]).status_code == 200
    assert sign_in_with(recovery_codes[0]).status_code == 401
    assert sign_in_with(recovery_codes[1]).status_code == 200


def test_turning_2fa_off_needs_a_valid_code(client):
    email, totp, recovery_codes = account_with_2fa(client)
    mfa_token = password_login(client, email).json()["mfa_token"]
    token = client.post("/auth/login/2fa", json={"mfa_token": mfa_token, "code": next_step_code(totp)}).json()["access_token"]
    headers = bearer(token)

    assert client.post("/auth/2fa/disable", headers=headers, json={"code": "000000"}).status_code == 400
    assert client.post("/auth/2fa/disable", headers=headers, json={"code": recovery_codes[0]}).status_code == 204
    assert password_login(client, email).json()["access_token"]


def test_repeated_wrong_passwords_are_locked_out(client):
    email = make_account(client)

    statuses = [password_login(client, email, "wrong-password").status_code for _ in range(6)]

    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429
