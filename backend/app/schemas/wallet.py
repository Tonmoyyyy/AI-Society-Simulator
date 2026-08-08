from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class WalletOut(BaseModel):
    citizen_id: int
    balance: Decimal


class TransferRequest(BaseModel):
    to_citizen_id: int
    amount: Decimal = Field(gt=0)


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_wallet_id: Optional[int]
    to_wallet_id: Optional[int]
    amount: Decimal
    type: str
    created_at: datetime
