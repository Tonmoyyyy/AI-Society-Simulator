"""
Aging and natural death — the two things that make a population change on its own.

WHY THIS IS A SEPARATE MODULE
-----------------------------
`engine.py` is an orchestrator: it walks the citizens, calls into a behaviour
module, and batches one commit. Every behaviour it calls lives in its own module
(decision_pipeline, gifting, shopping, social_interactions, salary), and mortality
follows that convention rather than adding two more branches to the loop.

The functions here are DELIBERATELY PURE — they take a citizen and a tick number
and return a decision. None of them touch the database, commit, or write a
timeline event. That is the engine's job, because the engine owns the tick's single
commit and its rollback path, and a repository call from inside here would break
both. It also means every rule below can be tested by constructing a citizen
object with no database at all.

DETERMINISM, AND WHERE IT DOES AND DOES NOT APPLY
-------------------------------------------------
The world generator is deterministic on purpose: the same database must always
produce the same city layout, so a citizen's house does not move when the server
restarts. THE SIMULATION IS NOT, and never has been — `decide_and_act`,
`perform_shopping` and `perform_gift` all roll dice. Death is a simulation event,
not world geometry, so it uses `random` like its neighbours. What IS deterministic
here is *when* a citizen has their birthday, which is derived from their id so it
needs no stored state and cannot drift.

TURNING IT OFF
--------------
`settings.NATURAL_DEATH_ENABLED = False` freezes aging and stops the engine
killing anyone. An admin can still record deaths by hand — this governs only what
the simulation does unprompted, which matters when you are testing something else
and would rather the population held still.
"""

import random
from typing import Optional

from app.core.config import settings
from app.models.citizen import Citizen

# Cause strings the engine records in `citizens.death_cause` and in the timeline.
# Fixed values rather than free text, unlike an admin-recorded death, so that
# "how many citizens died of old age" stays answerable with a GROUP BY.
CAUSE_OLD_AGE = "old age"
CAUSE_ILL_HEALTH = "ill health"

# Annual death risk added per year lived beyond settings.NATURAL_DEATH_START_AGE.
# At the threshold itself the risk is one unit (3% a year); ten years past it, 33%.
# Chosen so a population seeded at 18-70 thins out gradually over many simulated
# years instead of collapsing, and so the curve needs no tuning table.
_ANNUAL_RISK_PER_YEAR_OVER = 0.03

# Nobody's annual risk reaches certainty before MAX_CITIZEN_AGE, which is the only
# hard stop. Without this cap the linear curve would pass 100% around age 103 and
# the explicit ceiling would never be the thing that actually applied.
_MAX_ANNUAL_RISK = 0.95


def is_birthday(citizen: Citizen, tick_number: int) -> bool:
    """Whether this tick is the moment `citizen` gains a year.

    STAGGERED BY ID so the whole society does not age in the same instant. The
    offset is `citizen.id % TICKS_PER_YEAR_OF_AGE`, which is deterministic, needs
    no stored birthday column, and spreads birthdays evenly across the simulated
    year.

    NOBODY AGES DURING THE FIRST SIMULATED YEAR (`tick_number >=
    TICKS_PER_YEAR_OF_AGE`). Two reasons, and the second is the load-bearing one:
    a citizen created at age 40 turning 41 an hour later reads as a bug, and
    without the guard citizen 1 would have a birthday on tick 1, which would make
    age unstable across the very first tick of any fresh database.

    The trade-off, stated plainly: the offset is keyed to the GLOBAL tick counter
    rather than to when each citizen was created, so a citizen born late in a year
    may wait less than a full year for their first birthday. Fixing that properly
    needs a `born_at_tick` column, which is not worth a migration for a cosmetic
    difference in the first year of a citizen's life.
    """
    period = settings.TICKS_PER_YEAR_OF_AGE
    if period <= 0:  # a misconfiguration; treat as "aging disabled" rather than crash
        return False
    if tick_number < period:
        return False
    return tick_number % period == citizen.id % period


def apply_aging(citizen: Citizen, tick_number: int) -> bool:
    """Increment `age` if this tick is the citizen's birthday. Returns whether it did.

    This is the first code in the project that ever mutates `citizen.age` — it was
    set once at creation and never touched again. The caller is responsible for the
    `db.add`; this only changes the attribute.
    """
    if not settings.NATURAL_DEATH_ENABLED:
        return False
    if not is_birthday(citizen, tick_number):
        return False
    citizen.age += 1
    return True


def annual_death_risk(age: int) -> float:
    """The chance of dying within a year at a given age, as a 0.0-1.0 fraction.

    Zero below settings.NATURAL_DEATH_START_AGE, then linear. Exposed separately
    from `check_death` so the curve can be asserted in a test without dice: the
    randomness is in the caller, the shape of the risk is here.
    """
    over = age - settings.NATURAL_DEATH_START_AGE
    if over < 0:
        return 0.0
    return min((over + 1) * _ANNUAL_RISK_PER_YEAR_OVER, _MAX_ANNUAL_RISK)


def check_death(citizen: Citizen, rng: Optional[random.Random] = None) -> Optional[str]:
    """The cause of death if this citizen dies on this tick, otherwise None.

    Three ways to die, checked in order of certainty:

      1. HEALTH AT OR BELOW settings.CRITICAL_HEALTH — certain, and immediate.
         Nothing in the tick engine currently drains health, so in practice this
         fires only when an admin sets a critical value from the citizen editor.
         That is deliberate: it makes `health` mean something the moment anything
         starts reducing it, without changing existing simulation behaviour now.

      2. AGE AT OR ABOVE settings.MAX_CITIZEN_AGE — certain. A hard ceiling so the
         risk curve can stay gentle without ever permitting a 300-year-old.

      3. OTHERWISE A ROLL against the per-tick share of `annual_death_risk`. The
         annual figure is divided by TICKS_PER_YEAR_OF_AGE because this is
         evaluated once per tick, and dividing is what stops a 3%-per-year risk
         being applied 720 times a year and killing everyone in a month.

    `rng` is injectable so a test can force or forbid a death without monkeypatching
    the module. Defaults to the shared `random` module, which is what every other
    simulation module uses.
    """
    if not settings.NATURAL_DEATH_ENABLED:
        return None

    if citizen.health <= settings.CRITICAL_HEALTH:
        return CAUSE_ILL_HEALTH

    if citizen.age >= settings.MAX_CITIZEN_AGE:
        return CAUSE_OLD_AGE

    annual = annual_death_risk(citizen.age)
    if annual <= 0.0:
        return None

    period = settings.TICKS_PER_YEAR_OF_AGE
    per_tick = annual / period if period > 0 else annual
    roller = rng if rng is not None else random
    if roller.random() < per_tick:
        return CAUSE_OLD_AGE
    return None


def death_headline(citizen: Citizen, cause: str) -> tuple[str, str]:
    """`(title, description)` for the timeline event a death produces.

    Built here rather than in the engine so the wording lives next to the rules
    that decide a death, and so a test can assert the text without running a tick.
    """
    title = f"{citizen.name} has died"
    description = (
        f"{citizen.name}, aged {citizen.age}, died of {cause}. "
        f"They worked as a {citizen.job}."
    )
    return title, description
