import random

_TEMPLATES = [
    "Just had a {mood_word} day, feeling {mood_word}!",
    "Thinking about how things are going around the city lately.",
    "Grateful for good friends and good times.",
    "Some days are harder than others, but we push through.",
    "Excited about what's next for me!",
    "Anyone else feel like time is flying by?",
    "Trying to stay positive no matter what.",
]


def generate_post_content(citizen) -> str:
    """Simple v0.1 content generator — templates picked randomly, with a
    mood-derived word substituted in where a template calls for one.
    No LLM/generation model yet, intentionally (see SDD backlog)."""
    if citizen.mood > 0.3:
        mood_word = "great"
    elif citizen.mood < -0.3:
        mood_word = "rough"
    else:
        mood_word = "okay"

    template = random.choice(_TEMPLATES)
    return template.format(mood_word=mood_word) if "{mood_word}" in template else template
