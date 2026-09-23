import itertools

import pytest
from fastapi.testclient import TestClient

from app.main import app

PASSWORD = "hunter2pass"
_counter = itertools.count()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def register(client, email: str | None = None, password: str = PASSWORD):
    email = email or f"auth{next(_counter)}@example.com"
    return email, client.post("/auth/register", json={"email": email, "password": password})


def login(client, email: str, password: str = PASSWORD):
    return client.post("/auth/login", data={"username": email, "password": password})


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_registering_the_same_email_twice_is_rejected(client):
    email, first = register(client)
    assert first.status_code == 201

    second = client.post("/auth/register", json={"email": email, "password": PASSWORD})

    assert second.status_code == 400


def test_registering_with_a_malformed_email_is_rejected(client):
    response = client.post("/auth/register", json={"email": "not-an-email", "password": PASSWORD})

    assert response.status_code == 422


def test_login_with_an_unregistered_email_is_unauthorized(client):
    response = login(client, "nobody-here@example.com")

    assert response.status_code == 401


def test_me_without_a_token_is_unauthorized(client):
    assert client.get("/auth/me").status_code == 401


def test_me_with_a_garbage_token_is_unauthorized(client):
    assert client.get("/auth/me", headers=bearer("not-a-real-token")).status_code == 401


def test_me_with_another_users_token_returns_that_user(client):
    email_a, _ = register(client)
    email_b, _ = register(client)
    token_a = login(client, email_a).json()["access_token"]
    token_b = login(client, email_b).json()["access_token"]

    assert client.get("/auth/me", headers=bearer(token_a)).json()["email"] == email_a
    assert client.get("/auth/me", headers=bearer(token_b)).json()["email"] == email_b


def test_login_lockout_is_scoped_to_the_one_account(client):
    locked_out, _ = register(client)
    other, _ = register(client)

    statuses = [login(client, locked_out, "wrong-password").status_code for _ in range(6)]
    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429

    # A different account is unaffected by another account's lockout.
    assert login(client, other).status_code == 200


def test_login_lockout_key_is_not_case_sensitive_on_email(client):
    email, _ = register(client)

    for _ in range(5):
        login(client, email.upper(), "wrong-password")

    assert login(client, email).status_code == 429


def test_setup_twice_before_enabling_just_issues_a_new_secret(client):
    email, _ = register(client)
    headers = bearer(login(client, email).json()["access_token"])

    first = client.post("/auth/2fa/setup", headers=headers).json()
    second = client.post("/auth/2fa/setup", headers=headers).json()

    assert first["secret"] != second["secret"]


def test_setup_is_blocked_once_2fa_is_already_enabled(client):
    import pyotp

    email, _ = register(client)
    headers = bearer(login(client, email).json()["access_token"])
    secret = client.post("/auth/2fa/setup", headers=headers).json()["secret"]
    client.post("/auth/2fa/enable", headers=headers, json={"code": pyotp.TOTP(secret).now()})

    assert client.post("/auth/2fa/setup", headers=headers).status_code == 409


def test_enabling_without_a_prior_setup_is_rejected(client):
    email, _ = register(client)
    headers = bearer(login(client, email).json()["access_token"])

    response = client.post("/auth/2fa/enable", headers=headers, json={"code": "123456"})

    assert response.status_code == 400
