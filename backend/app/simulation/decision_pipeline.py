"""
The per-citizen decision pipeline, run once per citizen per tick.

Stages (see SDD "AI Decision Engine" design):
  1. Perceive   — implicit here: the citizen's current DB state IS the perception,
                   no separate gather step needed at v0.1 scale/complexity.
  2. Generate    — filter ACTIONS to ones valid for this citizen right now.
  3. Score       — utility() for each valid candidate.
  4. Select      — highest utility wins; small personality-driven noise
                    breaks ties instead of pure randomness.
  5. Execute     — mutate citizen state, return what happened (for memory logging).

No cross-citizen conflict resolution needed yet — v0.1 actions are all
single-citizen (work/sleep/eat/socialize/post). That step returns once
Phase 4+ adds actions that touch two citizens at once.
"""

import random

from app.models.citizen import Citizen
from app.simulation.actions import ACTIONS, ActionResult


def decide_and_act(citizen: Citizen) -> ActionResult | None:
    candidates = [a for a in ACTIONS if a.is_valid(citizen)]
    if not candidates:
        # Nothing valid to do (e.g. exhausted and unemployed) — idle this tick.
        citizen.current_activity = "idle"
        return None

    # Small personality-driven noise avoids identical citizens always picking
    # the exact same action in lockstep, without making the choice random.
    noise_scale = 1 + (citizen.personality_json.get("intelligence", 50) / 200)
    scored = [
        (action, action.utility(citizen) + random.uniform(0, noise_scale))
        for action in candidates
    ]
    best_action, _ = max(scored, key=lambda pair: pair[1])
    return best_action.execute(citizen)
