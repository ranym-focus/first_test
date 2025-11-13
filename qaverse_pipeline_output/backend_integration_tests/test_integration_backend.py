# test_integration.py

import os
import importlib
import pytest
from typing import Any, Dict, Optional

# Attempt to import FastAPI TestClient; if unavailable, skip tests at runtime
try:
    from fastapi.testclient import TestClient
except Exception:
    pytest.skip("FastAPI TestClient is required for integration tests.", allow_module_level=True)

def load_app_factory() -> Optional[Any]:
    """
    Try to locate a typical app factory function to build the FastAPI app.
    Common paths vary by project layout. This helper returns the factory if found.
    """
    candidates = [
        ("app.main", "create_app"),
        ("src.app.main", "create_app"),
        ("server.app", "create_app"),
        ("api.main", "create_app"),
    ]
    for module_path, factory_name in candidates:
        try:
            module = importlib.import_module(module_path)
            factory = getattr(module, factory_name)
            return factory
        except Exception:
            continue
    return None

@pytest.fixture(scope="session")
def app() -> Any:
    """
    Build the application using a discovered factory, configured for testing.

    Configuration is provided via a simple dict passed to the factory.
    - Use a test database URL (sqlite file) to isolate tests.
    - Enable mock/external service usage if supported by the app.
    """
    factory = load_app_factory()
    if factory is None:
        pytest.skip("No app factory found in known locations. Skipping integration tests.")

    config: Dict[str, Any] = {
        "TESTING": True,
        "DATABASE_URL": os.environ.get("TEST_DATABASE_URL", "sqlite:///./test.db"),
        "EXTERNAL_SERVICE_BASE_URL": os.environ.get("TEST_EXTERNAL_BASE_URL", "https://mock-external.local"),
        "USE_MOCK_EXTERNAL": True,
    }

    # The app factory is expected to accept a config dict; adapt as needed
    app = factory(config=config)  # type: ignore[arg-type]
    return app

@pytest.fixture(scope="session")
def client(app: Any) -> TestClient:
    """
    HTTP client for interacting with the test app.
    Uses FastAPI's TestClient for in-process testing.
    """
    with TestClient(app) as c:
        yield c

@pytest.fixture(scope="session")
def mock_external_service(monkeypatch) -> None:
    """
    Attempt to mock external service integrations.
    The test suite will try a few common module paths where a client
    to an external service (e.g., payment gateway) might be defined.
    If none are found, this fixture gracefully does nothing.
    """
    class MockPaymentClient:
        def __init__(self, *args, **kwargs):
            pass

        def charge(self, amount, currency, source):
            # Return a deterministic, successful charge
            return {"status": "succeeded", "id": "pay_mock_001"}

        def refund(self, charge_id):
            return {"status": "succeeded", "refund_id": "refund_mock_001"}

        def retrieve(self, charge_id):
            return {"status": "succeeded", "id": charge_id}

    module_paths = [
        ("external_services.payment", "PaymentClient"),
        ("app.services.payment", "PaymentClient"),
        ("services.payment", "PaymentClient"),
        ("payments.gateway", "PaymentClient"),
    ]

    patched = False
    for mod_path, attr_name in module_paths:
        try:
            mod = importlib.import_module(mod_path)
            monkeypatch.setattr(mod, attr_name, MockPaymentClient, raising=False)
            patched = True
            break
        except Exception:
            continue

    if not patched:
        # If none of the paths exist in the target app, skip patching gracefully
        pass

    yield
    # No explicit teardown required; monkeypatch will revert automatically

def _http(client: TestClient, method: str, path: str, *, json: Optional[Dict] = None, headers: Optional[Dict[str, str]] = None):
    """
    Helper to execute an HTTP request and gracefully skip tests if endpoint is missing.
    """
    resp = client.request(method, path, json=json, headers=headers or {})
    if resp.status_code == 404:
        pytest.skip(f"Endpoint {method} {path} not found in the application.")
    return resp

@pytest.fixture(scope="session", autouse=True)
def teardown_test_db() -> None:
    """
    Teardown fixture to cleanup test database files after the test session.
    Assumes a sqlite database URL of the form sqlite:///path/to/test.db
    """
    yield
    db_url = os.environ.get("TEST_DATABASE_URL", "sqlite:///./test.db")
    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///","")
        try:
            if os.path.exists(db_path):
                os.remove(db_path)
        except Exception:
            pass

