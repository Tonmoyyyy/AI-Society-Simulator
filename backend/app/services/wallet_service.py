from decimal import Decimal

from sqlalchemy.orm import Session

from app.repositories import citizen_repo, wallet_repo


class WalletError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class InsufficientBalance(WalletError):
    pass


def get_or_create_wallet(db: Session, citizen_id: int, commit: bool = True):
    wallet = wallet_repo.get_by_citizen_id(db, citizen_id)
    if wallet is None:
        wallet = wallet_repo.create_wallet(db, citizen_id, commit=commit)
    return wallet


def get_balance(db: Session, citizen_id: int) -> Decimal:
    wallet = get_or_create_wallet(db, citizen_id)
    return wallet.balance


def withdraw(db: Session, citizen_id: int, amount: Decimal, type_: str = "withdrawal", commit: bool = True):
    """
    Withdraws/Deducts money from a citizen's wallet.
    Used by tick engine and other services for payments, fees, or taxes.
    """
    if amount <= 0:
        raise WalletError("Withdrawal amount must be positive")

    wallet = get_or_create_wallet(db, citizen_id, commit=commit)
    target = wallet_repo.get_locked(db, wallet.id) if commit else wallet

    if target.balance < amount:
        if commit:
            db.rollback()
        raise InsufficientBalance(f"Citizen {citizen_id} has insufficient balance for withdrawal")

    target.balance = target.balance - amount
    db.add(target)

    txn = wallet_repo.record_transaction(
        db, from_wallet_id=target.id, to_wallet_id=None, amount=amount, type_=type_, commit=False
    )

    if commit:
        db.commit()
        db.refresh(target)
        db.refresh(txn)

    return txn


def deposit(db: Session, citizen_id: int, amount: Decimal, type_: str = "deposit", commit: bool = True):
    """
    Deposits/Adds money to a citizen's wallet.
    """
    if amount <= 0:
        raise WalletError("Deposit amount must be positive")

    wallet = get_or_create_wallet(db, citizen_id, commit=commit)
    target = wallet_repo.get_locked(db, wallet.id) if commit else wallet

    target.balance = target.balance + amount
    db.add(target)

    txn = wallet_repo.record_transaction(
        db, from_wallet_id=None, to_wallet_id=target.id, amount=amount, type_=type_, commit=False
    )

    if commit:
        db.commit()
        db.refresh(target)
        db.refresh(txn)

    return txn


def pay_salary(db: Session, citizen_id: int, amount: Decimal, commit: bool = True):
    """Credits a citizen's wallet from the system (from_wallet_id=None) and
    writes a matching transaction row, atomically. Used by the tick engine's
    `work` action — see engine.py.

    When commit=False (the tick-engine path), no row lock is taken: the
    whole tick is already one transaction that commits once at the end, so
    a per-citizen lock here would only add overhead without adding safety.
    Locking matters for commit=True calls (e.g. a concurrent API-triggered
    transfer), where a genuine race is possible."""
    wallet = get_or_create_wallet(db, citizen_id, commit=commit)
    target = wallet_repo.get_locked(db, wallet.id) if commit else wallet
    target.balance = target.balance + amount
    db.add(target)
    txn = wallet_repo.record_transaction(
        db, from_wallet_id=None, to_wallet_id=target.id, amount=amount, type_="salary", commit=False
    )
    if commit:
        db.commit()
        db.refresh(target)
        db.refresh(txn)
    return txn


def transfer(db: Session, from_citizen_id: int, to_citizen_id: int, amount: Decimal):
    if amount <= 0:
        raise WalletError("Transfer amount must be positive")
    if citizen_repo.get_by_id(db, from_citizen_id) is None:
        raise WalletError(f"Citizen {from_citizen_id} not found")
    if citizen_repo.get_by_id(db, to_citizen_id) is None:
        raise WalletError(f"Citizen {to_citizen_id} not found")

    from_wallet = get_or_create_wallet(db, from_citizen_id)
    to_wallet = get_or_create_wallet(db, to_citizen_id)

    # Lock in a fixed order (lower id first) to avoid deadlocks if two
    # transfers between the same pair of wallets happen concurrently.
    first_id, second_id = sorted([from_wallet.id, to_wallet.id])
    locked = {
        first_id: wallet_repo.get_locked(db, first_id),
        second_id: wallet_repo.get_locked(db, second_id),
    }
    from_locked = locked[from_wallet.id]
    to_locked = locked[to_wallet.id]

    if from_locked.balance < amount:
        db.rollback()
        raise InsufficientBalance(
            f"Citizen {from_citizen_id} has insufficient balance for this transfer"
        )

    from_locked.balance = from_locked.balance - amount
    to_locked.balance = to_locked.balance + amount
    db.add(from_locked)
    db.add(to_locked)

    txn = wallet_repo.record_transaction(
        db, from_wallet_id=from_locked.id, to_wallet_id=to_locked.id, amount=amount,
        type_="transfer", commit=False,
    )
    db.commit()
    db.refresh(txn)
    return txn


def get_transaction_history(db: Session, citizen_id: int, limit: int = 20):
    wallet = get_or_create_wallet(db, citizen_id)
    return wallet_repo.list_transactions_for_wallet(db, wallet.id, limit=limit)