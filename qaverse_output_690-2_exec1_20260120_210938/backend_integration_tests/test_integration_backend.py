# tests/test_integration.py

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Adjust the import paths to your actual project structure
from app.main import app
from app.database import Base, get_db
from app import models

# Setup a dedicated test SQLite database file
TEST_DB_FILE = "./test_integration.db"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_FILE}"

# Create engine and session factory for tests
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Cleanup after the entire test session
@pytest.fixture(scope="session", autouse=True)
def cleanup_test_db():
    yield
    if os.path.exists(TEST_DB_FILE):
        os.remove(TEST_DB_FILE)


# Create all tables and provide a clean DB session per test
@pytest.fixture(scope="function")
def db_session():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Provide a test client with the app's dependencies overridden for the test DB
@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_full_api_flow_api_service_db_and_auth(client, db_session, monkeypatch):
    # 1) Register a new user
    reg_resp = client.post("/auth/register", json={
        "email": "integration@example.com",
        "password": "secret",
        "name": "Integration User"
    })
    assert reg_resp.status_code in (200, 201)

    # 2) Login to obtain access token
    login_resp = client.post("/auth/login", json={
        "email": "integration@example.com",
        "password": "secret"
    })
    assert login_resp.status_code == 200
    token = login_resp.json().get("access_token") or login_resp.json().get("token")
    assert token is not None
    headers = {"Authorization": f"Bearer {token}"}

    # 3) Create a new item
    create_item_resp = client.post("/items", json={
        "name": "Integration Item",
        "price": 19.99
    }, headers=headers)
    assert create_item_resp.status_code in (200, 201)
    item_id = create_item_resp.json().get("id") or create_item_resp.json().get("item_id")
    assert item_id is not None

    # 4) Retrieve the item
    get_item_resp = client.get(f"/items/{item_id}", headers=headers)
    assert get_item_resp.status_code == 200
    assert get_item_resp.json().get("name") == "Integration Item"

    # 5) Update the item
    update_item_resp = client.put(f"/items/{item_id}", json={
        "name": "Integration Item Updated",
        "price": 24.99
    }, headers=headers)
    assert update_item_resp.status_code == 200
    assert update_item_resp.json().get("name") == "Integration Item Updated"

    # 6) Delete the item
    delete_item_resp = client.delete(f"/items/{item_id}", headers=headers)
    assert delete_item_resp.status_code in (200, 204)

    # 7) Data flow checks: ensure user exists in DB and item is removed
    user_in_db = db_session.query(models.User).filter_by(email="integration@example.com").first()
    assert user_in_db is not None

    item_in_db = db_session.query(models.Item).filter_by(id=item_id).first()
    assert item_in_db is None  # Deleted successfully


def test_api_auth_requirements_and_protected_endpoint(client, db_session):
    # Access protected endpoint without token should fail
    resp_unauth = client.get("/users/me")
    assert resp_unauth.status_code in (401, 403)

    # Register and login a user
    client.post("/auth/register", json={
        "email": "authflow@example.com",
        "password": "secret",
        "name": "Auth Flow"
    })
    login_resp = client.post("/auth/login", json={
        "email": "authflow@example.com",
        "password": "secret"
    })
    assert login_resp.status_code == 200
    token = login_resp.json().get("access_token") or login_resp.json().get("token")
    assert token is not None

    # Access protected endpoint with token
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/users/me", headers=headers)
    assert resp.status_code == 200
    assert "email" in resp.json()


def test_service_layer_interaction_with_mock(monkeypatch, client, db_session):
    # Mock the service layer's item creation to verify API -> Service interaction
    calls = {"create_item": 0}

    def fake_create_item(payload, db):
        calls["create_item"] += 1
        return {"id": 9999, "name": payload.get("name"), "price": payload.get("price")}

    # Path should match your actual service module path
    monkeypatch.setattr("app.services.item_service.create_item", fake_create_item)

    # Prepare authenticated user
    client.post("/auth/register", json={
        "email": "svc@example.com",
        "password": "secret",
        "name": "Svc User"
    })
    login_resp = client.post("/auth/login", json={
        "email": "svc@example.com",
        "password": "secret"
    })
    token = login_resp.json().get("access_token") or login_resp.json().get("token")
    headers = {"Authorization": f"Bearer {token}"}

    # Trigger item creation
    client.post("/items", json={"name": "Mocked Service Item", "price": 5.0}, headers=headers)

    # Verify that the service layer was invoked exactly once
    assert calls["create_item"] == 1


def test_external_service_mocking_on_registration(monkeypatch, client, db_session):
    # Mock an external email service used on registration
    was_called = {"sent": False}

    def fake_send_welcome_email(email, name):
        was_called["sent"] = True
        return True

    # Path should match your actual external service module path
    monkeypatch.setattr("app.services.email_sender.send_welcome_email", fake_send_welcome_email)

    # Register a user and verify the external service was invoked
    client.post("/auth/register", json={
        "email": "external@example.com",
        "password": "secret",
        "name": "External"
    })
    assert was_called["sent"] is True


def test_data_flow_api_to_db_consistency(client, db_session):
    # Register and login
    client.post("/auth/register", json={
        "email": "flowdb@example.com",
        "password": "secret",
        "name": "Flow DB"
    })
    login_resp = client.post("/auth/login", json={
        "email": "flowdb@example.com",
        "password": "secret"
    })
    token = login_resp.json().get("access_token") or login_resp.json().get("token")
    headers = {"Authorization": f"Bearer {token}"}

    # Create an item via API
    client.post("/items", json={"name": "Flow Item", "price": 7.5}, headers=headers)

    # Verify the item exists in DB with correct data
    item_in_db = db_session.query(models.Item).filter_by(name="Flow Item").first()
    assert item_in_db is not None
    assert float(item_in_db.price) == 7.5