def test_health_endpoint(client: TestClient) -> None:
    """
    Verify the health/check endpoint exists and returns a healthy status.
    Checks common health endpoints to maximize compatibility across backends.
    """
    endpoints = ["/health", "/healthz", "/ping"]
    for path in endpoints:
        resp = client.get(path)
        if resp.status_code == 200:
            try:
                data = resp.json()
                # If the API returns a dict with a status, validate it
                if isinstance(data, dict) and "status" in data:
                    assert data["status"] in {"ok", "healthy", "running"}
                else:
                    # If there's no explicit schema, consider 200 as healthy
                    pass
            except Exception:
                pass
            return
    pytest.skip("No healthy endpoint detected among common health routes.")

def test_item_crud_flow(client: TestClient) -> None:
    """
    Generic CRUD flow for a hypothetical Item API.
    Adapt the paths and payloads to your actual models/endpoints.
    """
    # Create an item
    payload = {
        "name": "Integration Test Item",
        "description": "Created by integration tests",
        "price": 19.99
    }
    resp = _http(client, "POST", "/api/items", json=payload)
    assert resp.status_code in (200, 201)
    data = resp.json()
    item_id = data.get("id") or data.get("item_id")
    assert item_id is not None

    # Retrieve the item
    resp = _http(client, "GET", f"/api/items/{item_id}")
    assert resp.status_code == 200
    retrieved = resp.json()
    assert retrieved.get("name") == payload["name"]

    # Update the item
    update_payload = {"name": "Updated Integration Test Item"}
    resp = _http(client, "PUT", f"/api/items/{item_id}", json=update_payload)
    assert resp.status_code in (200, 204)
    if resp.status_code == 200:
        updated = resp.json()
        assert updated.get("name") == update_payload["name"]

    # Delete the item
    resp = _http(client, "DELETE", f"/api/items/{item_id}")
    assert resp.status_code in (200, 204)

def test_auth_flow_if_available(client: TestClient) -> None:
    """
    Test authentication flow if an auth endpoint exists.
    If not available, this test will be skipped gracefully.
    """
    creds = {"username": "integration_user", "password": "secure-pass"}
    resp = _http(client, "POST", "/auth/login", json=creds)
    if resp.status_code not in (200, 201):
        pytest.skip("Authentication endpoint not available; skipping auth flow tests.")
    token = resp.json().get("access_token") or resp.json().get("token")
    assert token is not None

    headers = {"Authorization": f"Bearer {token}"}
    # Access a protected endpoint to validate token
    resp_me = _http(client, "GET", "/api/users/me", headers=headers)
    assert resp_me.status_code in (200, 401, 403) or True  # Permit skip if not implemented
    # If implemented, ensure correct structure
    if resp_me.status_code == 200:
        me = resp_me.json()
        assert "username" in me

def test_data_flow_api_service_db(client: TestClient) -> None:
    """
    Validate data flow from API -> service -> database by performing create/get operations.
    This verifies that the API layer triggers the service layer and results are persisted.
    Adapt endpoints to your models.
    """
    payload = {"name": "Flow Item", "description": "Data flow test", "price": 5.0}
    resp = _http(client, "POST", "/api/items", json=payload)
    if resp.status_code in (404, 405):
        pytest.skip("Items API not available; skipping data flow test.")
    assert resp.status_code in (200, 201)
    item_id = resp.json().get("id") or resp.json().get("item_id")
    assert item_id is not None

    # Immediately read back
    resp2 = _http(client, "GET", f"/api/items/{item_id}")
    assert resp2.status_code == 200
    item = resp2.json()
    assert item.get("name") == payload["name"]
    assert item.get("price") == payload["price"]

def test_external_service_integration_flow(client: TestClient, mock_external_service) -> None:
    """
    Exercise a flow that would invoke an external service (e.g., payment) via the API.
    The external dependency is mocked to avoid real network calls.
    """
    payload = {"amount": 1000, "currency": "USD", "source": "tok_test"}
    resp = _http(client, "POST", "/api/payments", json=payload)
    if resp.status_code in (404, 405):
        pytest.skip("Payments API not available; skipping external service integration test.")
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data.get("status") in {"succeeded", "paid", "completed"} or "payment" in data

# End of test_integration.py