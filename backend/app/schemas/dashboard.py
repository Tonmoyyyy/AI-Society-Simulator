from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class RichestCitizen(BaseModel):
    citizen_id: int
    name: str
    balance: Decimal


class DashboardStats(BaseModel):
    population: int
    average_happiness: float
    average_energy: float
    average_health: float
    employed_count: int
    unemployed_count: int
    total_money_in_economy: Decimal
    richest_citizen: Optional[RichestCitizen]


class TrendingPost(BaseModel):
    id: int
    citizen_id: int
    citizen_name: str
    content: str
    created_at: datetime
    comment_count: int
    reaction_count: int
    score: int
