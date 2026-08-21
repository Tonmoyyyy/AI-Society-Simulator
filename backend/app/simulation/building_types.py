"""
The building vocabulary + the render hints that go with it (World Phase 2).

Single source of truth, same pattern as simulation/jobs.py,
simulation/neighborhoods.py and simulation/world_layout.py. The renderer never
hardcodes a size or a colour: it reads them from GET /api/v1/world/building-types,
so adding "school" or "hospital" later is a change in THIS FILE ONLY — no
ALTER TABLE, no frontend edit.

`type` is stored as a plain String(30) on `buildings` (not a DB enum) to match
how the project already stores job / category / event_type / current_activity.

Sizes are in world units, on the Three.js XZ ground plane:
  width  -> X extent
  depth  -> Z extent
  height -> Y extent (Y is Three.js's UP axis)

`footprint` is the grid cell a building of this type needs when it is laid out
inside a district — always bigger than width/depth so buildings don't touch.
"""

# ---- type constants ----

BUILDING_PRESIDENTIAL_PALACE = "presidential_palace"
BUILDING_PARLIAMENT = "parliament"
BUILDING_GOVERNMENT_OFFICE = "government_office"
BUILDING_OFFICE = "office"
BUILDING_HOUSE = "house"
BUILDING_SHOP = "shop"
BUILDING_FACTORY = "factory"
BUILDING_MONUMENT = "monument"
BUILDING_PARK_FEATURE = "park_feature"

# Defined now, NOT generated yet — §21 "future-ready". The renderer already
# knows how to draw them, so adding them later is purely a generator change.
BUILDING_SCHOOL = "school"
BUILDING_HOSPITAL = "hospital"

BUILDING_TYPES = [
    BUILDING_PRESIDENTIAL_PALACE,
    BUILDING_PARLIAMENT,
    BUILDING_GOVERNMENT_OFFICE,
    BUILDING_OFFICE,
    BUILDING_HOUSE,
    BUILDING_SHOP,
    BUILDING_FACTORY,
    BUILDING_MONUMENT,
    BUILDING_PARK_FEATURE,
    BUILDING_SCHOOL,
    BUILDING_HOSPITAL,
]

# Types the renderer should draw with a unique hand-built mesh instead of a
# generic box. Everything else is a box (or an InstancedMesh, for houses).
LANDMARK_TYPES = {
    BUILDING_PRESIDENTIAL_PALACE,
    BUILDING_PARLIAMENT,
    BUILDING_MONUMENT,
}

# ---- render hints ----
#
# `color` is a hex string the frontend feeds straight into a THREE.Color.
# `icon` powers the map legend and the info panel heading.

