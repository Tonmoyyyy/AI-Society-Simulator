"""
Read-only aggregates for the dashboard.

EVERY CITIZEN AGGREGATE HERE COUNTS THE LIVING ONLY. Death is a soft flag, so
deceased citizens keep their rows; without the explicit `is_alive` filters below,
`population` would never fall and the wellbeing averages would be dragged by
people who are no longer in the society. `deceased_count` reports the dead
separately, which is the honest way to show both numbers at once.

The one deliberate exception is `total_money_in_economy` — see the comment at
its query.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.citizen import Citizen
from app.models.wallet import Wallet
from app.repositories import citizen_repo, social_repo, timeline_repo
from app.services import government_service
from app.simulation.genders import GENDER_FEMALE, GENDER_MALE


def _living(db: Session, *columns):
    """A query over the given columns, restricted to living citizens.

    A helper rather than six repeated `.filter(...)` calls, because a filter that
    has to be remembered six times is a filter that will eventually be forgotten
    once.
    """
    return db.query(*columns).filter(Citizen.is_alive.is_(True))


def get_stats(db: Session) -> dict:
    population = _living(db, func.count(Citizen.id)).scalar() or 0
    avg_happiness = _living(db, func.avg(Citizen.happiness)).scalar() or 0
    avg_energy = _living(db, func.avg(Citizen.energy)).scalar() or 0
    avg_health = _living(db, func.avg(Citizen.health)).scalar() or 0
    employed = (
        _living(db, func.count(Citizen.id)).filter(Citizen.job != "unemployed").scalar() or 0
    )

    # NOT filtered by liveness, on purpose. Death does not destroy money — it
    # leaves a wallet nobody is spending from. Excluding the dead here would make
    # the total drop every time someone died, which would read as currency
    # vanishing from the economy rather than as an inheritance problem nobody has
    # modelled yet. There is no inheritance system, so the honest statement is
    # "this much money exists".
    total_money = db.query(func.coalesce(func.sum(Wallet.balance), 0)).scalar() or 0

    richest_row = (
        db.query(Citizen.id, Citizen.name, Wallet.balance)
        .join(Wallet, Wallet.citizen_id == Citizen.id)
        .filter(Citizen.is_alive.is_(True))
        .order_by(Wallet.balance.desc())
        .first()
    )
    richest = None
    if richest_row is not None and richest_row[2] > 0:
        richest = {"citizen_id": richest_row[0], "name": richest_row[1], "balance": richest_row[2]}

    # Gender counts come from the same GROUP BY the demographics endpoint uses, so
    # the dashboard card and the demographics page can never disagree.
    by_gender = citizen_repo.count_by_gender(db, include_dead=False)

    # WHO GOVERNS, resolved by join on every request — the dashboard shows the
    # President and First Lady by name, and because nothing is cached, renaming
    # that citizen renames them here with no extra work. `system_available` is
    # False only when no government row exists, which lets the dashboard hide the
    # block instead of rendering "None".
    gov = government_service.get_summary(db)

    return {
        "population": population,
        "deceased_count": citizen_repo.count_dead(db),
        "average_happiness": round(float(avg_happiness), 2),
        "average_energy": round(float(avg_energy), 2),
        "average_health": round(float(avg_health), 2),
        "employed_count": employed,
        "unemployed_count": population - employed,
        "total_money_in_economy": total_money,
        "richest_citizen": richest,
        "male_count": by_gender.get(GENDER_MALE, 0),
        "female_count": by_gender.get(GENDER_FEMALE, 0),
        "president_name": gov.get("president_name"),
        "first_lady_name": gov.get("first_lady_name"),
        "government_available": gov.get("system_available", False),
    }


def get_trending_posts(db: Session, limit: int = 5, window: int = 50) -> list[dict]:
    """Ranks the most recent `window` posts by (comments + reactions) and
    returns the top `limit`. Good enough at v0.1 scale — a real "trending"
    algorithm (time-decay, velocity) is future work, not needed yet."""
    posts, _ = social_repo.list_posts_paginated(db, offset=0, limit=window)
    scored = []
    for post in posts:
        comment_count = social_repo.count_comments(db, post.id)
        reaction_count = social_repo.count_reactions(db, post.id)
        scored.append({
            "id": post.id,
            "citizen_id": post.citizen_id,
            "content": post.content,
            "created_at": post.created_at,
            "comment_count": comment_count,
            "reaction_count": reaction_count,
            "score": comment_count + reaction_count,
        })

    scored.sort(key=lambda p: p["score"], reverse=True)
    top = scored[:limit]

    # Resolve citizen names only for the ones we're actually returning.
    # `get_by_id` deliberately does not filter on liveness, so a post by someone
    # who has since died still shows their name rather than "Unknown" — their
    # posts outlive them, which is the point of a soft death.
    for item in top:
        citizen = citizen_repo.get_by_id(db, item["citizen_id"])
        item["citizen_name"] = citizen.name if citizen else "Unknown"

    return top


def get_leaderboard(db: Session, limit: int = 20) -> list[dict]:
    """Every LIVING citizen's wallet balance, richest first — citizens with no
    wallet yet (never worked/earned) show as $0.00, not omitted, so the
    view genuinely represents "who has how much" rather than only
    showing citizens who've already earned something.

    The dead are excluded: a leaderboard is a ranking of the society's current
    members, and leaving a deceased citizen at the top of it would be strange."""
    citizens = citizen_repo.list_all(db)  # living only by default
    from app.repositories import wallet_repo
    rows = []
    for citizen in citizens:
        wallet = wallet_repo.get_by_citizen_id(db, citizen.id)
        balance = wallet.balance if wallet else 0
        rows.append({
            "citizen_id": citizen.id,
            "name": citizen.name,
            "job": citizen.job,
            "neighborhood": citizen.neighborhood,
            "balance": balance,
        })
    rows.sort(key=lambda r: r["balance"], reverse=True)
    return rows[:limit]


def get_timeline(db: Session, page: int, page_size: int, category: str | None = None):
    offset = (page - 1) * page_size
    return timeline_repo.list_paginated(db, offset=offset, limit=page_size, category=category)
