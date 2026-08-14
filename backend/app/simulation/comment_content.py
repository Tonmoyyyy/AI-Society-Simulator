import random

# Three personality-influenced pools instead of one flat list — this was
# the direct fix for "conversations feel monotonous, same text repeating."
# Honest citizens skew blunter, social citizens skew more enthusiastic,
# everyone else draws from a large warm/neutral pool. Combined with the
# reply_to_name addressing below, this gives real variety instead of N
# citizens all saying the same 7 lines on repeat.

_WARM_REACTIONS = [
    "Totally agree with this.",
    "Never thought about it that way!",
    "This made my day a little better.",
    "Same here, honestly.",
    "That's such an interesting take.",
    "Sending good energy your way.",
    "Couldn't have said it better myself.",
    "This hit different today.",
    "Not gonna lie, I needed to read this.",
    "This is exactly how I feel too.",
    "I've been thinking the same thing lately.",
    "You always know what to say.",
    "This made me smile, thank you.",
    "Real talk, this resonates.",
    "I'm saving this one.",
    "Okay this is actually so relatable.",
    "Appreciate you sharing this.",
    "Big mood, honestly.",
]

_DIRECT_REACTIONS = [
    "Not sure I agree, but okay.",
    "Eh, seen better takes.",
    "Fair point, I guess.",
    "Sure, if you say so.",
    "Makes sense to me.",
    "Can't argue with that.",
    "Noted.",
    "Interesting. Not my thing, but interesting.",
]

_ENTHUSIASTIC_REACTIONS = [
    "YES exactly this!!",
    "Omg same!!",
    "This is everything.",
    "Screaming, I love this.",
    "Obsessed with this energy.",
    "Wait this is so real.",
]


def generate_comment_content(personality: dict | None = None, reply_to_name: str | None = None) -> str:
    """Templated (no generation model yet, same reasoning as post_content.py),
    but personality-influenced and combinatorial with reply addressing —
    two citizens' comments landing on the exact same wording is now rare
    rather than the norm. If `reply_to_name` is given, this citizen is
    replying within an existing back-and-forth (not just commenting on the
    original post) and addresses that person by name."""
    personality = personality or {}
    honesty = personality.get("honesty", 50)
    social = personality.get("social", 50)

    if honesty > 75 and random.random() < 0.5:
        pool = _DIRECT_REACTIONS
    elif social > 75 and random.random() < 0.5:
        pool = _ENTHUSIASTIC_REACTIONS
    else:
        pool = _WARM_REACTIONS

    reaction = random.choice(pool)

    if reply_to_name and random.random() < 0.6:
        return f"@{reply_to_name} {reaction}"
    return reaction
