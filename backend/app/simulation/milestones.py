"""
Milestone detectors for the Simulation Timeline (SDD §9). Each function is
a plain check against current aggregate state vs. what's already recorded
in timeline_events — deliberately cheap (a handful of aggregate queries),
not a new simulation subsystem. Called once per tick, after the tick's main
batch commit, so detectors see final post-tick state.

Adding a detector for a future phase (e.g. "first business created" in a
later economy expansion) means adding one function here and registering it
in run_all_detectors — nothing else needs to change.

EVERY AGGREGATE HERE COUNTS THE LIVING ONLY. Death is a soft flag, so the rows
of deceased citizens stay in the table; without the explicit `is_alive` filters
below, "population reached 50" would keep counting the dead and average happiness
would be dragged by people who are no longer around to be unhappy. Note that a
population milestone already recorded is NOT withdrawn if deaths take the
population back under the threshold — `exists_with_title` makes these
once-and-for-all historical records, which is the intent.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.citizen import Citizen
from app.models.wallet import Wallet
from app.repositories import timeline_repo

_POPULATION_THRESHOLDS = [10, 25, 50, 75, 100]
_HAPPINESS_LOW = 30.0
_HAPPINESS_RECOVERED = 50.0


def _check_population_milestone(db: Session, tick_number: int) -> list:
    count = (
        db.query(func.count(Citizen.id))
        .filter(Citizen.is_alive.is_(True))
        .scalar()
        or 0
    )
    created = []
    for threshold in _POPULATION_THRESHOLDS:
        if count < threshold:
            continue
        title = f"Population reached {threshold}"
        if timeline_repo.exists_with_title(db, title):
            continue
        event = timeline_repo.create(
            db,
            tick_number=tick_number,
            category="population",
            title=title,
            description=f"The city has grown to {count} citizens.",
            payload={"population": count},
            commit=False,
        )
        created.append(event)
    return created


def _check_richest_citizen(db: Session, tick_number: int) -> list:
    row = (
        db.query(Citizen.id, Citizen.name, Wallet.balance)
        .join(Wallet, Wallet.citizen_id == Citizen.id)
        .filter(Wallet.balance > 0, Citizen.is_alive.is_(True))
        .order_by(Wallet.balance.desc())
        .first()
    )
    if row is None:
        return []
    citizen_id, name, balance = row

    last = timeline_repo.get_latest_by_category(db, "richest_citizen")
    last_id = (last.payload_json or {}).get("citizen_id") if last else None
    if last_id == citizen_id:
        return []

    event = timeline_repo.create(
        db,
        tick_number=tick_number,
        category="richest_citizen",
        title=f"{name} became the richest citizen",
        description=f"{name} is now the wealthiest citizen with a balance of {balance}.",
        payload={"citizen_id": citizen_id, "balance": str(balance)},
        commit=False,
    )
    return [event]


def _check_happiness(db: Session, tick_number: int) -> list:
    avg_happiness = (
        db.query(func.avg(Citizen.happiness))
        .filter(Citizen.is_alive.is_(True))
        .scalar()
    )
    if avg_happiness is None:
        return []
    avg_happiness = float(avg_happiness)

    last = timeline_repo.get_latest_by_category(db, "happiness")
    currently_alerting = last is not None and last.title == "Happiness crisis"

    if avg_happiness < _HAPPINESS_LOW and not currently_alerting:
        event = timeline_repo.create(
            db,
            tick_number=tick_number,
            category="happiness",
            title="Happiness crisis",
            description=f"Average citizen happiness dropped to {avg_happiness:.1f}.",
            payload={"average_happiness": round(avg_happiness, 2)},
            commit=False,
        )
        return [event]
    elif avg_happiness >= _HAPPINESS_RECOVERED and currently_alerting:
        event = timeline_repo.create(
            db,
            tick_number=tick_number,
            category="happiness",
            title="Happiness recovered",
            description=f"Average citizen happiness recovered to {avg_happiness:.1f}.",
            payload={"average_happiness": round(avg_happiness, 2)},
            commit=False,
        )
        return [event]
    return []


def run_all_detectors(db: Session, tick_number: int) -> list:
    """Returns the list of newly-created (not-yet-committed) TimelineEvent
    objects — the caller (engine.py) commits once and can broadcast them."""
    created = []
    created += _check_population_milestone(db, tick_number)
    created += _check_richest_citizen(db, tick_number)
    created += _check_happiness(db, tick_number)
    return created
