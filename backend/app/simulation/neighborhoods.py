"""
The city's neighborhoods — cosmetic/flavor for v0.1 (no commute time, rent,
or district-level economy tied to these yet), assigned randomly at citizen
creation unless the creator picks one. Single source of truth so the
citizen-creation form (frontend) and citizen_service's random assignment
never drift apart — same pattern as simulation/jobs.py.
"""

NEIGHBORHOOD_NAMES = [
    "Downtown",
    "Riverside",
    "Uptown",
    "Old Town",
    "Harbor District",
    "Hillside",
    "Greenwood",
]
