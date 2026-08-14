from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.citizen import (
    CitizenCreate,
    CitizenUpdate,
    CitizenOut,
    CitizenListResponse,
)
from app.schemas.simulation import MemoryOut
from app.services import citizen_service, simulation_service
from app.services.citizen_service import CitizenNotFound, CitizenLimitReached
from app.simulation.jobs import JOB_NAMES
from app.simulation.neighborhoods import NEIGHBORHOOD_NAMES
from app.simulation.personality import TRAITS as TRAIT_NAMES

router = APIRouter(prefix="/api/v1/citizens", tags=["citizens"])


@router.post("", response_model=CitizenOut, status_code=status.HTTP_201_CREATED)
def create_citizen(
    payload: CitizenCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # citizen creation is an authenticated action
):
    try:
        citizen = citizen_service.create_citizen(
            db,
            name=payload.name,
            age=payload.age,
            job=payload.job,
            neighborhood=payload.neighborhood,
            personality_json=payload.personality_json,
        )
    except CitizenLimitReached as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)
    return citizen


@router.get("", response_model=CitizenListResponse)
def list_citizens(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Public read — spectators can browse citizens without logging in."""
    items, total = citizen_service.list_citizens(db, page=page, page_size=page_size)
    return {"total": total, "items": items}


@router.get("/options", response_model=dict)
def get_citizen_options():
    """Public — the valid job/neighborhood/personality-trait values, so the
    frontend's "customize" form never hardcodes a list that could drift
    from the backend's actual validation rules."""
    return {
        "jobs": ["unemployed"] + JOB_NAMES,
        "neighborhoods": NEIGHBORHOOD_NAMES,
        "traits": TRAIT_NAMES,
    }


@router.get("/{citizen_id}", response_model=CitizenOut)
def get_citizen(citizen_id: int, db: Session = Depends(get_db)):
    try:
        citizen = citizen_service.get_citizen(db, citizen_id)
    except CitizenNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    return citizen


@router.patch("/{citizen_id}", response_model=CitizenOut)
def update_citizen(
    citizen_id: int,
    payload: CitizenUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        citizen = citizen_service.update_citizen(
            db,
            citizen_id,
            name=payload.name,
            job=payload.job,
            neighborhood=payload.neighborhood,
            current_activity=payload.current_activity,
        )
    except CitizenNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    return citizen


@router.delete("/{citizen_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_citizen(
    citizen_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        citizen_service.delete_citizen(db, citizen_id)
    except CitizenNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)


@router.get("/{citizen_id}/memories", response_model=list[MemoryOut])
def get_citizen_memories(
    citizen_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Public — a citizen's memory log, most recent first."""
    try:
        citizen_service.get_citizen(db, citizen_id)  # 404s if the citizen doesn't exist
    except CitizenNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    return simulation_service.get_citizen_memories(db, citizen_id, limit=limit)
