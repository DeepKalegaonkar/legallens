from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

SAMPLE = Path(__file__).parent.parent.parent / "samples" / "sample_services_agreement.txt"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def auth_headers(client):
    credentials = {"email": "dashboard@example.com", "password": "hunter2pass"}
    client.post("/auth/register", json=credentials)
    token = client.post("/auth/login", data={"username": credentials["email"], "password": credentials["password"]})
    return {"Authorization": f"Bearer {token.json()['access_token']}"}


def test_new_account_has_no_documents(client, auth_headers):
    assert client.get("/documents", headers=auth_headers).json() == []


def test_list_returns_a_preview_and_risk_counts_for_each_document(client, auth_headers):
    upload = client.post(
        "/documents/upload",
        headers=auth_headers,
        files={"file": ("sample.txt", SAMPLE.read_bytes(), "text/plain")},
    )
    assert upload.status_code == 201

    documents = client.get("/documents", headers=auth_headers).json()

    assert len(documents) == 1
    item = documents[0]
    assert item["filename"] == "sample.txt"
    assert item["clause_count"] == len(upload.json()["clauses"])
    assert item["preview"].startswith("SERVICES AGREEMENT")
    assert len(item["preview"]) <= 280
    assert item["key_findings"]["medium"] > 0
    assert item["key_findings"]["high"] > 0
    assert item["other_flags"] >= 0


def test_documents_are_private_to_their_owner(client, auth_headers):
    other = {"email": "someone.else@example.com", "password": "hunter2pass"}
    client.post("/auth/register", json=other)
    token = client.post("/auth/login", data={"username": other["email"], "password": other["password"]}).json()
    headers = {"Authorization": f"Bearer {token['access_token']}"}

    assert client.get("/documents", headers=headers).json() == []
