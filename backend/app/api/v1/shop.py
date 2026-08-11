from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.shop import ShopOut, ShopCreate, ProductOut, ProductCreate, PurchaseOut
from app.services import shop_service
from app.services.shop_service import ShopNotFound

router = APIRouter(prefix="/api/v1", tags=["economy"])


@router.get("/shops", response_model=list[ShopOut])
def list_shops(db: Session = Depends(get_db)):
    """Public — every shop and its product catalog. Same read-is-public
    pattern as citizens/posts/dashboard."""
    return shop_service.list_shops_with_products(db)


@router.post("/shops", response_model=ShopOut, status_code=status.HTTP_201_CREATED)
def create_shop(
    payload: ShopCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shop = shop_service.create_shop(db, name=payload.name, category=payload.category)
    return {"id": shop.id, "name": shop.name, "category": shop.category, "products": []}


@router.post("/shops/{shop_id}/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    shop_id: int,
    payload: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return shop_service.create_product(db, shop_id=shop_id, name=payload.name, price=payload.price)
    except ShopNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.get("/citizens/{citizen_id}/purchases", response_model=list[PurchaseOut])
def get_purchases(
    citizen_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Public — a citizen's purchase history, most recent first."""
    return shop_service.get_purchase_history(db, citizen_id, limit=limit)
