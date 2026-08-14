from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.citizen import Citizen
from app.models.wallet import Wallet
from app.repositories import social_repo, timeline_repo


def get_stats(db: Session) -> dict:
    population = db.query(func.count(Citizen.id)).scalar() or 0
    avg_happiness = db.query(func.avg(Citizen.happiness)).scalar() or 0
    avg_energy = db.query(func.avg(Citizen.energy)).scalar() or 0
    avg_health = db.query(func.avg(Citizen.health)).scalar() or 0
    employed = (
        db.query(func.count(Citizen.id)).filter(Citizen.job != "unemployed").scalar() or 0
    )
    total_money = db.query(func.coalesce(func.sum(Wallet.balance), 0)).scalar() or 0

    richest_row = (
        db.query(Citizen.id, Citizen.name, Wallet.balance)
        .join(Wallet, Wallet.citizen_id == Citizen.id)
        .order_by(Wallet.balance.desc())
        .first()
    )
    richest = None
    if richest_row is not None and richest_row[2] > 0:
        richest = {"citizen_id": richest_row[0], "name": richest_row[1], "balance": richest_row[2]}

    return {
        "population": population,
        "average_happiness": round(float(avg_happiness), 2),
        "average_energy": round(float(avg_energy), 2),
        "average_health": round(float(avg_health), 2),
        "employed_count": employed,
        "unemployed_count": population - employed,
        "total_money_in_economy": total_money,
        "richest_citizen": richest,
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

    # resolve citizen names only for the ones we're actually returning
    from app.repositories import citizen_repo
    for item in top:
        citizen = citizen_repo.get_by_id(db, item["citizen_id"])
        item["citizen_name"] = citizen.name if citizen else "Unknown"

    return top


def get_leaderboard(db: Session, limit: int = 20) -> list[dict]:
    """Every citizen's wallet balance, richest first — citizens with no
    wallet yet (never worked/earned) show as $0.00, not omitted, so the
    view genuinely represents "who has how much" rather than only
    showing citizens who've already earned something."""
    citizens = db.query(Citizen).all()
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
