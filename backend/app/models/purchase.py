from datetime import datetime

from sqlalchemy import Numeric, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Purchase(Base):
    """One purchase event. `price` is snapshotted at purchase time — if a
    product's price changes later, past purchase history stays accurate.
    The matching money movement is also recorded in `transactions`
    (type="purchase", to_wallet_id=None — money leaving the simulated
    economy, same field that was reserved for this in Phase 5)."""

    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    citizen_id: Mapped[int] = mapped_column(ForeignKey("citizens.id"), nullable=False, index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    price: Mapped[Numeric] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
