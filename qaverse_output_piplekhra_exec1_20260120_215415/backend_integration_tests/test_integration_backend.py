import os
import pytest
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI, Depends, HTTPException, Header
from pydantic import BaseModel
from fastapi.testclient import TestClient
import httpx
import respx

# --- Generic ORM setup (in-memory test DB) ---
Base = declarative_base()

class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    value = Column(Integer, nullable=False)

# Pydantic schemas
class ItemCreate(BaseModel):
    name: str
    value: int

class ItemOut(BaseModel):
    id: int
    name: str
    value: int

    class Config:
        orm_mode = True

class AuthRequest(BaseModel):
    username: str
    password: str

class PaymentRequest(BaseModel):
    item_id: int

# Create a FastAPI app with in-test endpoints
def create_app(engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    app = FastAPI(title="Generic Backend Integration API (Test)")

    def get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    # Simple token-based auth for tests
    async def verify_token(authorization: str = Header(None)):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Not authenticated")
        token = authorization.split(" ")[1]
        if token != "test-token":
            raise HTTPException(status_code=403, detail="Forbidden")
        return token

    @app.post("/items", response_model=ItemOut, status_code=201)
    def create_item(item: ItemCreate, db: Session = Depends(get_db)):
        db_item = Item(name=item.name, value=item.value)
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        return db_item

    @app.get("/items/{item_id}", response_model=ItemOut)
    def read_item(item_id: int, db: Session = Depends(get_db)):
        item = db.query(Item).filter(Item.id == item_id).first()
        if item is None:
            raise HTTPException(status_code=404, detail="Item not found")
        return item

    @app.post("/auth/login")
    def login(auth: AuthRequest):
        if auth.username == "test" and auth.password == "password":
            return {"token": "test-token"}
        raise HTTPException(status_code=401, detail="Invalid credentials")

    @app.get("/protected/items")
    def protected_items(token: str = Depends(verify_token)):
        return {"status": "ok"}

    @app.post("/payments")
    def process_payment(payment: PaymentRequest, db: Session = Depends(get_db)):
        # Call to an external payment service (mocked in tests)
        import httpx
        resp = httpx.post("https://payments.example/api/charge", json={"item_id": payment.item_id})
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Payment service error")
        data = resp.json()
        return {"charge_id": data.get("charge_id"), "status": "paid"}

    return app

# --- PyTest fixtures for test DB and client ---

@pytest.fixture(scope="module")
def engine():
    # Use an in-memory SQLite DB that is shared across the test module
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def client(engine):
    app = create_app(engine)
    with TestClient(app) as c:
        yield c

# --- Integration tests: API endpoints, DB ops, service/auth flows, external calls ---

def test_create_and_get_item(client):
    # Create an item via API
    resp = client.post("/items", json={"name": "Widget", "value": 42})
    assert resp.status_code == 201
    data = resp.json()
    item_id = data["id"]
    assert data["name"] == "Widget"
    assert data["value"] == 42

    # Retrieve the same item
    resp2 = client.get(f"/items/{item_id}")
    assert resp2.status_code == 200
    assert resp2.json() == data

def test_auth_and_protected_endpoint(client):
    # Authenticate
    resp = client.post("/auth/login", json={"username": "test", "password": "password"})
    assert resp.status_code == 200
    token = resp.json()["token"]
    assert token == "test-token"

    # Access protected endpoint with token
    resp = client.get("/protected/items", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

def test_payment_integration(client):
    # Ensure an item exists for payment flow
    resp = client.post("/items", json={"name": "Gadget", "value": 15})
    assert resp.status_code == 201
    item_id = resp.json()["id"]

    with respx.mock(assert_all_called=False) as rsps:
        rsps.post("https://payments.example/api/charge").mock(
            return_value=httpx.Response(200, json={"charge_id": "ch_123"})
        )

        resp = client.post("/payments", json={"item_id": item_id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["charge_id"] == "ch_123"
        assert data["status"] == "paid"

def test_db_transaction_rollback(engine):
    # Verify that a manual transaction can be rolled back and not persisted
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        trans = session.begin()
        item = Item(name="Temp", value=5)
        session.add(item)
        # Rollback the transaction
        trans.rollback()
        count = session.query(Item).filter_by(name="Temp").count()
        assert count == 0
    finally:
        session.close()

# End of tests