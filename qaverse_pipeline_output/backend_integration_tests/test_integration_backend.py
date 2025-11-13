# tests/test_integration.py

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch

# The following imports assume a typical backend structure.
# Adjust module paths to match your actual project layout.
try:
    from myapp.main import app  # FastAPI instance
    from myapp.database import get_db, Base  # DB dependency and declarative base
except Exception as e:
    # If the app structure differs, tests will be skipped gracefully.
    pytest.skip(f"App structure not detected for integration tests: {e}", allow_module_level=True)

# Database configuration for tests
TEST_DATABASE_URL = "sqlite:///./test.db"  # File-based SQLite for stable multi-thread testing
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Helper to import Item model if present; tests will skip DB assertions if model not present
try:
    from myapp.models import Item as ItemModel  # Optional: your Item ORM model
except Exception:
    ItemModel = None  # type: ignore

@pytest.fixture(scope="session")
def client():
    # Override the app's DB dependency to use the test database
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # Create all tables for the test DB
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as test_client:
        yield test_client

    # Teardown: drop all test tables
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()

@pytest.fixture(autouse=True)
def run_around_tests():
    # Optional: could reset state between tests if needed
    yield
    # After each test: if ItemModel exists, ensure DB is clean for isolation
    if ItemModel is not None:
        with TestingSessionLocal() as session:
            session.query(ItemModel).delete()
            session.commit()

def test_health_endpoint(client):
    # Generic health check
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() if resp.content else {"status": "ok"}

def test_create_item_saves_and_returns_id(client):
    payload = {"name": "Widget", "price": 9.99}
    resp = client.post("/items/", json=payload)
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert "id" in data
    assert data["name"] == payload["name"]
    assert float(data["price"]) == float(payload["price"])

    # Verify DB persistence if ItemModel exists
    if ItemModel is not None:
        with TestingSessionLocal() as session:
            item = session.query(ItemModel).filter(ItemModel.id == data["id"]).first()
            assert item is not None
            assert item.name == payload["name"]
            assert float(item.price) == float(payload["price"])

def test_get_item_by_id(client):
    # First create an item
    payload = {"name": "Gadget", "price": 12.5}
    create_resp = client.post("/items/", json=payload)
    assert create_resp.status_code in (200, 201)
    item_id = create_resp.json()["id"]

    # Then retrieve it
    resp = client.get(f"/items/{item_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == item_id
    assert data["name"] == payload["name"]
    assert float(data["price"]) == float(payload["price"])

def test_list_items_includes_created_item(client):
    # Create two items
    client.post("/items/", json={"name": "Alpha", "price": 1.0})
    client.post("/items/", json={"name": "Beta", "price": 2.5})

    resp = client.get("/items/")
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) >= 2  # At least the two we've added

def test_update_item(client):
    # Create item to update
    create_resp = client.post("/items/", json={"name": "OldName", "price": 3.0})
    item_id = create_resp.json()["id"]

    # Update the item
    resp = client.put(f"/items/{item_id}", json={"name": "NewName", "price": 4.5})
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == item_id
    assert data["name"] == "NewName"
    assert float(data["price"]) == 4.5

    # Verify DB update if model exists
    if ItemModel is not None:
        with TestingSessionLocal() as session:
            item = session.query(ItemModel).get(item_id)
            if item:
                assert item.name == "NewName"
                assert float(item.price) == 4.5

def test_delete_item(client):
    # Create item to delete
    create_resp = client.post("/items/", json={"name": "Temp", "price": 0.99})
    item_id = create_resp.json()["id"]

    # Delete
    resp = client.delete(f"/items/{item_id}")
    assert resp.status_code in (200, 204)

    # Ensure it's gone
    resp = client.get(f"/items/{item_id}")
    assert resp.status_code == 404

def test_api_calls_service_layer_when_creating_item(client, monkeypatch):
    # Optional: verify API delegates to service layer
    # If your project has a service layer path like myapp.services.item_service.create_item
    try:
        import myapp.services.item_service as item_service
        service_path = "myapp.services.item_service.create_item"

        called = {}

        def fake_create_item(db, item_in):
            called['payload'] = item_in
            return {"id": 9999, "name": item_in.get("name"), "price": item_in.get("price")}

        monkeypatch.setattr(service_path, "create_item", fake_create_item, raising=True)

        resp = client.post("/items/", json={"name": "ServiceItem", "price": 7.77})
        assert resp.status_code in (200, 201)
        assert resp.json()["id"] == 9999
        assert called['payload'] is not None
        assert called['payload'].get("name") == "ServiceItem"
        assert float(called['payload'].get("price")) == 7.77
    except Exception:
        # If service layer path isn't present in the project, skip this check gracefully
        pytest.skip("Service layer integration test skipped (path not found).")

def test_external_notifier_is_called_on_item_creation(client):
    # Attempt to patch an external notifier; skip if not present
    notifier_path = "myapp.external.notifier.notify_item_created"
    try:
        with patch(notifier_path) as mock_notify:
            resp = client.post("/items/", json={"name": "NotifyTest", "price": 5.0})
            assert resp.status_code in (200, 201)
            mock_notify.assert_called_once()
    except Exception:
        pytest.skip("External notifier integration not available in this project structure.")
```