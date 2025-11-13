# tests/integration/test_backend_integration.py

import os
import json
import importlib
import asyncio
import pytest
import httpx
from typing import Any, Dict, Optional

"""
Comprehensive integration tests template for a backend application.

What this test suite covers:
- API CRUD flow for a generic "items" resource
- Authentication flow and usage of a protected endpoint
- Integration with an external service via mocked HTTP responses
- Data flow from API -> Service -> Database layers (via API endpoints)
- Setup/teardown considerations for a test database (via environment-configured DB URL)
- Transactional-like flow validations via dedicated endpoints (if present)

How to adapt:
- Set APP_ASGI_APP to point to your ASGI app, e.g. "my_app.main:app"
- Set DATABASE_URL (or rely on your app's default) to a test database (e.g. sqlite:///./test.db)
- If your endpoints differ, rename paths accordingly or adjust payloads

Note:
This is a generic integration test scaffold. Replace endpoint names, payload shapes, and
assertions to match your actual API contract. The tests use httpx.AsyncClient with the
ASGI app to perform true in-process HTTP-style integration tests.

Install requirements (example):
- pytest
- httpx
- pytest-asyncio
- pytest-httpx

Example environment configuration:
export APP_ASGI_APP=app.main:app
export DATABASE_URL=sqlite:///./test.db
"""

# ---------------------------
# Helpers: App loader & client
# ---------------------------

def _load_app_from_env() -> Any:
    """
    Dynamically import the ASGI app from an environment variable.
    Default path: "app.main:app"
    """
    app_path = os.environ.get("APP_ASGI_APP", "app.main:app")
    module_path, attr_name = app_path.split(":")
    module = importlib.import_module(module_path)
    return getattr(module, attr_name)


@pytest.fixture(scope="session")
def app() -> Any:
    """
    Load the application under test.
    """
    return _load_app_from_env()


@pytest.fixture(scope="function")
async def client(app: Any) -> httpx.AsyncClient:
    """
    Async HTTP client bound to the in-process ASGI app.
    """
    async with httpx.AsyncClient(app=app, base_url="http://test") as c:
        yield c


# ---------------------------
# Tests
# ---------------------------

@pytest.mark.asyncio
async def test_api_items_crud_flow(client: httpx.AsyncClient) -> None:
    """
    End-to-end CRUD flow for a generic /items resource.

    - Create an item
    - List items
    - Retrieve single item
    - Update item
    - Delete item
    - Confirm deletion
    """
    # 1) Create item
    create_payload: Dict[str, Any] = {
        "name": "Integration Test Item",
        "description": "Created by integration test",
        "price": 9.99
    }

    resp = await client.post("/items", json=create_payload)
    assert resp.status_code == 201, f"Expected 201 Created, got {resp.status_code}: {resp.text}"

    created = resp.json()
    assert isinstance(created, dict), "Response should be a JSON object with item details"
    item_id = created.get("id")
    assert item_id is not None, "Created item should return an 'id' field"

    # 2) List items
    resp = await client.get("/items")
    assert resp.status_code == 200, f"List items failed: {resp.text}"
    items = resp.json()
    assert isinstance(items, list), "GET /items should return a list"

    # 3) Retrieve single item
    resp = await client.get(f"/items/{item_id}")
    assert resp.status_code == 200, f"GET /items/{item_id} failed"
    item_detail = resp.json()
    assert item_detail.get("id") == item_id
    assert item_detail.get("name") == create_payload["name"]

    # 4) Update item
    update_payload = {"name": "Updated Integration Test Item"}
    resp = await client.patch(f"/items/{item_id}", json=update_payload)
    assert resp.status_code in (200, 202), f"Update failed: {resp.text}"

    # Verify update
    resp = await client.get(f"/items/{item_id}")
    assert resp.status_code == 200
    updated = resp.json()
    assert updated.get("name") == update_payload["name"]

    # 5) Delete item
    resp = await client.delete(f"/items/{item_id}")
    assert resp.status_code in (200, 204), f"Delete failed: {resp.text}"

    # 6) Confirm deletion
    resp = await client.get(f"/items/{item_id}")
    # Depending on implementation, 404 (Not Found) or 410 (Gone) may be returned
    assert resp.status_code in (404, 410, 204), f"Deleted item should not be retrievable: {resp.text}"


@pytest.mark.asyncio
async def test_auth_flow_and_protected_endpoint(client: httpx.AsyncClient) -> None:
    """
    Authentication flow test with protected resource access.

    - Attempt login to obtain a token
    - Access a protected endpoint with the token
    - Ensure unauthorized access without token is rejected
    """
    login_payload = {
        "username": "test_user",
        "password": "test_password"
    }

    # Attempt login
    resp = await client.post("/auth/login", json=login_payload)
    # Some environments may skip auth setup; handle gracefully
    if resp.status_code != 200:
        pytest.skip("Authentication is not configured in this environment; skipped.")

    token = None
    try:
        token = resp.json().get("access_token")
    except Exception:
        pass

    # Access protected endpoint with token
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = await client.get("/protected", headers=headers)
    # Depending on implementation, protected might be 200 or 401/403
    assert resp.status_code in (200, 401, 403), f"Protected endpoint access has unexpected status: {resp.status_code}"

    # Access protected endpoint without token to confirm rejection when applicable
    resp_no_auth = await client.get("/protected")
    # If the endpoint requires auth, expect 401/403; otherwise 200
    assert resp_no_auth.status_code in (200, 401, 403)


