"""
The v0.1 action catalog. Each action defines:
  - is_valid(citizen): can this action even be taken right now?
  - utility(citizen): how much does the citizen want to take it? (higher wins)
  - execute(citizen, memory_writer): mutate citizen state, optionally log a memory

This is the "utility-scored FSM" from the SDD's AI Decision Engine design —
deliberately simple (no behavior tree, no LLM) so it's cheap to run at
citizen-scale and easy to reason about. See simulation/decision_pipeline.py
for how these get selected each tick.
"""

from dataclasses import dataclass
from typing import Callable

from app.models.citizen import Citizen


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


@dataclass
class ActionResult:
    activity: str
    memory_event: str | None = None
    memory_description: str | None = None
    memory_importance: int = 1


class Action:
    def __init__(
        self,
        name: str,
        is_valid: Callable[[Citizen], bool],
        utility: Callable[[Citizen], float],
        execute: Callable[[Citizen], ActionResult],
    ):
        self.name = name
        self.is_valid = is_valid
        self.utility = utility
        self.execute = execute


def _sleep_utility(c: Citizen) -> float:
    # Wanted more the lower energy is; low-conscientiousness-ish trait (ambition)
    # citizens are slightly more willing to rest instead of pushing through.
    low_ambition_bonus = (100 - c.personality_json.get("ambition", 50)) * 0.05
    return (100 - c.energy) * 1.0 + low_ambition_bonus


def _sleep_execute(c: Citizen) -> ActionResult:
    c.energy = _clamp(c.energy + 30)
    c.current_activity = "sleeping"
    return ActionResult(activity="sleeping")


def _eat_utility(c: Citizen) -> float:
    # Health doubles as our v0.1 stand-in for "hunger" (no dedicated field
    # per the approved schema) — the lower it is, the more eating is wanted.
    return (100 - c.health) * 0.8


def _eat_execute(c: Citizen) -> ActionResult:
    c.health = _clamp(c.health + 15)
    c.energy = _clamp(c.energy + 5)
    c.current_activity = "eating"
    return ActionResult(activity="eating")


def _work_is_valid(c: Citizen) -> bool:
    # Standard jobs (excluding thief, bhikkhuk, unemployed)
    special_jobs = {"unemployed", "thief", "bhikkhuk"}
    return c.job not in special_jobs and c.energy > 20


def _work_utility(c: Citizen) -> float:
    ambition = c.personality_json.get("ambition", 50)
    return ambition * 0.7


def _work_execute(c: Citizen) -> ActionResult:
    c.energy = _clamp(c.energy - 15)
    ambition = c.personality_json.get("ambition", 50)
    c.happiness = _clamp(c.happiness + (ambition - 50) * 0.1)
    c.current_activity = "working"
    return ActionResult(
        activity="working",
        memory_event="worked",
        memory_description=f"{c.name} put in a shift at work.",
        memory_importance=1,
    )


# ------------------------------------------------------------- Custom Jobs Logic

def _steal_is_valid(c: Citizen) -> bool:
    return c.job == "thief" and c.energy > 20


def _steal_utility(c: Citizen) -> float:
    # High ambition + low honesty drives high urge to steal
    ambition = c.personality_json.get("ambition", 50)
    honesty = c.personality_json.get("honesty", 50)
    return (ambition * 0.6) + ((100 - honesty) * 0.4)


def _steal_execute(c: Citizen) -> ActionResult:
    c.energy = _clamp(c.energy - 20)
    c.happiness = _clamp(c.happiness + 10)
    c.mood = _clamp(c.mood - 0.1, lo=-1.0, hi=1.0)
    c.current_activity = "stealing"
    return ActionResult(
        activity="stealing",
        memory_event="stole_money",
        memory_description=f"{c.name} executed a stealthy operation in the city.",
        memory_importance=2,
    )


def _beg_is_valid(c: Citizen) -> bool:
    return c.job == "bhikkhuk" and c.energy > 10


def _beg_utility(c: Citizen) -> float:
    # Low health/energy or low ambition drives begging
    ambition = c.personality_json.get("ambition", 50)
    return (100 - c.energy) * 0.5 + (100 - ambition) * 0.5


def _beg_execute(c: Citizen) -> ActionResult:
    c.energy = _clamp(c.energy - 10)
    c.happiness = _clamp(c.happiness - 2)
    c.current_activity = "begging"
    return ActionResult(
        activity="begging",
        memory_event="begged_alms",
        memory_description=f"{c.name} asked for alms near the public market.",
        memory_importance=1,
    )

# -------------------------------------------------------------------------------


def _socialize_is_valid(c: Citizen) -> bool:
    return c.energy > 15


def _socialize_utility(c: Citizen) -> float:
    social = c.personality_json.get("social", 50)
    happiness_gap = 100 - c.happiness
    return social * 0.65 + happiness_gap * 0.2


def _socialize_execute(c: Citizen) -> ActionResult:
    social = c.personality_json.get("social", 50)
    c.happiness = _clamp(c.happiness + 5 + social * 0.05)
    c.mood = _clamp(c.mood + 0.1, lo=-1.0, hi=1.0)
    c.energy = _clamp(c.energy - 5)
    c.current_activity = "socializing"
    return ActionResult(
        activity="socializing",
        memory_event="socialized",
        memory_description=f"{c.name} spent time with other citizens.",
        memory_importance=1,
    )


def _post_is_valid(c: Citizen) -> bool:
    return c.energy > 10


def _post_utility(c: Citizen) -> float:
    social = c.personality_json.get("social", 50)
    honesty = c.personality_json.get("honesty", 50)
    return social * 0.45 + honesty * 0.15


def _post_execute(c: Citizen) -> ActionResult:
    c.mood = _clamp(c.mood + 0.05, lo=-1.0, hi=1.0)
    c.energy = _clamp(c.energy - 3)
    c.current_activity = "posting"
    return ActionResult(
        activity="posting",
        memory_event="created_post",
        memory_description=f"{c.name} shared a thought with the community.",
        memory_importance=1,
    )


ACTIONS: list[Action] = [
    Action("sleep", is_valid=lambda c: c.energy < 90, utility=_sleep_utility, execute=_sleep_execute),
    Action("eat", is_valid=lambda c: c.health < 90, utility=_eat_utility, execute=_eat_execute),
    Action("work", is_valid=_work_is_valid, utility=_work_utility, execute=_work_execute),
    Action("steal", is_valid=_steal_is_valid, utility=_steal_utility, execute=_steal_execute),
    Action("beg", is_valid=_beg_is_valid, utility=_beg_utility, execute=_beg_execute),
    Action("socialize", is_valid=_socialize_is_valid, utility=_socialize_utility, execute=_socialize_execute),
    Action("create_post", is_valid=_post_is_valid, utility=_post_utility, execute=_post_execute),
]