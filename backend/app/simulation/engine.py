"""
The tick orchestrator. One call to run_tick() = one simulated hour
(see SDD Simulation Configuration). This is what both the manual
POST /api/v1/simulation/tick endpoint and the APScheduler background
job call — same code path either way, so "trigger a tick by hand" and
"let it run automatically" can never drift apart.

THE DEAD DO NOT GET TURNS. The citizen query below filters on `is_alive`, which
is the single most important line in this file for the death feature: it excludes
the deceased from acting, from posting, from earning, from shopping, and from
being picked as anyone else's social or gift target (the same list is passed as
the candidate pool). Filtering here rather than in five places downstream is why
that holds.
"""

import random
from sqlalchemy.orm import Session

from app.models.citizen import Citizen
from app.repositories import (
    citizen_repo,
    memory_repo,
    simulation_tick_repo,
    social_repo,
    timeline_repo,
)
from app.simulation import milestones, mortality
from app.simulation.decision_pipeline import decide_and_act
from app.simulation.gifting import perform_gift
from app.simulation.post_content import generate_post_content
from app.simulation.salary import calculate_salary
from app.simulation.shopping import perform_shopping
from app.simulation.social_interactions import perform_social_interaction
from app.services import government_service, wallet_service
from app.websocket.connection_manager import manager


def run_tick(db: Session) -> dict:
    tick = simulation_tick_repo.start_tick(db)

    # LIVING CITIZENS ONLY. A soft-deleted (deceased) citizen keeps their row, so
    # an unfiltered `db.query(Citizen).all()` — which is what this was — would
    # keep giving the dead turns forever.
    citizens = db.query(Citizen).filter(Citizen.is_alive.is_(True)).all()
    processed = 0
    new_posts: list[tuple[str, object]] = []  # (citizen_name, Post) — broadcast after commit
    broadcast_queue: list[dict] = []  # social-interaction + purchase events — broadcast after commit
    deaths: list[dict] = []  # citizens who died this tick — offices vacated after commit

    try:
        for citizen in citizens:
            # ---- aging and natural death, before the citizen acts ----
            #
            # Checked first so that someone who dies this tick does not also post,
            # work and go shopping in the same hour. Both calls are pure (see
            # simulation/mortality.py); the database work stays here, where the
            # tick's single commit and its rollback path are owned.
            mortality.apply_aging(citizen, tick.tick_number)

            cause = mortality.check_death(citizen)
            if cause is not None:
                citizen_repo.mark_dead(
                    db,
                    citizen,
                    tick_number=tick.tick_number,
                    cause=cause,
                    commit=False,  # batch-committed once below, like every other write here
                )
                title, description = mortality.death_headline(citizen, cause)
                timeline_repo.create(
                    db,
                    tick_number=tick.tick_number,
                    category="death",
                    title=title,
                    description=description,
                    payload={
                        "citizen_id": citizen.id,
                        "name": citizen.name,
                        "age": citizen.age,
                        "cause": cause,
                    },
                    commit=False,
                )
                deaths.append(
                    {
                        "citizen_id": citizen.id,
                        "name": citizen.name,
                        "age": citizen.age,
                        "cause": cause,
                        "title": title,
                        "description": description,
                    }
                )
                processed += 1
                continue

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

            # ---- Custom Jobs Processing (Thief & Bhikkhuk) ----
            if result is not None and result.memory_event == "stole_money":
                # Find valid targets who are not the thief
                targets = [c for c in citizens if c.id != citizen.id and c.is_alive]
                if targets:
                    victim = random.choice(targets)
                    stolen_amount = random.randint(20, 50)
                    
                    # Process money transfer safely
                    wallet_service.withdraw(db, victim.id, stolen_amount, commit=False)
                    wallet_service.deposit(db, citizen.id, stolen_amount, commit=False)

            if result is not None and result.memory_event == "begged_alms":
                # Find generous citizens around
                donors = [c for c in citizens if c.id != citizen.id and c.is_alive]
                if donors:
                    donor = random.choice(donors)
                    alms_amount = random.randint(5, 15)
                    
                    wallet_service.withdraw(db, donor.id, alms_amount, commit=False)
                    wallet_service.deposit(db, citizen.id, alms_amount, commit=False)

            # Secondary effects — layered on top of the primary action FSM
            if result is not None and result.memory_event == "socialized":
                perform_social_interaction(db, citizen, citizens, broadcast_queue)
            perform_shopping(db, citizen, broadcast_queue)
            perform_gift(db, citizen, citizens, broadcast_queue)

            processed += 1

        db.commit()  # one batch commit for the whole tick, not per-citizen
        simulation_tick_repo.finish_tick(db, tick, citizens_processed=processed, status="completed")

        for death in deaths:
            death["vacated_offices"] = government_service.vacate_offices_for_citizen(
                db, death["citizen_id"]
            )

        new_milestones = milestones.run_all_detectors(db, tick.tick_number)
        if new_milestones:
            db.commit()

        # Broadcast websocket events after commit
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

        for death in deaths:
            manager.broadcast_threadsafe({
                "type": "citizen_died",
                "citizen_id": death["citizen_id"],
                "citizen_name": death["name"],
                "age": death["age"],
                "cause": death["cause"],
                "title": death["title"],
                "description": death["description"],
                "vacated_offices": death.get("vacated_offices", []),
            })
    except Exception:
        db.rollback()
        simulation_tick_repo.finish_tick(db, tick, citizens_processed=processed, status="failed")
        raise

    return {
        "tick_number": tick.tick_number,
        "citizens_processed": processed,
        "deaths": len(deaths),
        "status": "completed",
    }