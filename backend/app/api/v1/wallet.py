from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.wallet import WalletOut, TransferRequest, TransactionOut
from app.services import citizen_service, wallet_service
from app.services.citizen_service import CitizenNotFound
from app.services.wallet_service import WalletError, InsufficientBalance

router = APIRouter(prefix="/api/v1/citizens", tags=["economy"])


@router.get("/{citizen_id}/wallet", response_model=WalletOut)
def get_wallet(citizen_id: int, db: Session = Depends(get_db)):
    """Public — wallet balance, same visibility level as the rest of a
    citizen's profile."""
    try:
        citizen_service.get_citizen(db, citizen_id)
    except CitizenNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    balance = wallet_service.get_balance(db, citizen_id)
    return {"citizen_id": citizen_id, "balance": balance}


@router.get("/{citizen_id}/transactions", response_model=list[TransactionOut])
def get_transactions(
    citizen_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    try:
        citizen_service.get_citizen(db, citizen_id)
    except CitizenNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    return wallet_service.get_transaction_history(db, citizen_id, limit=limit)


@router.post("/{citizen_id}/wallet/transfer", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def transfer(
    citizen_id: int,
    payload: TransferRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manual citizen-to-citizen transfer — mainly for testing/seeding the
    economy; the primary money-in path is the tick engine's salary payment."""
    try:
        return wallet_service.transfer(db, citizen_id, payload.to_citizen_id, payload.amount)
    except InsufficientBalance as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)
    except WalletError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
