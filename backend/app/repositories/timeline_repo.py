from typing import Optional

from sqlalchemy.orm import Session

from app.models.timeline_event import TimelineEvent


def create(
    db: Session,
    tick_number: int,
    category: str,
    title: str,
    description: str,
    payload: Optional[dict] = None,
    commit: bool = True,
) -> TimelineEvent:
    event = TimelineEvent(
        tick_number=tick_number,
        category=category,
        title=title,
        description=description,
        payload_json=payload,
    )
    db.add(event)
    if commit:
        db.commit()
        db.refresh(event)
    return event


def exists_with_title(db: Session, title: str) -> bool:
    return db.query(TimelineEvent).filter(TimelineEvent.title == title).first() is not None


def get_latest_by_category(db: Session, category: str) -> Optional[TimelineEvent]:
    return (
        db.query(TimelineEvent)
        .filter(TimelineEvent.category == category)
        .order_by(TimelineEvent.id.desc())
        .first()
    )


def list_paginated(
    db: Session, offset: int, limit: int, category: Optional[str] = None
) -> tuple[list[TimelineEvent], int]:
    query = db.query(TimelineEvent)
    if category:
        query = query.filter(TimelineEvent.category == category)
    # NOTE: previously used query.with_entities(func.count()).scalar(),
    # which generates a bare "SELECT count(*)" with NO FROM clause once
    # with_entities() drops the query's table context — MySQL happily
    # returns 1 for that (counting one implicit row of constants),
    # completely disconnected from the actual table. query.count() is the
    # correct way to count a filtered ORM query; it preserves the FROM
    # clause and any .filter() already applied.
    total = query.count()
    items = query.order_by(TimelineEvent.id.desc()).offset(offset).limit(limit).all()
    return items, total
