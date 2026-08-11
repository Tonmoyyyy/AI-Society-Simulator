from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.shop import Shop
from app.models.product import Product
from app.models.purchase import Purchase


# ---- shops ----

def count_shops(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Shop)) or 0


def list_shops(db: Session) -> list[Shop]:
    return db.query(Shop).order_by(Shop.id).all()


def get_shop(db: Session, shop_id: int) -> Optional[Shop]:
    return db.get(Shop, shop_id)


def create_shop(db: Session, name: str, category: str, commit: bool = True) -> Shop:
    shop = Shop(name=name, category=category)
    db.add(shop)
    if commit:
        db.commit()
        db.refresh(shop)
    return shop


# ---- products ----

def list_products(db: Session, shop_id: Optional[int] = None) -> list[Product]:
    query = db.query(Product)
    if shop_id is not None:
        query = query.filter(Product.shop_id == shop_id)
    return query.order_by(Product.id).all()


def get_product(db: Session, product_id: int) -> Optional[Product]:
    return db.get(Product, product_id)


def create_product(db: Session, shop_id: int, name: str, price: Decimal, commit: bool = True) -> Product:
    product = Product(shop_id=shop_id, name=name, price=price)
    db.add(product)
    if commit:
        db.commit()
        db.refresh(product)
    return product


def list_affordable_products(db: Session, max_price: Decimal) -> list[Product]:
    """Used by the tick engine's shopping step — every product a citizen
    with this balance could buy right now."""
    return db.query(Product).filter(Product.price <= max_price).all()


# ---- purchases ----

def create_purchase(
    db: Session,
    citizen_id: int,
    shop_id: int,
    product_id: int,
    price: Decimal,
    commit: bool = True,
) -> Purchase:
    purchase = Purchase(citizen_id=citizen_id, shop_id=shop_id, product_id=product_id, price=price)
    db.add(purchase)
    if commit:
        db.commit()
        db.refresh(purchase)
    return purchase


def list_purchases_for_citizen(db: Session, citizen_id: int, limit: int = 20) -> list[Purchase]:
    return (
        db.query(Purchase)
        .filter(Purchase.citizen_id == citizen_id)
        .order_by(Purchase.id.desc())
        .limit(limit)
        .all()
    )
