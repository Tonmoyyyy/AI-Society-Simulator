from sqlalchemy import Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Wallet(Base):
    """
    The ONLY source of truth for a citizen's money — citizens has no money
    column (see approved v0.1 corrections). One wallet per citizen, created
    on demand (see wallet_service.get_or_create_wallet) rather than forced
    at citizen-creation time, so Phase 2's citizen creation code didn't need
    to change for this phase.
    """

    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    citizen_id: Mapped[int] = mapped_column(ForeignKey("citizens.id"), nullable=False, unique=True)
    balance: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False, default=0)
