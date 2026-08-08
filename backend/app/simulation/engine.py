"""
The tick orchestrator. One call to run_tick() = one simulated hour
(see SDD Simulation Configuration). This is what both the manual
POST /api/v1/simulation/tick endpoint and the APScheduler background
job call — same code path either way, so "trigger a tick by hand" and
"let it run automatically" can never drift apart.
"""

from sqlalchemy.orm import Session

from app.models.citizen import Citizen
from app.repositories import memory_repo, simulation_tick_repo, social_repo
from app.simulation.decision_pipeline import decide_and_act
from app.simulation.post_content import generate_post_content
from app.simulation.salary import calculate_salary
from app.services import wallet_service
from app.websocket.connection_manager import manager


def run_tick(db: Session) -> dict:
    tick = simulation_tick_repo.start_tick(db)

    citizens = db.query(Citizen).all()
    processed = 0
    new_posts: list[tuple[str, object]] = []  # (citizen_name, Post) — broadcast after commit

    try:
        for citizen in citizens:
            result = decide_and_act(citizen)
            db.add(citizen)  # state mutations (energy/mood/etc.) from the action

            if result is not None and result.memory_event is not None:
                memory_repo.create(
                    db,
                    citizen_id=citizen.id,
                    event_type=result.memory_event,
                    description=result.memory_description,
                    importance=result.memory_importance,
                    commit=False,  # batch-committed once below, not per citizen
                )

            if result is not None and result.memory_event == "created_post":
                content = generate_post_content(citizen)
                post = social_repo.create_post(db, citizen_id=citizen.id, content=content, commit=False)
                new_posts.append((citizen.name, post))

            if result is not None and result.memory_event == "worked":
                salary = calculate_salary(citizen)
                wallet_service.pay_salary(db, citizen.id, salary, commit=False)

            processed += 1

        db.commit()  # one batch commit for the whole tick, not per-citizen
        simulation_tick_repo.finish_tick(db, tick, citizens_processed=processed, status="completed")

        # Broadcast only after the commit succeeds, so a WS client never
        # hears about a post that then gets rolled back.
        for citizen_name, post in new_posts:
            db.refresh(post)
            manager.broadcast_threadsafe({
                "type": "new_post",
                "post_id": post.id,
                "citizen_id": post.citizen_id,
                "citizen_name": citizen_name,
                "content": post.content,
            })
    except Exception:
        db.rollback()
        simulation_tick_repo.finish_tick(db, tick, citizens_processed=processed, status="failed")
        raise

    return {
        "tick_number": tick.tick_number,
        "citizens_processed": processed,
        "status": "completed",
    }
