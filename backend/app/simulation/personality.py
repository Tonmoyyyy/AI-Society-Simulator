import random

# The fixed trait set for v0.1 (see SDD §5 — personality_json format).
# Every citizen gets exactly these five traits, each a 0-100 int score.
TRAITS = ["kindness", "intelligence", "ambition", "social", "honesty"]


def generate_personality() -> dict:
    """
    Produces a randomized-but-structured personality: each trait is drawn
    from a normal distribution centered at 50 (clamped to 0-100), so most
    citizens land in a plausible middle range with some genuinely extreme
    outliers — not a flat uniform 0-100 roll, which would make "very kind"
    or "very ambitious" citizens no rarer than average ones.
    """
    personality = {}
    for trait in TRAITS:
        score = int(random.gauss(mu=50, sigma=20))
        personality[trait] = max(0, min(100, score))
    return personality
