from sqlalchemy.orm import Session

from app.models.memory import Memory


def create(
    db: Session,
    citizen_id: int,
    event_type: str,
    description: str,
    importance: int,
    commit: bool = True,
) -> Memory:
    memory = Memory(
        citizen_id=citizen_id,
        event_type=event_type,
        description=description,
        importance=importance,
    )
    db.add(memory)
    if commit:
        db.commit()
        db.refresh(memory)
    return memory


def list_for_citizen(db: Session, citizen_id: int, limit: int = 20) -> list[Memory]:
    return (
        db.query(Memory)
        .filter(Memory.citizen_id == citizen_id)
        .order_by(Memory.created_at.desc())
        .limit(limit)
        .all()
    )
