"""
The world's layout vocabulary and its default starting blueprint.

Single source of truth for district types so the backend, the seeder and the
(future) Three.js renderer never drift apart — exactly the same pattern as
simulation/jobs.py and simulation/neighborhoods.py.

--------------------------------------------------------------------------
ON "CITY NAMES MUST NOT BE HARDCODED"
--------------------------------------------------------------------------
DEFAULT_WORLD below is a *first-boot seed*, not a hardcoded world. It is read
exactly once — when the cities table is empty — and after that the DATABASE is
the only source of truth. The frontend never sees this file; it reads
/api/v1/world. Renaming a city via PATCH /api/v1/world/cities/{id} changes the
name everywhere with no code change, and the rename survives restarts because
the seeder is a no-op once cities exist.

The alternative (an empty world on first boot) would mean nobody can see
anything until they manually create four cities by hand, which makes the
feature look broken. The shop system already made this exact call — see
simulation/seed_shops.py.

--------------------------------------------------------------------------
ON DETERMINISM
--------------------------------------------------------------------------
Every coordinate here is a fixed literal. Nothing is randomised, so a
citizen's city never moves between restarts. Positions are written to the DB
at seed time and read back from the DB afterwards; this file is not consulted
again. (Phase 2 adds per-building/per-home coordinate generation, which will
be seeded from a stable key rather than an unseeded RNG for the same reason.)

Coordinates are on the Three.js XZ ground plane (Y is the up axis, so the
ground is XZ). Districts are stored as offsets from their city centre.
"""

# ---- district types (the `neighborhoods.type` vocabulary) ----
#
# Rendering hints only — the simulation itself doesn't branch on these yet.
# Kept as plain strings (not a DB enum) to match how the project already
# stores job / category / event_type / current_activity, and because adding a
# new district type should not require an ALTER TABLE.

DISTRICT_PRESIDENTIAL = "presidential"
DISTRICT_GOVERNMENT = "government"
DISTRICT_CENTRAL = "central"
DISTRICT_RESIDENTIAL = "residential"
DISTRICT_COMMERCIAL = "commercial"
DISTRICT_WORKER = "worker"
DISTRICT_INDUSTRIAL = "industrial"
DISTRICT_PARK = "park"

DISTRICT_TYPES = [
    DISTRICT_PRESIDENTIAL,
    DISTRICT_GOVERNMENT,
    DISTRICT_CENTRAL,
    DISTRICT_RESIDENTIAL,
    DISTRICT_COMMERCIAL,
    DISTRICT_WORKER,
    DISTRICT_INDUSTRIAL,
    DISTRICT_PARK,
]

# Legend metadata, served by GET /api/v1/world/district-types so the map
# legend is generated from backend data instead of being retyped in HTML.
#
# `color` is the flat plate colour the renderer tints the district's ground
# with — it lives here, next to the label and icon, so the whole palette is
# backend-owned. Adding a district type therefore needs no frontend edit
# (§4, §11).
DISTRICT_TYPE_LABELS = {
    DISTRICT_PRESIDENTIAL: {"label": "Presidential Area", "icon": "\U0001F451", "color": "#d9c98f"},  # crown
    DISTRICT_GOVERNMENT: {"label": "Government", "icon": "\U0001F3DB", "color": "#c6cfdd"},           # classical building
    DISTRICT_CENTRAL: {"label": "Central", "icon": "\U0001F306", "color": "#bfc6d2"},                 # cityscape at dusk
    DISTRICT_RESIDENTIAL: {"label": "Residential", "icon": "\U0001F3E0", "color": "#cdd7b8"},         # house
    DISTRICT_COMMERCIAL: {"label": "Commercial", "icon": "\U0001F3EA", "color": "#e3cf9f"},           # convenience store
    DISTRICT_WORKER: {"label": "Worker", "icon": "\U0001F477", "color": "#cfc7b4"},                   # worker
    DISTRICT_INDUSTRIAL: {"label": "Industrial", "icon": "\U0001F3ED", "color": "#b6b8bc"},           # factory
    DISTRICT_PARK: {"label": "Park", "icon": "\U0001F333", "color": "#a8cf9c"},                       # tree
}


# ---- default first-boot world ----
#
# Four cities laid out around the capital at the origin. The capital is the
# only city with a presidential district — that's what `is_capital` marks.

