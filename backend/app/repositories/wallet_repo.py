from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.wallet import Wallet
from app.models.transaction import Transaction


def get_by_citizen_id(db: Session, citizen_id: int) -> Optional[Wallet]:
    return db.query(Wallet).filter(Wallet.citizen_id == citizen_id).first()


def get_locked(db: Session, wallet_id: int) -> Wallet:
    """SELECT ... FOR UPDATE — call only inside a transaction that will
    commit promptly. This is what makes concurrent balance changes safe
    (see SDD Security Plan: never a bare UPDATE balance)."""
    return db.query(Wallet).filter(Wallet.id == wallet_id).with_for_update().one()


def create_wallet(db: Session, citizen_id: int, commit: bool = True) -> Wallet:
    wallet = Wallet(citizen_id=citizen_id, balance=Decimal("0.00"))
    db.add(wallet)
    if commit:
        db.commit()
        db.refresh(wallet)
    return wallet


def record_transaction(
    db: Session,
    from_wallet_id: Optional[int],
    to_wallet_id: Optional[int],
    amount: Decimal,
    type_: str,
    commit: bool = True,
) -> Transaction:
    txn = Transaction(
        from_wallet_id=from_wallet_id,
        to_wallet_id=to_wallet_id,
        amount=amount,
        type=type_,
    )
    db.add(txn)
    if commit:
        db.commit()
        db.refresh(txn)
    return txn


def list_transactions_for_wallet(db: Session, wallet_id: int, limit: int = 20) -> list[Transaction]:
    return (
        db.query(Transaction)
        .filter(
            (Transaction.from_wallet_id == wallet_id) | (Transaction.to_wallet_id == wallet_id)
        )
        .order_by(Transaction.id.desc())
        .limit(limit)
        .all()
    )