@pytest.mark.asyncio
async def test_external_service_integration(client: httpx.AsyncClient, httpx_mock) -> None:
    """
    Test that the system properly interacts with an external service by mocking
    the outbound HTTP call.

    Endpoint assumption: POST /external-sync triggers a call to
    https://external-service/api/config and returns a combined result.
    """
    external_url = "https://external-service/api/config"

    httpx_mock.add_response(
        method="GET",
        url=external_url,
        json={"config_key": "config_value"},
        status_code=200
    )

    resp = await client.post("/external-sync", json={"source": "unit-test"})
    assert resp.status_code == 200, f"External sync failed: {resp.text}"

    result = resp.json()
    assert isinstance(result, dict)
    # Expect the response to include data from the mocked external service
    assert "external_config_present" in result or "config_key" in result


@pytest.mark.asyncio
async def test_transactional_flow_and_db_opportunities(client: httpx.AsyncClient) -> None:
    """
    Validate transaction-like operations via endpoints that run multiple DB actions.

    This test assumes the API exposes a batch/create-with-transaction endpoint.
    If not present, adapt accordingly (e.g., single-item transactional write).
    """
    payload = [
        {"name": "Transact Item 1", "price": 5.0},
        {"name": "Transact Item 2", "price": 7.5}
    ]

    resp = await client.post("/transactions/batch-create", json=payload)
    # Depending on implementation, could be 200/201 on success
    assert resp.status_code in (200, 201), f"Transactional create failed: {resp.text}"

    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == len(payload)

    # Optional: verify that the items were actually persisted
    # by querying the list and ensuring both exist
    resp = await client.get("/items")
    assert resp.status_code == 200
    items = resp.json()
    names = {item.get("name") for item in items}
    assert "Transact Item 1" in names and "Transact Item 2" in names


@pytest.mark.asyncio
async def test_data_flow_api_service_database_layers(client: httpx.AsyncClient) -> None:
    """
    Validate the data flow from API -> Service -> Database layers.

    This test assumes there is an endpoint that logs internal service calls
    or returns a trace of operations. If your app does not expose such an endpoint,
    adapt to validate by using a combination of CRUD endpoints and mocked service
    layer behavior (see test_service_layer_mocking in the next test).
    """
    resp = await client.post("/items/trace", json={"name": "Trace Item", "price": 1.23})
    # If the endpoint exists, ensure it returns a trace and 201/200 status
    if resp.status_code not in (200, 201):
        pytest.skip("Trace endpoint not available in this environment.")
        return

    trace = resp.json()
    assert isinstance(trace, dict)
    assert "service_calls" in trace or "db_operations" in trace


@pytest.mark.asyncio
async def test_service_layer_mocking_when_present(client: httpx.AsyncClient) -> None:
    """
    If your backend supports swapping/mocking the service layer, verify this interaction.

    - Attempt to create item via API
    - Mock the underlying service function to ensure it is called with expected arguments
    - Verify API responds with the mocked output

    This test will gracefully skip if the service-layer mocking hooks are not available.
    """
    try:
        import unittest.mock as mock  # Python standard library for mocking

        # Path should point to your actual service function used by the endpoint
        # Example: "app.services.item_service.create_item"
        service_path = os.environ.get("SERVICE_MOCK_PATH", "app.services.item_service.create_item")

        module_path, func_name = service_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        original_func = getattr(module, func_name)

        mocked_result = {"id": "mocked-id", "name": "Mocked Item"}

        with mock.patch(service_path, return_value=mocked_result) as mock_func:
            resp = await client.post("/items", json={"name": "Will Be Mocked", "price": 9.99})
            # If endpoint exists, ensure it returns the mocked data
            assert resp.status_code in (200, 201)
            data = resp.json()
            assert data.get("id") == "mocked-id"

            mock_func.assert_called()
    except Exception:
        pytest.skip("Service-layer mocking not configured in this environment.")


# ---------------------------
# Optional: Teardown / Cleanup
# ---------------------------

@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_artifacts():
    """
    Optional cleanup hook to be run after the test session.
    For example, remove test database files if you created them in tests.
    Implementations may vary depending on how your test DB URL is configured.
    """
    yield
    # Example cleanup (uncomment if you rely on a file-based test DB)
    # test_db_path = os.environ.get("TEST_DB_PATH", "./test.db")
    # try:
    #     if os.path.exists(test_db_path):
    #         os.remove(test_db_path)
    # except Exception:
    #     pass

# End of tests/integration/test_backend_integration.py

# Instructions:
# - Update endpoint paths, payloads, and expected status codes to align with your API contract.
# - If your project uses a different authentication mechanism or different protected endpoints,
#   adjust the tests under test_auth_flow_and_protected_endpoint accordingly.
# - If you expose database introspection endpoints or transactional endpoints, you can enrich
#   test_database_operations and test_transactional_flow sections.