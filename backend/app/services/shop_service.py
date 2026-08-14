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


def get_purchase_history(db: Session, citizen_id: int, limit: int = 20) -> list[dict]:
    """Enriched with shop/product names (not just IDs) — the purchases
    table itself is IDs-only by design (see Purchase model), but showing
    "Product #5" in a UI is bad UX, so the API layer resolves names here
    rather than pushing that join onto every client."""
    purchases = shop_repo.list_purchases_for_citizen(db, citizen_id, limit=limit)
    result = []
    for purchase in purchases:
        shop = shop_repo.get_shop(db, purchase.shop_id)
        product = shop_repo.get_product(db, purchase.product_id)
        result.append({
            "id": purchase.id,
            "citizen_id": purchase.citizen_id,
            "shop_id": purchase.shop_id,
            "shop_name": shop.name if shop else "Unknown shop",
            "product_id": purchase.product_id,
            "product_name": product.name if product else "Unknown product",
            "price": purchase.price,
            "created_at": purchase.created_at,
        })
    return result
