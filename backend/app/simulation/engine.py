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
from app.simulation import milestones
from app.simulation.decision_pipeline import decide_and_act
from app.simulation.gifting import perform_gift
from app.simulation.post_content import generate_post_content
from app.simulation.salary import calculate_salary
from app.simulation.shopping import perform_shopping
from app.simulation.social_interactions import perform_social_interaction
from app.services import wallet_service
from app.websocket.connection_manager import manager


def run_tick(db: Session) -> dict:
    tick = simulation_tick_repo.start_tick(db)

    citizens = db.query(Citizen).all()
    processed = 0
    new_posts: list[tuple[str, object]] = []  # (citizen_name, Post) — broadcast after commit
    broadcast_queue: list[dict] = []  # social-interaction + purchase events — broadcast after commit

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

            # Secondary effects — layered on top of the primary action FSM,
            # not competing actions in it (see each module's docstring for
            # why). "socialize" gains a real target; every citizen
            # independently has a modest chance to shop regardless of
            # their primary action this tick.
            if result is not None and result.memory_event == "socialized":
                perform_social_interaction(db, citizen, citizens, broadcast_queue)
            perform_shopping(db, citizen, broadcast_queue)
            perform_gift(db, citizen, citizens, broadcast_queue)

            processed += 1

        db.commit()  # one batch commit for the whole tick, not per-citizen
        simulation_tick_repo.finish_tick(db, tick, citizens_processed=processed, status="completed")

        # Milestone detectors run against final post-tick state (population,
        # richest citizen, average happiness) — see simulation/milestones.py.
        # Committed separately since they depend on the tick's own commit
        # having already landed (e.g. updated wallet balances).
        new_milestones = milestones.run_all_detectors(db, tick.tick_number)
        if new_milestones:
            db.commit()

        # Broadcast only after the commit succeeds, so a WS client never
        # hears about something that then gets rolled back.
        for citizen_name, post in new_posts:
            db.refresh(post)
            manager.broadcast_threadsafe({
                "type": "new_post",
                "post_id": post.id,
                "citizen_id": post.citizen_id,
                "citizen_name": citizen_name,
                "content": post.content,
            })
        for event in new_milestones:
            db.refresh(event)
            manager.broadcast_threadsafe({
                "type": "new_milestone",
                "category": event.category,
                "title": event.title,
                "description": event.description,
            })
        for event in broadcast_queue:
            manager.broadcast_threadsafe(event)
    except Exception:
        db.rollback()
        simulation_tick_repo.finish_tick(db, tick, citizens_processed=processed, status="failed")
        raise

    return {
        "tick_number": tick.tick_number,
        "citizens_processed": processed,
        "status": "completed",
    }
