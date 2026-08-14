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
    # Passive drift toward baseline — without this, one good socialize
    # session pushes happiness near 100 and it stays there permanently
    # (nothing ever pulls it back down), which kills socialize's own
    # utility (driven by the happiness gap) for good after the first few
    # ticks. Real needs decay over time; this keeps socializing something
    # citizens periodically need to do again, not a one-time event. Kept
    # gentle (3% of the gap per tick) so it's a slow drift, not a state
    # reset.
    citizen.happiness = citizen.happiness + (50.0 - citizen.happiness) * 0.03
    citizen.mood = citizen.mood + (0.0 - citizen.mood) * 0.03

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
