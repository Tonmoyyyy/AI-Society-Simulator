from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class RichestCitizen(BaseModel):
    citizen_id: int
    name: str
    balance: Decimal


class LeaderboardEntry(BaseModel):
    citizen_id: int
    name: str
    job: str
    neighborhood: str
    balance: Decimal


class DashboardStats(BaseModel):
    """
    GET /api/v1/dashboard/stats.

    `population` counts the LIVING; `deceased_count` reports the dead separately
    rather than being folded in, because after the first death "how many citizens
    are there" has two right answers and the API should not silently pick one.

    The government fields are resolved from `citizens` by join on every request and
    are not stored anywhere, so renaming the citizen who is President relabels the
    dashboard — and the 3D map's Presidential Palace — with no further work.
    `government_available` is False only when no government row exists at all,
    which is what lets the dashboard hide the block instead of rendering "None".
    Note that True does not imply a President: an established government can have
    vacant offices, so `president_name` may still be null.
    """

    population: int
    deceased_count: int = 0
    average_happiness: float
    average_energy: float
    average_health: float
    employed_count: int
    unemployed_count: int
    total_money_in_economy: Decimal
    richest_citizen: Optional[RichestCitizen]

    male_count: int = 0
    female_count: int = 0

    president_name: Optional[str] = None
    first_lady_name: Optional[str] = None
    government_available: bool = False


class TrendingPost(BaseModel):
    id: int
    citizen_id: int
    citizen_name: str
    content: str
    created_at: datetime
    comment_count: int
    reaction_count: int
    score: int
