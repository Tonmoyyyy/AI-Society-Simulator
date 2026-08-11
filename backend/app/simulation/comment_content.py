import random

_TEMPLATES = [
    "Totally agree with this.",
    "Never thought about it that way.",
    "This made my day a little better.",
    "Same here, honestly.",
    "Interesting take!",
    "Sending good energy your way.",
    "Couldn't have said it better myself.",
]


def generate_comment_content() -> str:
    """v0.1 comment content is templated, same reasoning as post_content.py —
    no generation model yet, intentionally."""
    return random.choice(_TEMPLATES)
