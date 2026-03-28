"""
Integration tests for SafeSave API.
Uses an in-memory SQLite DB — no real PayHero calls are made (patched).
Run with:  pytest tests/ -v
"""
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_safesave.db")
os.environ.setdefault("PAYHERO_API_KEY", "test-key")
os.environ.setdefault("PAYHERO_CHANNEL_ID", "9999")

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from main import app, Base, engine

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_db():
    """Recreate all tables before each test for isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def registered_user(client):
    payload = {
        "email": "test@safesave.com",
        "phone": "0712345678",
        "id_number": "12345678",
        "password": "Secure123",
        "confirm_password": "Secure123",
    }
    r = client.post("/register", json=payload)
    assert r.status_code == 201
    return payload


@pytest.fixture
def auth_headers(client, registered_user):
    r = client.post("/login", json={
        "email": registered_user["email"],
        "password": registered_user["password"],
    })
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Health ─────────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("healthy", "degraded")
    assert "environment" in data


def test_docs_available(client):
    r = client.get("/docs")
    assert r.status_code == 200


# ── Register ───────────────────────────────────────────────────────────────────

def test_register_success(client):
    r = client.post("/register", json={
        "email": "new@safesave.com",
        "phone": "0799999999",
        "id_number": "99999999",
        "password": "Strong1pass",
        "confirm_password": "Strong1pass",
    })
    assert r.status_code == 201
    assert r.json()["email"] == "new@safesave.com"


def test_register_duplicate_email(client, registered_user):
    r = client.post("/register", json={
        "email": registered_user["email"],
        "phone": "0799000000",
        "id_number": "00000001",
        "password": "Strong1pass",
        "confirm_password": "Strong1pass",
    })
    assert r.status_code == 400
    assert "Email" in r.json()["detail"]


def test_register_weak_password(client):
    r = client.post("/register", json={
        "email": "weak@safesave.com",
        "phone": "0711111111",
        "id_number": "11111111",
        "password": "weakpass",
        "confirm_password": "weakpass",
    })
    assert r.status_code == 422


def test_register_password_mismatch(client):
    r = client.post("/register", json={
        "email": "mismatch@safesave.com",
        "phone": "0722222222",
        "id_number": "22222222",
        "password": "Strong1pass",
        "confirm_password": "Different1pass",
    })
    assert r.status_code == 422


# ── Login ──────────────────────────────────────────────────────────────────────

def test_login_success(client, registered_user):
    r = client.post("/login", json={
        "email": registered_user["email"],
        "password": registered_user["password"],
    })
    assert r.status_code == 200
    assert "access_token" in r.json()
    assert r.json()["token_type"] == "bearer"


def test_login_wrong_password(client, registered_user):
    r = client.post("/login", json={
        "email": registered_user["email"],
        "password": "WrongPass1",
    })
    assert r.status_code == 401


def test_login_unknown_email(client):
    r = client.post("/login", json={
        "email": "nobody@safesave.com",
        "password": "Whatever1",
    })
    assert r.status_code == 401


# ── Profile ────────────────────────────────────────────────────────────────────

def test_get_profile(client, auth_headers):
    r = client.get("/profile", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["email"] == "test@safesave.com"


def test_profile_no_token(client):
    r = client.get("/profile")
    assert r.status_code == 401


# ── Savings ────────────────────────────────────────────────────────────────────

def test_create_savings(client, auth_headers):
    r = client.post("/savings", json={"target_amount": 5000, "duration_days": 30}, headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["target_amount"] == 5000


def test_create_duplicate_savings(client, auth_headers):
    # Multiple goals are now allowed — second one should also succeed
    client.post("/savings", json={"target_amount": 5000, "duration_days": 30}, headers=auth_headers)
    r = client.post("/savings", json={"target_amount": 3000, "duration_days": 10}, headers=auth_headers)
    assert r.status_code == 201


def test_savings_status_no_goal(client, auth_headers):
    r = client.get("/savings/status", headers=auth_headers)
    assert r.status_code == 200
    assert "No active" in r.json()["message"]


def test_savings_status_with_goal(client, auth_headers):
    client.post("/savings", json={"target_amount": 5000, "duration_days": 30}, headers=auth_headers)
    r = client.get("/savings/status", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["target_amount"] == 5000
    assert r.json()["progress_percent"] == 0.0


# ── Deposit ────────────────────────────────────────────────────────────────────

def test_deposit_no_savings(client, auth_headers):
    r = client.post("/deposit", json={"amount": 500, "phone": "0712345678"}, headers=auth_headers)
    assert r.status_code == 400
    assert "savings goal" in r.json()["detail"].lower()


def test_deposit_success(client, auth_headers):
    s = client.post("/savings", json={"target_amount": 5000, "duration_days": 30}, headers=auth_headers)
    savings_id = s.json()["id"]
    mock_result = {"success": True, "status": "QUEUED", "reference": "TEST-REF-001", "CheckoutRequestID": "ws_CO_test"}
    with patch("main.pay_hero.initiate_payment", return_value=mock_result):
        r = client.post("/deposit", json={"savings_id": savings_id, "amount": 500, "phone": "0712345678"}, headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["status"] == "pending"
    assert r.json()["payhero_reference"] == "TEST-REF-001"


def test_deposit_exceeds_target(client, auth_headers):
    s = client.post("/savings", json={"target_amount": 1000, "duration_days": 30}, headers=auth_headers)
    savings_id = s.json()["id"]
    mock_result = {"success": True, "status": "QUEUED", "reference": "REF-A"}
    with patch("main.pay_hero.initiate_payment", return_value=mock_result):
        r = client.post("/deposit", json={"savings_id": savings_id, "amount": 2000, "phone": "0712345678"}, headers=auth_headers)
    assert r.status_code == 400
    assert "exceed" in r.json()["detail"].lower()


def test_deposit_payhero_failure(client, auth_headers):
    s = client.post("/savings", json={"target_amount": 5000, "duration_days": 30}, headers=auth_headers)
    savings_id = s.json()["id"]
    with patch("main.pay_hero.initiate_payment", return_value={"error": "Network timeout"}):
        r = client.post("/deposit", json={"savings_id": savings_id, "amount": 500, "phone": "0712345678"}, headers=auth_headers)
    assert r.status_code == 400
    assert "failed" in r.json()["detail"].lower()


# ── Withdraw ───────────────────────────────────────────────────────────────────

def test_withdraw_no_savings(client, auth_headers):
    r = client.post("/withdraw", json={"savings_id": 9999, "phone": "0712345678"}, headers=auth_headers)
    assert r.status_code == 404


def test_withdraw_target_not_reached(client, auth_headers):
    s = client.post("/savings", json={"target_amount": 5000, "duration_days": 30}, headers=auth_headers)
    savings_id = s.json()["id"]
    r = client.post("/withdraw", json={"savings_id": savings_id, "phone": "0712345678"}, headers=auth_headers)
    assert r.status_code == 400
    assert "not reached" in r.json()["detail"].lower()


# ── Webhook ────────────────────────────────────────────────────────────────────

def test_webhook_success_flow(client, auth_headers):
    """Full flow: create savings → deposit → webhook SUCCESS → savings updated"""
    s = client.post("/savings", json={"target_amount": 5000, "duration_days": 30}, headers=auth_headers)
    savings_id = s.json()["id"]

    mock_result = {"success": True, "status": "QUEUED", "reference": "REF-WH-001"}
    with patch("main.pay_hero.initiate_payment", return_value=mock_result):
        dep = client.post("/deposit", json={"savings_id": savings_id, "amount": 500, "phone": "0712345678"}, headers=auth_headers)
    assert dep.status_code == 201
    ext_ref = dep.json()["external_reference"]

    webhook_payload = {
        "status": True,
        "response": {
            "ExternalReference": ext_ref,
            "Status": "Success",
            "MpesaReceiptNumber": "SAE3YULR0Y",
            "Amount": 500,
            "Phone": "+254712345678",
            "ResultCode": 0,
            "ResultDesc": "The service request is processed successfully.",
            "CheckoutRequestID": "ws_CO_test",
        },
    }
    r = client.post("/webhooks/payhero", json=webhook_payload)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    # Check savings updated via /savings/{id}
    status_r = client.get(f"/savings/{savings_id}", headers=auth_headers)
    assert status_r.json()["current_amount"] == 500.0


def test_webhook_failed_payment(client, auth_headers):
    s = client.post("/savings", json={"target_amount": 5000, "duration_days": 30}, headers=auth_headers)
    savings_id = s.json()["id"]
    mock_result = {"success": True, "status": "QUEUED", "reference": "REF-WH-002"}
    with patch("main.pay_hero.initiate_payment", return_value=mock_result):
        dep = client.post("/deposit", json={"savings_id": savings_id, "amount": 500, "phone": "0712345678"}, headers=auth_headers)
    ext_ref = dep.json()["external_reference"]

    webhook_payload = {
        "status": False,
        "response": {
            "ExternalReference": ext_ref,
            "Status": "Failed",
            "ResultCode": 1032,
            "ResultDesc": "Request cancelled by user.",
            "Amount": 500,
            "Phone": "+254712345678",
            "CheckoutRequestID": "ws_CO_test2",
        },
    }
    r = client.post("/webhooks/payhero", json=webhook_payload)
    assert r.status_code == 200

    txns = client.get("/transactions", headers=auth_headers)
    statuses = [t["status"] for t in txns.json()["transactions"]]
    assert "failed" in statuses


def test_webhook_unknown_reference(client):
    r = client.post("/webhooks/payhero", json={
        "status": True,
        "response": {"ExternalReference": "NONEXISTENT-REF", "Status": "Success", "ResultCode": 0},
    })
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Transactions ───────────────────────────────────────────────────────────────

def test_get_transactions_empty(client, auth_headers):
    r = client.get("/transactions", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["total"] == 0


# ── Customer Care ──────────────────────────────────────────────────────────────

def test_customer_care(client):
    r = client.get("/customer-care")
    assert r.status_code == 200
    assert "email" in r.json()
    assert "phone" in r.json()


# ── Metrics ────────────────────────────────────────────────────────────────────

def test_metrics(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    data = r.json()
    assert "total_users" in data
    assert "transactions" in data
