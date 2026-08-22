"""
The gender vocabulary, in one place.

Same role as `jobs.py` and `neighborhoods.py`: a small closed vocabulary that
the schema layer validates against and that the API hands to the frontend, so
no dropdown anywhere hardcodes a list that could drift from what the backend
actually accepts.

WHY `unknown` EXISTS AND IS THE DEFAULT
--------------------------------------
Every citizen in an existing database predates this column. There is no honest
way to guess the gender of a citizen whose name an admin typed by hand, so the
migration backfills what it can from the generator's own name pools and leaves
everyone else `unknown` for an admin to correct. Making the column NOT NULL with
an `unknown` default rather than nullable means demographics counting never has
to special-case NULL, and "not recorded" stays visible in the numbers instead of
silently disappearing.

WHY IT IS A PLAIN STRING AND NOT A DATABASE ENUM
------------------------------------------------
Every other closed vocabulary in this project (`citizens.job`,
`buildings.type`, `neighborhoods.type`, `timeline_events.category`) is a
`String` validated in Python. Adding a value to a MySQL ENUM needs a migration;
adding one here needs one line. Consistency with the rest of the schema wins,
and Pydantic is doing the enforcing either way.
"""

GENDER_MALE = "male"
GENDER_FEMALE = "female"
GENDER_OTHER = "other"
GENDER_UNKNOWN = "unknown"

# Order matters: this is the order the API returns them in and therefore the
# order they appear in the admin dropdown. `unknown` is last because it is the
# fallback, not a choice anyone should make first.
GENDER_NAMES = [GENDER_MALE, GENDER_FEMALE, GENDER_OTHER, GENDER_UNKNOWN]

GENDER_LABELS = {
    GENDER_MALE: "Male",
    GENDER_FEMALE: "Female",
    GENDER_OTHER: "Other",
    GENDER_UNKNOWN: "Not recorded",
}

# The two genders the demographics panel charts separately. `other` and
# `unknown` are still counted and still returned — they are just not part of the
# male/female comparison the user asked to see, and lumping them into either
# side would make that comparison a lie.
BINARY_GENDERS = (GENDER_MALE, GENDER_FEMALE)

DEFAULT_GENDER = GENDER_UNKNOWN


def label_for(gender: str) -> str:
    """Display label for a stored value, falling back to the raw value.

    Falls back rather than raising because this is called on the read path: a
    row that somehow holds an unrecognised value should still render, not 500
    the whole citizens list.
    """
    return GENDER_LABELS.get(gender, gender)
