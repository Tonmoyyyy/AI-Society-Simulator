import random
from typing import Optional

from app.simulation.genders import (
    GENDER_FEMALE,
    GENDER_MALE,
    GENDER_UNKNOWN,
)

_FIRST_NAMES = [
    "Aiden", "Maya", "Rahim", "Priya", "Leo", "Sara", "Kenji", "Nadia",
    "Omar", "Elena", "Fatima", "Hiro", "Amara", "Diego", "Zara", "Noah",
    "Layla", "Mateo", "Ines", "Yusuf",
]
_LAST_NAMES = [
    "Rahman", "Silva", "Novak", "Chen", "Karim", "Rossi", "Haque", "Petrov",
    "Suzuki", "Khan", "Costa", "Ito", "Ahmed", "Kowalski", "Sato", "Islam",
]

# ---------------------------------------------------------------------------
# Gendered first-name pools
# ---------------------------------------------------------------------------
# These two lists PARTITION `_FIRST_NAMES` — every name above appears in exactly
# one of them, and neither contains a name that is not above. That invariant is
# what lets `infer_gender_from_name` classify a citizen the generator produced,
# and it is pinned by a test (`test_gendered_pools_partition_first_names`) so a
# future edit to one list without the other fails loudly instead of silently
# creating a name the inference can never classify.
#
# `_FIRST_NAMES` is deliberately left as its own literal rather than being
# rebuilt from these two by concatenation: `generate_name()` predates this
# change and callers rely on it, so its behaviour is kept exactly as it was.
_MALE_FIRST_NAMES = [
    "Aiden", "Rahim", "Leo", "Kenji", "Omar", "Hiro", "Diego", "Noah",
    "Mateo", "Yusuf",
]
_FEMALE_FIRST_NAMES = [
    "Maya", "Priya", "Sara", "Nadia", "Elena", "Fatima", "Amara", "Zara",
    "Layla", "Ines",
]

# Built once at import, not per call. Keys are lowercased so a hand-typed
# "maya rahman" still classifies.
_FIRST_NAME_GENDERS: dict[str, str] = {
    **{n.lower(): GENDER_MALE for n in _MALE_FIRST_NAMES},
    **{n.lower(): GENDER_FEMALE for n in _FEMALE_FIRST_NAMES},
}


def generate_name() -> str:
    """A random full name with no gender attached.

    KEPT FOR COMPATIBILITY and still the right function to call when gender is
    irrelevant. Prefer `generate_person()` when creating a citizen, so the name
    and the recorded gender agree with each other.
    """
    return f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}"


def generate_name_for_gender(gender: str) -> str:
    """A random full name drawn from the pool matching `gender`.

    Falls back to the mixed pool for `other` / `unknown` / anything
    unrecognised, because there is no pool for those and inventing one would be
    a guess dressed up as data.
    """
    if gender == GENDER_MALE:
        pool = _MALE_FIRST_NAMES
    elif gender == GENDER_FEMALE:
        pool = _FEMALE_FIRST_NAMES
    else:
        pool = _FIRST_NAMES
    return f"{random.choice(pool)} {random.choice(_LAST_NAMES)}"


def generate_person(gender: Optional[str] = None) -> tuple[str, str]:
    """Return a `(name, gender)` pair that agrees with itself.

    This is what citizen creation should call. Pass a `gender` to pick a name to
    match it; pass nothing and a gender is chosen first, then a matching name —
    which is why an auto-generated population comes out roughly balanced instead
    of accumulating `unknown` rows nobody ever fixes.

    Only male/female are auto-assigned. `other` is a real option an admin can
    set, but the simulation has no basis for assigning it to a randomly
    generated person, so it is never guessed.
    """
    if gender is None:
        gender = random.choice([GENDER_MALE, GENDER_FEMALE])
    return generate_name_for_gender(gender), gender


def infer_gender_from_name(name: str) -> str:
    """Best-effort gender for an existing name, or `unknown`.

    Used by the migration to backfill citizens created before the column
    existed, and by citizen creation when a caller supplies a name but no
    gender. It only recognises first names from this module's own pools — an
    admin-typed name it has never seen returns `unknown` rather than a guess.
    Nothing downstream treats `unknown` as an error; it is a value an admin can
    correct from the citizen editor.
    """
    if not name:
        return GENDER_UNKNOWN
    first = name.strip().split(" ")[0].lower()
    return _FIRST_NAME_GENDERS.get(first, GENDER_UNKNOWN)
