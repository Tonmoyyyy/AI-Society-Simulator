from decimal import Decimal

from sqlalchemy.orm import Session

from app.repositories import shop_repo


class ShopError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ShopNotFound(ShopError):
    pass


def list_shops_with_products(db: Session) -> list[dict]:
    shops = shop_repo.list_shops(db)
    result = []
    for shop in shops:
        products = shop_repo.list_products(db, shop_id=shop.id)
        result.append({
            "id": shop.id,
            "name": shop.name,
            "category": shop.category,
            "products": products,
        })
    return result


def get_shop(db: Session, shop_id: int):
    shop = shop_repo.get_shop(db, shop_id)
    if shop is None:
        raise ShopNotFound(f"Shop {shop_id} not found")
    return shop


def create_shop(db: Session, name: str, category: str):
    return shop_repo.create_shop(db, name=name, category=category)


def create_product(db: Session, shop_id: int, name: str, price: Decimal):
    get_shop(db, shop_id)  # 404s if missing
    return shop_repo.create_product(db, shop_id=shop_id, name=name, price=price)


def get_purchase_history(db: Session, citizen_id: int, limit: int = 20):
    return shop_repo.list_purchases_for_citizen(db, citizen_id, limit=limit)
