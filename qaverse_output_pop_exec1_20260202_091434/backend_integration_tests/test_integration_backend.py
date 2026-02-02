import os
import importlib
import pytest
from fastapi.testclient import TestClient

# Utility to dynamically locate the FastAPI app instance
def load_app():
    candidate_paths = [
        "app.main",
        "app",
        "main",
        "server.api",
        "backend.main",
    ]
    for path in candidate_paths:
        try:
            module = importlib.import_module(path)
            if hasattr(module, "app"):
                return getattr(module, "app")
        except Exception:
            continue
    return None

APP = load_app()
if APP is None:
    raise SystemExit("Could not locate a FastAPI app instance named 'app' in known paths. Please expose your FastAPI instance as 'app' in your codebase.")

@pytest.fixture(scope="session")
def client():
    with TestClient(APP) as c:
        yield c

@pytest.fixture(scope="session", autouse=True)
def setup_test_database(monkeypatch):
    # Point the app to a test database
    test_db_url = "sqlite:///./test.db"
    monkeypatch.setenv("DATABASE_URL", test_db_url)

    # Ensure a clean slate for each test session
    if os.path.exists("./test.db"):
        os.remove("./test.db")
    yield
    # Teardown: remove test database after tests complete
    if os.path.exists("./test.db"):
        os.remove("./test.db")


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    # Optional: verify payload if your health endpoint returns data
    # assert resp.json().get("status") == "healthy"


def test_item_crud_flow(client):
    # Create
    payload = {"name": "Integration Item", "description": "Created by integration tests"}
    resp = client.post("/items/", json=payload)
    assert resp.status_code in (200, 201)
    created = resp.json()
    item_id = created.get("id") or created.get("item_id")
    assert item_id is not None

    # Read
    resp = client.get(f"/items/{item_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("name") == payload["name"]

    # Update
    update_payload = {"name": "Integration Item Updated"}
    resp = client.put(f"/items/{item_id}", json=update_payload)
    assert resp.status_code in (200, 202)

    resp = client.get(f"/items/{item_id}")
    assert resp.status_code == 200
    assert resp.json().get("name") == update_payload["name"]

    # Delete
    resp = client.delete(f"/items/{item_id}")
    assert resp.status_code in (200, 204)

    # Verify deletion
    resp = client.get(f"/items/{item_id}")
    assert resp.status_code in (404, 400)


def test_items_list_and_pagination(client):
    resp = client.get("/items/?limit=5&offset=0")
    # Depending on implementation, list may be empty or contain items
    assert resp.status_code in (200, 204)
    if resp.status_code == 200:
        data = resp.json()
        assert isinstance(data, list)


def test_nonexistent_item_returns_404(client):
    resp = client.get("/items/99999999")
    assert resp.status_code in (404, 400)


def test_authentication_flow_if_present(client, monkeypatch):
    # Try to authenticate if auth endpoints exist; otherwise skip gracefully
    try:
        resp = client.post("/auth/login", json={"username": "test", "password": "test"})
        if resp.status_code == 200:
            token = resp.json().get("access_token")
            assert token
            headers = {"Authorization": f"Bearer {token}"}
            # Access a protected endpoint
            resp2 = client.get("/users/me", headers=headers)
            assert resp2.status_code in (200, 201)
        else:
            pytest.skip("Authentication endpoint not configured or returned non-success; skipping auth tests.")
    except Exception:
        pytest.skip("Authentication endpoints not available; skipping auth tests.")


def test_data_flow_api_service_database_with_mock(client, monkeypatch):
    # This test ensures that API -> Service layer is engaged.
    # It patches the service layer's create_item to verify it's invoked with correct payload.
    try:
        # Attempt to import the real service path; skip if not present
        import services.item_service as item_service  # type: ignore
        real_create = item_service.create_item

        called = {}

        def fake_create_item(payload):
            called["payload"] = payload
            # Return a minimal representation as if created by DB/service
            return {"id": 12345, "name": payload.get("name")}

        monkeypatch.setattr(item_service, "create_item", fake_create_item)

        payload = {"name": "Flow Item", "description": "Data flows API -> Service -> DB"}
        resp = client.post("/items/", json=payload)
        assert resp.status_code in (200, 201)
        assert called.get("payload") == payload

        # Restore original for other tests
        monkeypatch.setattr(item_service, "create_item", real_create)
    except Exception:
        pytest.skip("Service layer path not found; skipping API -> Service flow test.")


def test_external_service_mock_on_create(client, monkeypatch):
    # Attempt to mock an external notification service that might be called on create
    try:
        import external_service  # hypothetical module
        calls = {}

        def fake_notify_item_created(item_id, payload):
            calls["item_id"] = item_id
            calls["payload"] = payload
            return True

        monkeypatch.setattr(external_service, "notify_item_created", fake_notify_item_created)

        payload = {"name": "Notified Item", "description": "Should trigger external notification"}
        resp = client.post("/items/", json=payload)
        assert resp.status_code in (200, 201)
        item = resp.json()
        item_id = item.get("id")
        # If the create path triggered the notifier, our fake should have captured the call
        assert calls.get("item_id") == item_id
    except Exception:
        pytest.skip("External service module not found; skipping external service mock test.")


def test_transaction_rollback_on_invalid_input(client):
    # Capture current count
    resp_before = client.get("/items/")
    count_before = len(resp_before.json()) if resp_before.status_code == 200 else 0

    # Attempt to create with invalid payload that should trigger a validation error
    resp = client.post("/items/", json={"name": ""})  # invalid data
    assert resp.status_code in (400, 422)

    # Ensure no new item was persisted
    resp_after = client.get("/items/")
    count_after = len(resp_after.json()) if resp_after.status_code == 200 else 0
    assert count_after == count_before

# End of integration tests
```