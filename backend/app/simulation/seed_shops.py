"""
Seeds a handful of shops and products if none exist yet. Called once at
app startup (see main.py's lifespan) — same "safety net, not the source of
truth" spirit as the Base.metadata.create_all() call: idempotent (checks
count first), and if it fails (DB not reachable), the app should still
boot rather than crash.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.repositories import shop_repo

_SEED_DATA = [
    ("Corner Grocery", "grocery", [
        ("Bread", "5.00"),
        ("Milk", "4.00"),
        ("Eggs", "6.00"),
        ("Rice (5kg)", "8.00"),
    ]),
    ("City Electronics", "electronics", [
        ("Phone Charger", "15.00"),
        ("Headphones", "40.00"),
        ("Bluetooth Speaker", "60.00"),
    ]),
    ("Fashion Studio", "clothing", [
        ("T-Shirt", "20.00"),
        ("Jacket", "55.00"),
        ("Shoes", "45.00"),
    ]),
    ("Book Nook", "books", [
        ("Novel", "12.00"),
        ("Cookbook", "18.00"),
    ]),
]


def ensure_seed_shops(db: Session) -> None:
    if shop_repo.count_shops(db) > 0:
        return  # already seeded (or a human created shops manually) — don't duplicate

    for shop_name, category, products in _SEED_DATA:
        shop = shop_repo.create_shop(db, name=shop_name, category=category, commit=False)
        db.flush()  # need shop.id for the products below, without a full commit yet
        for product_name, price in products:
            shop_repo.create_product(db, shop_id=shop.id, name=product_name, price=Decimal(price), commit=False)
    db.commit()
