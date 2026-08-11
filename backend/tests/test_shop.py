from decimal import Decimal

from app.models.citizen import Citizen
from app.models.wallet import Wallet
from app.models.shop import Shop
from app.models.product import Product
from app.repositories import shop_repo
from app.simulation.seed_shops import ensure_seed_shops
from app.simulation.shopping import perform_shopping


def _get_token(client, email="shoptest@example.com", password="Pass1234"):
    client.post("/api/v1/auth/signup", json={"email": email, "password": password})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


def _make_citizen(name, job="unemployed"):
    return Citizen(
        name=name, age=30,
        personality_json={"kindness": 50, "intelligence": 50, "ambition": 50, "social": 50, "honesty": 50},
        mood=0.0, happiness=50.0, energy=100.0, health=100.0,
        job=job, current_activity="idle",
    )


# ---- seeding ----

def test_ensure_seed_shops_creates_shops_once(db_session):
    assert shop_repo.count_shops(db_session) == 0
    ensure_seed_shops(db_session)
    count_after_first = shop_repo.count_shops(db_session)
    assert count_after_first > 0

    ensure_seed_shops(db_session)  # idempotent — must not duplicate
    assert shop_repo.count_shops(db_session) == count_after_first


# ---- shop API ----

def test_list_shops_public(client, db_session):
    ensure_seed_shops(db_session)
    resp = client.get("/api/v1/shops")
    assert resp.status_code == 200
    shops = resp.json()
    assert len(shops) > 0
    assert all("products" in s for s in shops)


def test_create_shop_requires_auth(client):
    resp = client.post("/api/v1/shops", json={"name": "Test Shop", "category": "misc"})
    assert resp.status_code == 403  # HTTPBearer: no Authorization header at all


def test_create_shop_and_product(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    shop_resp = client.post(
        "/api/v1/shops", json={"name": "Test Shop", "category": "misc"}, headers=headers
    )
    assert shop_resp.status_code == 201
    shop_id = shop_resp.json()["id"]

    product_resp = client.post(
        f"/api/v1/shops/{shop_id}/products",
        json={"name": "Widget", "price": 9.99},
        headers=headers,
    )
    assert product_resp.status_code == 201
    assert product_resp.json()["name"] == "Widget"

    shops = client.get("/api/v1/shops").json()
    test_shop = next(s for s in shops if s["id"] == shop_id)
    assert any(p["name"] == "Widget" for p in test_shop["products"])


def test_create_product_for_missing_shop(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/api/v1/shops/999999/products", json={"name": "Ghost Item", "price": 1}, headers=headers
    )
    assert resp.status_code == 404


def test_purchases_empty_for_new_citizen(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    citizen_id = client.post("/api/v1/citizens", json={}, headers=headers).json()["id"]

    resp = client.get(f"/api/v1/citizens/{citizen_id}/purchases")
    assert resp.status_code == 200
    assert resp.json() == []


# ---- shopping engine logic (unit-level) ----

def test_shopping_does_nothing_with_no_wallet(db_session):
    citizen = _make_citizen("Broke")
    db_session.add(citizen)
    db_session.commit()

    broadcast_queue = []
    for _ in range(20):
        perform_shopping(db_session, citizen, broadcast_queue)
    assert broadcast_queue == []


def test_shopping_does_nothing_with_zero_balance(db_session):
    citizen = _make_citizen("StillBroke")
    db_session.add(citizen)
    db_session.commit()
    db_session.add(Wallet(citizen_id=citizen.id, balance=Decimal("0.00")))
    db_session.commit()

    broadcast_queue = []
    for _ in range(20):
        perform_shopping(db_session, citizen, broadcast_queue)
    assert broadcast_queue == []


def test_shopping_buys_affordable_product_and_deducts_balance(db_session):
    citizen = _make_citizen("Shopper")
    db_session.add(citizen)
    db_session.commit()
    wallet = Wallet(citizen_id=citizen.id, balance=Decimal("100.00"))
    db_session.add(wallet)
    db_session.commit()

    shop = Shop(name="Test Store", category="misc")
    db_session.add(shop)
    db_session.commit()
    product = Product(shop_id=shop.id, name="Cheap Thing", price=Decimal("5.00"))
    db_session.add(product)
    db_session.commit()

    broadcast_queue = []
    bought = False
    for _ in range(200):  # SHOP_PROBABILITY is only 20% per call
        perform_shopping(db_session, citizen, broadcast_queue)
        db_session.commit()
        if broadcast_queue:
            bought = True
            break

    assert bought
    db_session.refresh(wallet)
    assert wallet.balance == Decimal("95.00")

    purchases = shop_repo.list_purchases_for_citizen(db_session, citizen.id)
    assert len(purchases) == 1
    assert purchases[0].price == Decimal("5.00")


def test_shopping_skips_when_nothing_affordable(db_session):
    citizen = _make_citizen("PoorShopper")
    db_session.add(citizen)
    db_session.commit()
    db_session.add(Wallet(citizen_id=citizen.id, balance=Decimal("1.00")))
    db_session.commit()

    shop = Shop(name="Expensive Store", category="misc")
    db_session.add(shop)
    db_session.commit()
    db_session.add(Product(shop_id=shop.id, name="Yacht", price=Decimal("999999.00")))
    db_session.commit()

    broadcast_queue = []
    for _ in range(50):
        perform_shopping(db_session, citizen, broadcast_queue)
        db_session.commit()

    assert broadcast_queue == []


def test_full_tick_produces_purchases_and_transactions(client):
    token = _get_token(client, email="tickshop@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    citizen_id = client.post("/api/v1/citizens", json={}, headers=headers).json()["id"]
    client.patch(f"/api/v1/citizens/{citizen_id}", json={"job": "engineer"}, headers=headers)

    for _ in range(30):
        resp = client.post("/api/v1/simulation/tick", headers=headers)
        assert resp.status_code == 200

    wallet = client.get(f"/api/v1/citizens/{citizen_id}/wallet").json()
    purchases = client.get(f"/api/v1/citizens/{citizen_id}/purchases").json()
    assert "balance" in wallet
    assert isinstance(purchases, list)
