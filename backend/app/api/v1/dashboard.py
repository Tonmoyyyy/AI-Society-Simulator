from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.dashboard import DashboardStats, TrendingPost, LeaderboardEntry
from app.schemas.timeline import TimelineListResponse
from app.services import dashboard_service

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


@router.get("/dashboard/stats", response_model=DashboardStats)
def get_stats(db: Session = Depends(get_db)):
    """Public — population, average mood/energy/health, employment,
    total money in the simulated economy, and the current richest citizen."""
    return dashboard_service.get_stats(db)


@router.get("/dashboard/trending", response_model=list[TrendingPost])
def get_trending(limit: int = Query(default=5, ge=1, le=20), db: Session = Depends(get_db)):
    """Public — most-engaged recent posts, ranked by comments + reactions."""
    return dashboard_service.get_trending_posts(db, limit=limit)


@router.get("/dashboard/leaderboard", response_model=list[LeaderboardEntry])
def get_leaderboard(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)):
    """Public — every citizen's wallet balance, richest first."""
    return dashboard_service.get_leaderboard(db, limit=limit)


@router.get("/timeline", response_model=TimelineListResponse)
def get_timeline(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Public — the Simulation Timeline (SDD §9): milestone events in
    reverse-chronological order, optionally filtered by category
    ('population', 'richest_citizen', 'happiness')."""
    items, total = dashboard_service.get_timeline(db, page=page, page_size=page_size, category=category)
    return {"total": total, "items": items}