BUILDING_TYPE_SPECS = {
    BUILDING_PRESIDENTIAL_PALACE: {
        "label": "Presidential Palace",
        "icon": "\U0001F451",          # crown
        "color": "#f0e6cf",
        "width": 46.0,
        "depth": 30.0,
        "height": 26.0,
        "footprint": 60.0,
        "is_landmark": True,
    },
    BUILDING_PARLIAMENT: {
        "label": "Parliament",
        "icon": "\U0001F3DB",          # classical building
        "color": "#e7ecf3",
        "width": 36.0,
        "depth": 24.0,
        "height": 20.0,
        "footprint": 48.0,
        "is_landmark": True,
    },
    BUILDING_GOVERNMENT_OFFICE: {
        "label": "Government Building",
        "icon": "\U0001F3E2",          # office building
        "color": "#c9d4e4",
        "width": 16.0,
        "depth": 14.0,
        "height": 14.0,
        "footprint": 24.0,
        "is_landmark": False,
    },
    BUILDING_OFFICE: {
        "label": "Office",
        "icon": "\U0001F3E2",
        "color": "#b8c6da",
        "width": 13.0,
        "depth": 12.0,
        "height": 17.0,
        "footprint": 20.0,
        "is_landmark": False,
    },
    BUILDING_HOUSE: {
        "label": "Citizen House",
        "icon": "\U0001F3E0",          # house
        "color": "#e8d4bd",
        "width": 7.0,
        "depth": 7.0,
        "height": 6.0,
        "footprint": 12.0,
        "is_landmark": False,
    },
    BUILDING_SHOP: {
        "label": "Shop",
        "icon": "\U0001F3EA",          # convenience store
        "color": "#f4cf8f",
        "width": 12.0,
        "depth": 10.0,
        "height": 9.0,
        "footprint": 18.0,
        "is_landmark": False,
    },
    BUILDING_FACTORY: {
        "label": "Factory",
        "icon": "\U0001F3ED",          # factory
        "color": "#a9b2bd",
        "width": 22.0,
        "depth": 18.0,
        "height": 12.0,
        "footprint": 30.0,
        "is_landmark": False,
    },
    BUILDING_MONUMENT: {
        "label": "Monument",
        "icon": "\U0001F5FF",          # moai
        "color": "#d8c9a8",
        "width": 8.0,
        "depth": 8.0,
        "height": 22.0,
        "footprint": 22.0,
        "is_landmark": True,
    },
    BUILDING_PARK_FEATURE: {
        "label": "Park",
        "icon": "\U0001F333",          # tree
        "color": "#7fbf7a",
        "width": 6.0,
        "depth": 6.0,
        "height": 8.0,
        "footprint": 16.0,
        "is_landmark": False,
    },
    BUILDING_SCHOOL: {
        "label": "School",
        "icon": "\U0001F3EB",          # school
        "color": "#cfe0c4",
        "width": 20.0,
        "depth": 16.0,
        "height": 11.0,
        "footprint": 28.0,
        "is_landmark": False,
    },
    BUILDING_HOSPITAL: {
        "label": "Hospital",
        "icon": "\U0001F3E5",          # hospital
        "color": "#e6d6d6",
        "width": 20.0,
        "depth": 16.0,
        "height": 15.0,
        "footprint": 28.0,
        "is_landmark": False,
    },
}


def spec_for(type_: str) -> dict:
    """Render hints for a type, falling back to the house spec so an unknown
    value stored by a future migration can never crash the map."""
    return BUILDING_TYPE_SPECS.get(type_, BUILDING_TYPE_SPECS[BUILDING_HOUSE])


# ---- where a citizen stands, given what they're doing (§16) ----
#
# The simulation already writes `citizens.current_activity` every tick (see
# simulation/actions.py: sleeping / eating / working / socializing / posting,
# and decision_pipeline.py: idle). The map reads it to decide WHERE to draw the
# marker — which is the whole of "simulation integration" without inventing a
# movement system or any pathfinding.
#
# An activity that is NOT listed here means "stay at home", which is the right
# default for sleeping, eating, posting and idle.

VENUE_TYPES_BY_ACTIVITY = {
    "working": (
        BUILDING_SHOP,
        BUILDING_FACTORY,
        BUILDING_OFFICE,
        BUILDING_GOVERNMENT_OFFICE,
        BUILDING_PARLIAMENT,
        BUILDING_PRESIDENTIAL_PALACE,
    ),
    "socializing": (
        BUILDING_SHOP,
        BUILDING_PARK_FEATURE,
        BUILDING_MONUMENT,
    ),
}

# Activities that count as "at work" for the info panel's badge.
WORK_ACTIVITIES = ("working",)


# ---- road kinds ----
#
# Roads are stored in their own table because a highway spans two cities and
# therefore belongs to neither one exclusively (see models/road.py).

ROAD_HIGHWAY = "highway"        # city -> city
ROAD_MAIN = "main"              # city centre -> district
ROAD_GOVERNMENT = "government"  # the ceremonial road to the Presidential Palace
ROAD_DISTRICT = "district"      # the spine inside one district

ROAD_KINDS = [ROAD_HIGHWAY, ROAD_MAIN, ROAD_GOVERNMENT, ROAD_DISTRICT]

ROAD_KIND_SPECS = {
    ROAD_HIGHWAY: {"label": "Highway", "color": "#8d8f96", "width": 9.0},
    ROAD_MAIN: {"label": "Main Road", "color": "#9a9ca3", "width": 7.0},
    ROAD_GOVERNMENT: {"label": "Government Road", "color": "#b9a06a", "width": 12.0},
    ROAD_DISTRICT: {"label": "District Road", "color": "#a4a6ad", "width": 4.5},
}
