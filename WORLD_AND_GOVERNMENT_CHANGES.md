# 3D World Map + Government system — what changed and how to start it

This file is the handoff note for the two features added on top of the existing
simulator: the **3D Society Map** (`frontend/pages/world.html`) and the
**Government / President / First Lady system** (`/api/v1/government`). Nothing
that already worked was rewritten or removed — every table, route, service and
page that existed before is untouched, and both features were added through the
project's existing API → Service → Repository → Model layering with Alembic
migrations for the schema.

## Read this before you run anything

**None of this code has been executed.** The Linux sandbox I work in refused to
start in every session (`VM_DISK_SPACE_INSUFFICIENT`), so `alembic`, `pytest` and
`uvicorn` were never run against it. Everything was written and then cross-checked
by reading — including two full audits of the finished code — but reading is not
running. Expect to hit at least a small runtime issue on the first attempt, and
run the migration and the test suite before you look at the browser.

## First run, in this order

The migration must go first, because a schema fix is part of this change set. On
a fresh database `alembic upgrade head` previously died partway through with
MySQL error 1060 (`Duplicate column name 'neighborhood'`), which meant Alembic
never created any of the world tables at all. Two migrations
(`2cdfcfa31200` and `bd5026cd32f7`) had byte-identical bodies. The second one is
now a documented no-op — deliberately neutralised rather than deleted, because
deleting a revision file breaks any database already stamped with it.

```bash
cd backend
alembic upgrade head        # chain is now linear, single head: f18a3c6d40b2
python -m pytest tests/ -v  # includes tests/test_world.py and tests/test_government.py
uvicorn app.main:app --reload
```

Then serve the frontend as usual (`cd frontend && python -m http.server 5500`)
and open `http://127.0.0.1:5500/pages/world.html`.

On first boot the app seeds the cities and districts, lays out the buildings,
roads and citizen homes, and establishes the government row — all three steps are
idempotent, so restarting never re-rolls the world and never overwrites a rename.

## If the map has no President on it

That is expected on a brand-new database and the map will tell you so. Nothing in
this project creates citizens automatically, so a fresh install boots with zero
citizens and there is nobody to appoint. The government row is still created, with
both offices vacant, and the startup seeder deliberately does **not** come back
later and fill them — it cannot tell "never appointed" apart from "the admin
vacated this on purpose", and silently restoring a dissolved government would be
worse. Once you have citizens, one admin call fixes it:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/government/auto-appoint \
  -H "Authorization: Bearer $TOKEN"
```

Or choose the office holders yourself with `PATCH /api/v1/government`. Note that
`tax_rate` is a fraction between 0.0 and 1.0, not a percentage — `0.15` means 15%,
and anything above 1.0 is rejected.

## The design decision that matters most

There is no `president_name` column anywhere. The `governments` table stores
`president_citizen_id` and `first_lady_citizen_id` as foreign keys into `citizens`,
and the name is resolved by a join on every request. That is what makes your
requirement work: rename citizen "Tonmoy" to "Alex" through the ordinary
`PATCH /api/v1/citizens/{id}` endpoint and the Presidential Palace on the 3D map
relabels itself, with no world regeneration, no cache to invalidate and no
frontend change. There is a test pinning exactly that
(`test_renaming_the_president_renames_them_on_the_map`).

The same rule is applied throughout. City and district names come from the
database and are admin-editable, populations are counted at request time rather
than stored in a column that could drift, and every label, icon and colour the
renderer uses comes from `GET /api/v1/world/legend` — so adding a building type is
a change in one backend file, not in the JavaScript.

## Bugs found and fixed while finishing this

A real off-by-one in the day counter. `get_simulation_summary` computed the day as
`(tick // 24) + 1`, which assumes ticks start at zero, but
`simulation_tick_repo.next_tick_number` returns `(max or 0) + 1` — ticks are
1-based. Day 1 was therefore 23 hours long and every later day boundary was
shifted by one tick. It is now `((max(tick, 1) - 1) // 24) + 1`, with the clamp
guarding tick 0 against Python's `-1 // 24 == -1`.

A stored cross-site-scripting hole on the world page. `main.js` interpolated the
President's name and city names straight into `innerHTML`. Citizen names are
user-supplied with no character filtering, so a citizen created with markup in
their name and then appointed President would have executed that markup for every
visitor to a page that is public and unauthenticated. The `esc()` helper is now
exported from `panels.js` and used at both sites. If you add anything to this page
later, route database strings through `esc()` or build the node with `textContent`.

The government block was never re-read after the initial page load, so appointing
a President or changing the tax rate stayed invisible until someone reloaded —
while the palace panel claimed it would update on its own. The 6-second poll now
also reads `/api/v1/world/government` and, only when something actually changed,
relabels the palace in place. That is a `textContent` rewrite of one string, not a
world rebuild, so it does not re-upload any geometry to the GPU.

Also fixed: `get_world_overview` was querying the buildings table twice per map
load, and the building-type validator was rebuilding its lookup set once per query
parameter value.

## Where the code lives

The government is `models/government.py`, migration `f18a3c6d40b2`,
`repositories/government_repo.py`, `schemas/government.py`,
`services/government_service.py` and `api/v1/government.py`, with
`tests/test_government.py` covering it. The map's backend is `models/city.py`,
`models/neighborhood.py`, `models/building.py`, `models/road.py`,
`simulation/world_layout.py`, `simulation/world_generator.py`,
`services/world_service.py`, `services/world_generation_service.py` and
`api/v1/world.py`, with `tests/test_world.py`.

The frontend is `pages/world.html` plus `static/js/world/` — `scene.js` (camera,
lights, renderer, and the only file that imports Three.js directly),
`builders.js` (geometry), `picking.js` (raycasting), `panels.js` (the info cards
and legend) and `main.js` (loading, polling, performance guards). Three.js 0.160.1
comes from a CDN through an import map, so there is still no build step anywhere
in this project.

Endpoint tables for both features are in `backend/README.md`, sections 12b and 12c.

## Two things worth knowing about the seams

`world_service.get_government_summary()` is the single point where the map and the
government meet. Government facts come from `government_service`, location facts
(which city is the capital, which district is presidential) come from the world,
and that function is the only place they are merged. The import direction is
strictly one-way — `world_service` imports `government_service`, never the reverse
— which is what keeps them from becoming circular.

The test suite runs against in-memory SQLite with no MySQL required, but the
startup seeder talks to the real MySQL session, which the test override does not
patch. So under pytest the database starts genuinely empty and each test seeds what
it needs. That is why `test_world.py` still asserts the map degrades gracefully
with no government at all: that is the state pytest runs in, and the map has to
handle it rather than inventing a name.