DEFAULT_WORLD = [
    {
        "name": "Tonmoy Capital",
        "region": "Capital Region",
        "description": "Seat of government and the most populous city in the society.",
        "world_x": 0.0,
        "world_z": 0.0,
        "radius": 170.0,
        "is_capital": True,
        "neighborhoods": [
            {
                "name": "Presidential District",
                "type": DISTRICT_PRESIDENTIAL,
                "description": "Home of the Presidential Palace and the Parliament.",
                "offset_x": 0.0,
                "offset_z": -110.0,
                "width": 150.0,
                "depth": 85.0,
            },
            {
                "name": "Central District",
                "type": DISTRICT_CENTRAL,
                "description": "The administrative and civic heart of the capital.",
                "offset_x": 0.0,
                "offset_z": -10.0,
                "width": 125.0,
                "depth": 80.0,
            },
            {
                "name": "Commercial District",
                "type": DISTRICT_COMMERCIAL,
                "description": "Markets, shops and trade.",
                "offset_x": -105.0,
                "offset_z": 65.0,
                "width": 90.0,
                "depth": 70.0,
            },
            {
                "name": "Residential District",
                "type": DISTRICT_RESIDENTIAL,
                "description": "Where most citizens of the capital live.",
                "offset_x": 0.0,
                "offset_z": 95.0,
                "width": 115.0,
                "depth": 70.0,
            },
            {
                "name": "Worker District",
                "type": DISTRICT_WORKER,
                "description": "Dense housing for the capital's workforce.",
                "offset_x": 105.0,
                "offset_z": 65.0,
                "width": 90.0,
                "depth": 70.0,
            },
        ],
    },
    {
        "name": "Nova City",
        "region": "Eastern Region",
        "description": "A fast-growing modern city east of the capital.",
        "world_x": 430.0,
        "world_z": -120.0,
        "radius": 125.0,
        "is_capital": False,
        "neighborhoods": [
            {
                "name": "Central District",
                "type": DISTRICT_CENTRAL,
                "description": "Nova City's civic centre.",
                "offset_x": 0.0,
                "offset_z": -45.0,
                "width": 105.0,
                "depth": 70.0,
            },
            {
                "name": "Residential District",
                "type": DISTRICT_RESIDENTIAL,
                "description": "Suburban housing.",
                "offset_x": -70.0,
                "offset_z": 45.0,
                "width": 90.0,
                "depth": 70.0,
            },
            {
                "name": "Commercial District",
                "type": DISTRICT_COMMERCIAL,
                "description": "Shopping and small business.",
                "offset_x": 65.0,
                "offset_z": 45.0,
                "width": 90.0,
                "depth": 70.0,
            },
        ],
    },
    {
        "name": "River City",
        "region": "Western Region",
        "description": "A quieter riverside settlement west of the capital.",
        "world_x": -410.0,
        "world_z": 160.0,
        "radius": 125.0,
        "is_capital": False,
        "neighborhoods": [
            {
                "name": "Central District",
                "type": DISTRICT_CENTRAL,
                "description": "River City's town centre.",
                "offset_x": 0.0,
                "offset_z": -45.0,
                "width": 105.0,
                "depth": 70.0,
            },
            {
                "name": "Residential District",
                "type": DISTRICT_RESIDENTIAL,
                "description": "Riverside homes.",
                "offset_x": -65.0,
                "offset_z": 45.0,
                "width": 90.0,
                "depth": 70.0,
            },
            {
                "name": "Riverside Park",
                "type": DISTRICT_PARK,
                "description": "Green space along the river.",
                "offset_x": 65.0,
                "offset_z": 45.0,
                "width": 85.0,
                "depth": 70.0,
            },
        ],
    },
    {
        "name": "Industrial City",
        "region": "Southern Region",
        "description": "The society's manufacturing and heavy-industry hub.",
        "world_x": 180.0,
        "world_z": 440.0,
        "radius": 135.0,
        "is_capital": False,
        "neighborhoods": [
            {
                "name": "Industrial District",
                "type": DISTRICT_INDUSTRIAL,
                "description": "Factories and warehouses.",
                "offset_x": 0.0,
                "offset_z": -50.0,
                "width": 125.0,
                "depth": 80.0,
            },
            {
                "name": "Worker District",
                "type": DISTRICT_WORKER,
                "description": "Housing for factory workers.",
                "offset_x": -72.0,
                "offset_z": 55.0,
                "width": 95.0,
                "depth": 70.0,
            },
            {
                "name": "Commercial District",
                "type": DISTRICT_COMMERCIAL,
                "description": "Local shops serving the workforce.",
                "offset_x": 72.0,
                "offset_z": 55.0,
                "width": 85.0,
                "depth": 70.0,
            },
        ],
    },
]
