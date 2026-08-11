from datetime import datetime
from typing import Optional

from sqlalchemy import Numeric, String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Transaction(Base):
    """
    An immutable ledger row. Every balance change — salary, transfer,
    purchase, etc. — writes one of these in the same DB transaction as the
    balance update (see wallet_service), never a bare UPDATE.
    from_wallet_id is NULL for system-sourced money (salary); to_wallet_id
    is NULL for money leaving the simulated economy (purchases — see
    Purchase model, which records the shop/product detail this row alone
    doesn't capture).
    """

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    from_wallet_id: Mapped[Optional[int]] = mapped_column(ForeignKey("wallets.id"), nullable=True)
    to_wallet_id: Mapped[Optional[int]] = mapped_column(ForeignKey("wallets.id"), nullable=True)
    amount: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)  # "salary" | "transfer" | "purchase"
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
