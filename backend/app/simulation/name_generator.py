import random

_FIRST_NAMES = [
    "Aiden", "Maya", "Rahim", "Priya", "Leo", "Sara", "Kenji", "Nadia",
    "Omar", "Elena", "Fatima", "Hiro", "Amara", "Diego", "Zara", "Noah",
    "Layla", "Mateo", "Ines", "Yusuf",
]
_LAST_NAMES = [
    "Rahman", "Silva", "Novak", "Chen", "Karim", "Rossi", "Haque", "Petrov",
    "Suzuki", "Khan", "Costa", "Ito", "Ahmed", "Kowalski", "Sato", "Islam",
]


def generate_name() -> str:
    return f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}"
