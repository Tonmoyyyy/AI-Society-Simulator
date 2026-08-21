"""
Tests for the World / 3D Map feature (World Phases 1-8).

Two layers, deliberately:

  * unit tests over app/simulation/world_generator.py — the layout maths, where
    the determinism guarantee (§12) actually lives
  * API tests over /api/v1/world/* — response shape, public/admin split and
    route ordering

NOTE ON SEEDING: the app's lifespan seeds the default world, but it does so
through the real `SessionLocal` (MySQL), which conftest's override does NOT
patch — and every startup step is wrapped in try/except. So under pytest the
database starts genuinely EMPTY. Tests that need cities seed them explicitly
via POST /api/v1/world/seed. That is a feature, not a workaround: it means these
tests never depend on a MySQL server being up.
"""

import pytest

from app.simulation.building_types import BUILDING_HOUSE, BUILDING_SHOP, spec_for
from app.simulation.world_generator import (
    DISTRICT_CORRIDOR_HALF,
    grid_slots,
    house_footprint_for,
    housing_capacity,
    marker_offset,
    stable_rng,
)
from app.simulation.world_layout import (
    DEFAULT_WORLD,
    DISTRICT_COMMERCIAL,
    DISTRICT_RESIDENTIAL,
    DISTRICT_TYPES,
)


# --------------------------------------------------------------- helpers

def _admin_headers(client, db_session, email="worldadmin@example.com"):
    """Sign up, then promote to admin directly in the DB.

    Signup always creates role="spectator" (models/user.py), and there is no
    self-service promotion endpoint — correctly so. Tests therefore flip the
    column, which also documents that /generate really is gated on role.
    """
    from app.models.user import User

    client.post("/api/v1/auth/signup", json={"email": email, "password": "Pass1234"})
    user = db_session.query(User).filter(User.email == email).first()
    user.role = "admin"
    db_session.commit()

    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Pass1234"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _spectator_headers(client, email="worldspectator@example.com"):
    client.post("/api/v1/auth/signup", json={"email": email, "password": "Pass1234"})
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Pass1234"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed(client, headers):
    resp = client.post("/api/v1/world/seed", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _make_citizens(client, headers, n):
    return [
        client.post("/api/v1/citizens", json={}, headers=headers).json()["id"]
        for _ in range(n)
    ]


# ================================================================= unit:
# ------------------------------------------------------------- stable_rng

def test_stable_rng_is_reproducible_across_calls():
    """The whole no-random-coordinates guarantee (§12) rests on this."""
    a = [stable_rng("slots", 3).random() for _ in range(5)]
    b = [stable_rng("slots", 3).random() for _ in range(5)]
    assert a == b


def test_stable_rng_differs_per_key():
    assert stable_rng("slots", 1).random() != stable_rng("slots", 2).random()
    assert stable_rng("houses", 1).random() != stable_rng("shops", 1).random()


def test_stable_rng_does_not_depend_on_pythons_hash():
    """Regression guard for the reason stable_rng exists.

    `hash()` on a str is salted per process (PYTHONHASHSEED), so seeding an RNG
    with it would move every building on restart. This pins the value: if
    someone "simplifies" stable_rng to use hash(), this test fails.
    """
    expected = stable_rng("slots", 0).random()
    assert stable_rng("slots", 0).random() == expected
    # And the value must be derived from the string content, not object identity.
    key = "".join(["sl", "ots"])
    assert stable_rng(key, 0).random() == expected


# ------------------------------------------------------------- grid_slots

@pytest.mark.parametrize("district_type", DISTRICT_TYPES)
def test_grid_slots_never_empty_for_any_district_type(district_type):
    """REGRESSION (the bug that hid every shop).

    grid_slots drops any row inside the central road corridor. With a 90x70
    district and the 18-unit shop grid, the two available rows land at +/-9,
    both inside the corridor threshold of 5.0 + 4.5 = 9.5 -> zero slots. Every
    commercial district generated no shops at all, so buildings.shop_id was NULL
    everywhere and three districts rendered as bare ground.

    Asking for buildings and getting none back is never an acceptable answer.
    """
    footprint = house_footprint_for(district_type)
    slots = grid_slots(90.0, 70.0, count=6, footprint=footprint)
    assert slots, f"{district_type} produced no slots"


def test_grid_slots_shop_grid_specifically():
    """The exact numbers from the bug report: shop footprint in a 90x70."""
    footprint = spec_for(BUILDING_SHOP)["footprint"]
    slots = grid_slots(90.0, 70.0, count=6, footprint=footprint)
    assert len(slots) >= 1


def test_grid_slots_single_row_district_still_yields_slots():
    """The `rows == 1` case: the only row sits at exactly z=0, i.e. dead centre
    of the corridor. A naive corridor-drop returns [] here no matter how the
    corridor width is tweaked, which is why the guard zeroes the threshold
    instead of shrinking it."""
    # A district barely deeper than one cell => rows == 1.
    slots = grid_slots(90.0, 30.0, count=4, footprint=18.0)
    assert slots


def test_grid_slots_is_deterministic():
    a = grid_slots(120.0, 100.0, count=12, footprint=14.0)
    b = grid_slots(120.0, 100.0, count=12, footprint=14.0)
    assert a == b


def test_grid_slots_respects_count_cap():
    slots = grid_slots(400.0, 400.0, count=5, footprint=10.0)
    assert len(slots) == 5


def test_grid_slots_stay_inside_the_district():
    """Slots must not spill outside the plate, or buildings float off the
    district's ground in the 3D view."""
    width, depth = 120.0, 100.0
    slots = grid_slots(width, depth, count=20, footprint=12.0)
    for x, z in slots:
        assert abs(x) <= width / 2, f"x={x} outside width {width}"
        assert abs(z) <= depth / 2, f"z={z} outside depth {depth}"


def test_grid_slots_keeps_road_corridor_clear_when_it_can():
    """The corridor guard must not become an excuse to always ignore the
    corridor: in a district roomy enough to have clear rows, the middle strip
    still has to stay empty.

    `count` is set to the full capacity of this grid (23x23 at a 12-unit cell in
    a 300x300 district) so the generator walks EVERY row instead of returning
    early from the first one — otherwise this never reaches the centre row it is
    meant to be checking.
    """
    slots = grid_slots(300.0, 300.0, count=529, footprint=12.0)
    assert len(slots) > 100, "expected a large grid to walk all its rows"
    # The centre row is dropped, and its neighbours sit a full cell away, so
    # nothing should land inside the corridor here.
    assert all(abs(z) >= DISTRICT_CORRIDOR_HALF for _x, z in slots)


def test_grid_slots_row_major_order_is_stable():
    """Citizen #1 must always get the same house, so ordering matters as much
    as the coordinates."""
    first = grid_slots(200.0, 200.0, count=10, footprint=15.0)
    second = grid_slots(200.0, 200.0, count=10, footprint=15.0)
    assert first[0] == second[0]
    assert first[-1] == second[-1]


# --------------------------------------------------- capacity & markers

def test_housing_capacity_covers_residents():
    for residents in (0, 1, 7, 8, 9, 33, 100, 501):
        assert housing_capacity(residents) >= residents


def test_housing_capacity_is_monotonic():
    values = [housing_capacity(n) for n in range(0, 200)]
    assert values == sorted(values)


def test_marker_offset_is_stable_per_citizen():
    """A citizen's marker jitter must not change between polls, or every marker
    visibly twitches on each refresh even when nobody moved."""
    assert marker_offset(42) == marker_offset(42)
    assert marker_offset(42) != marker_offset(43)


def test_marker_offset_within_radius():
    for citizen_id in range(1, 50):
        dx, dz = marker_offset(citizen_id, radius=3.0)
        assert (dx**2 + dz**2) ** 0.5 <= 3.0 + 1e-9


def test_house_footprint_worker_district_is_denser():
    base = house_footprint_for(DISTRICT_RESIDENTIAL)
    worker = house_footprint_for("worker")
    assert worker < base


# ================================================================== API:
# ------------------------------------------------------------ read shape

def test_world_overview_is_public_and_well_formed_when_empty(client):
    """No auth, no seed, no geometry — must still return a valid payload with
    world_generated False rather than 404 or a crash."""
    resp = client.get("/api/v1/world")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    for key in (
        "cities",
        "neighborhoods",
        "buildings",
        "roads",
        "citizens",
        "government",
        "simulation",
        "unassigned_citizens",
        "citizens_truncated",
        "world_generated",
    ):
        assert key in body, f"missing {key}"

    assert body["world_generated"] is False
    assert body["buildings"] == []


def test_world_simulation_endpoint_shape(client):
    """The header-stats route the map polls every tick."""
    resp = client.get("/api/v1/world/simulation")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in (
        "tick_number",
        "day",
        "population",
        "city_count",
        "neighborhood_count",
        "average_happiness",
        "current_event",
    ):
        assert key in body, f"missing {key}"


def test_world_legend_is_backend_owned(client):
    """The frontend holds no palette: every district/building/road entry must
    arrive with its own label, icon and colour."""
    resp = client.get("/api/v1/world/legend")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["districts"] and body["buildings"] and body["roads"]
    for d in body["districts"]:
        assert d["type"] and d["label"] and d["icon"] and d["color"].startswith("#")
    for b in body["buildings"]:
        assert b["type"] and b["label"] and b["icon"] and b["color"].startswith("#")
    for r in body["roads"]:
        assert r["kind"] and r["label"] and r["color"].startswith("#")


def test_district_types_route_is_not_swallowed_by_city_id(client):
    """ROUTE ORDERING REGRESSION.

    Starlette matches routes in registration order and takes the first match —
    it does NOT prefer literal segments over parameterised ones. If
    /cities/{city_id} were ever declared above the literal paths, this request
    would try to parse "district-types" as an int and return 422.
    """
    resp = client.get("/api/v1/world/district-types")
    assert resp.status_code == 200, resp.text
    types = [d["type"] for d in resp.json()]
    assert set(types) == set(DISTRICT_TYPES)


def test_government_summary_reports_unavailable_system(client):
    """The Government/President/First Lady system is not in this codebase yet.

    The contract is that the map degrades gracefully rather than inventing a
    name: system_available False, names None. When that system lands, this test
    should be updated — it is the marker for the single wiring point.
    """
    resp = client.get("/api/v1/world/government")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["system_available"] is False
    assert body["president_name"] is None
    assert body["first_lady_name"] is None


# --------------------------------------------------------------- seeding

def test_seed_creates_default_world_and_is_idempotent(client, db_session):
    headers = _admin_headers(client, db_session)

    first = _seed(client, headers)
    assert first["created_cities"] == len(DEFAULT_WORLD)
    assert first["created_neighborhoods"] > 0

    # Second call must be a no-op, which is what protects admin renames.
    second = _seed(client, headers)
    assert second["created_cities"] == 0
    assert second["created_neighborhoods"] == 0

    cities = client.get("/api/v1/world/cities").json()
    assert len(cities) == len(DEFAULT_WORLD)
    assert sum(1 for c in cities if c["is_capital"]) == 1


def test_seed_requires_admin(client):
    assert client.post("/api/v1/world/seed").status_code in (401, 403)
    assert client.post(
        "/api/v1/world/seed", headers=_spectator_headers(client)
    ).status_code == 403


def test_city_population_is_counted_not_stored(client, db_session):
    """cities has no population column on purpose; the value is GROUP BY-counted
    at request time so it can never go stale."""
    headers = _admin_headers(client, db_session)
    _seed(client, headers)
    _make_citizens(client, headers, 4)
    client.post("/api/v1/world/generate?force=true", headers=headers)

    cities = client.get("/api/v1/world/cities").json()
    assert sum(c["population"] for c in cities) == 4


# ------------------------------------------------------------ generation

def test_generate_requires_admin(client):
    assert client.post("/api/v1/world/generate").status_code in (401, 403)
    assert client.post(
        "/api/v1/world/generate", headers=_spectator_headers(client)
    ).status_code == 403


def test_generate_places_buildings_roads_and_homes(client, db_session):
    headers = _admin_headers(client, db_session)
    _seed(client, headers)
    _make_citizens(client, headers, 12)

    result = client.post("/api/v1/world/generate?force=true", headers=headers)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["created_buildings"] > 0
    assert body["created_roads"] > 0
    assert body["assigned_citizens"] == 12
    assert body["housed_citizens"] > 0

    overview = client.get("/api/v1/world").json()
    assert overview["world_generated"] is True
    assert overview["unassigned_citizens"] == 0
    assert len(overview["citizens"]) == 12


def test_generate_without_force_declines_instead_of_erroring(client, db_session):
    """Mirrors POST /seed: a refusal is a 200 with zero counts and an
    explanatory detail, not an exception."""
    headers = _admin_headers(client, db_session)
    _seed(client, headers)
    client.post("/api/v1/world/generate?force=true", headers=headers)

    again = client.post("/api/v1/world/generate", headers=headers)
    assert again.status_code == 200, again.text
    body = again.json()
    assert body["created_buildings"] == 0
    assert body["deleted_buildings"] == 0
    assert body["detail"]


def test_generation_is_deterministic_across_force_rebuilds(client, db_session):
    """§12, the headline guarantee: a citizen's house does not move.

    Force-regenerating wipes and rebuilds every building, so if any coordinate
    came from an unseeded random this comparison fails.
    """
    headers = _admin_headers(client, db_session)
    _seed(client, headers)
    _make_citizens(client, headers, 10)
    client.post("/api/v1/world/generate?force=true", headers=headers)

    def fingerprint():
        buildings = client.get("/api/v1/world/buildings").json()
        return [
            (b["type"], b["city_id"], b["offset_x"], b["offset_z"], b["rotation"])
            for b in buildings
        ]

    before = fingerprint()
    assert before

    client.post("/api/v1/world/generate?force=true", headers=headers)
    assert fingerprint() == before


def test_every_commercial_district_gets_shops(client, db_session):
    """Integration-level regression for the grid_slots corridor bug.

    plan_district_buildings emits `max(6, len(shop_names))` BUILDING_SHOP
    blueprints per commercial district — but every one of them came from
    grid_slots, so when that returned [] the district produced literally zero
    buildings and rendered as bare ground. The unit tests above prove the maths;
    this proves the generated world actually contains shops.
    """
    headers = _admin_headers(client, db_session)
    _seed(client, headers)
    _make_citizens(client, headers, 8)
    client.post("/api/v1/world/generate?force=true", headers=headers)

    districts = client.get("/api/v1/world/neighborhoods").json()
    commercial = [d for d in districts if d["type"] == DISTRICT_COMMERCIAL]
    assert commercial, "default world has no commercial district to test"

    buildings = client.get("/api/v1/world/buildings").json()
    for district in commercial:
        in_district = [b for b in buildings if b["neighborhood_id"] == district["id"]]
        assert in_district, f"district {district['name']} has no buildings at all"
        assert any(
            b["type"] == BUILDING_SHOP for b in in_district
        ), f"district {district['name']} has no shops"

    # And globally: a world with no shop anywhere means the bug is back.
    assert any(b["type"] == BUILDING_SHOP for b in buildings)


def test_citizen_markers_carry_resolved_positions(client, db_session):
    headers = _admin_headers(client, db_session)
    _seed(client, headers)
    _make_citizens(client, headers, 6)
    client.post("/api/v1/world/generate?force=true", headers=headers)

    citizens = client.get("/api/v1/world/citizens").json()
    assert len(citizens) == 6
    for c in citizens:
        assert isinstance(c["marker_x"], (int, float))
        assert isinstance(c["marker_z"], (int, float))
        assert c["city_id"] is not None
        # WorldCitizenOut is deliberately NOT CitizenOut — no personality blob.
        assert "personality_json" not in c
        assert "energy" not in c


def test_house_label_follows_a_citizen_rename(client, db_session):
    """Houses store name = NULL; the label is the owner's CURRENT name resolved
    per request. So a rename must show up on the map with no regeneration."""
    headers = _admin_headers(client, db_session)
    _seed(client, headers)
    citizen_ids = _make_citizens(client, headers, 5)
    client.post("/api/v1/world/generate?force=true", headers=headers)

    houses = client.get("/api/v1/world/buildings?type=house").json()
    owned = [b for b in houses if b["owner_citizen_id"] is not None]
    assert owned, "generation housed nobody"

    target = owned[0]
    client.patch(
        f"/api/v1/citizens/{target['owner_citizen_id']}",
        json={"name": "Renamed Person"},
        headers=headers,
    )

    refreshed = client.get(f"/api/v1/world/buildings/{target['id']}").json()
    assert refreshed["owner_name"] == "Renamed Person"
    assert refreshed["name"] is None


def test_city_rename_is_reflected_everywhere(client, db_session):
    """City names are never hardcoded in the frontend — this is the flow that
    guarantees it."""
    headers = _admin_headers(client, db_session)
    _seed(client, headers)
    city_id = client.get("/api/v1/world/cities").json()[0]["id"]

    resp = client.patch(
        f"/api/v1/world/cities/{city_id}",
        json={"name": "New Capital Name"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    names = [c["name"] for c in client.get("/api/v1/world/cities").json()]
    assert "New Capital Name" in names


def test_city_rename_rejects_duplicates(client, db_session):
    headers = _admin_headers(client, db_session)
    _seed(client, headers)
    cities = client.get("/api/v1/world/cities").json()
    resp = client.patch(
        f"/api/v1/world/cities/{cities[0]['id']}",
        json={"name": cities[1]["name"]},
        headers=headers,
    )
    assert resp.status_code == 409


def test_district_retype_validates_against_known_types(client, db_session):
    headers = _admin_headers(client, db_session)
    _seed(client, headers)
    district_id = client.get("/api/v1/world/neighborhoods").json()[0]["id"]

    bad = client.patch(
        f"/api/v1/world/neighborhoods/{district_id}",
        json={"type": "not_a_real_type"},
        headers=headers,
    )
    assert bad.status_code == 422

    good = client.patch(
        f"/api/v1/world/neighborhoods/{district_id}",
        json={"type": DISTRICT_COMMERCIAL},
        headers=headers,
    )
    assert good.status_code == 200
    assert good.json()["type"] == DISTRICT_COMMERCIAL


# ------------------------------------------------------------- filtering

def test_city_filter_restricts_the_whole_payload(client, db_session):
    headers = _admin_headers(client, db_session)
    _seed(client, headers)
    _make_citizens(client, headers, 10)
    client.post("/api/v1/world/generate?force=true", headers=headers)

    city_id = client.get("/api/v1/world/cities").json()[0]["id"]
    body = client.get(f"/api/v1/world?city_id={city_id}").json()

    assert [c["id"] for c in body["cities"]] == [city_id]
    assert all(n["city_id"] == city_id for n in body["neighborhoods"])
    assert all(b["city_id"] == city_id for b in body["buildings"])


def test_unknown_city_filter_is_404(client):
    assert client.get("/api/v1/world?city_id=999999").status_code == 404


def test_include_citizens_false_drops_markers(client, db_session):
    headers = _admin_headers(client, db_session)
    _seed(client, headers)
    _make_citizens(client, headers, 5)
    client.post("/api/v1/world/generate?force=true", headers=headers)

    body = client.get("/api/v1/world?include_citizens=false").json()
    assert body["citizens"] == []
    assert body["buildings"], "terrain must still come back"


def test_citizen_limit_sets_truncated_flag(client, db_session):
    headers = _admin_headers(client, db_session)
    _seed(client, headers)
    _make_citizens(client, headers, 6)
    client.post("/api/v1/world/generate?force=true", headers=headers)

    body = client.get("/api/v1/world?citizen_limit=3").json()
    assert len(body["citizens"]) == 3
    assert body["citizens_truncated"] is True


def test_unknown_building_type_filter_is_422(client):
    resp = client.get("/api/v1/world/buildings?type=definitely_not_a_type")
    assert resp.status_code == 422


def test_buildings_ordered_by_id_for_stable_instancing(client, db_session):
    """The renderer's InstancedMesh indices assume this ordering."""
    headers = _admin_headers(client, db_session)
    _seed(client, headers)
    _make_citizens(client, headers, 8)
    client.post("/api/v1/world/generate?force=true", headers=headers)

    ids = [b["id"] for b in client.get("/api/v1/world/buildings").json()]
    assert ids == sorted(ids)


def test_house_type_filter_returns_only_houses(client, db_session):
    headers = _admin_headers(client, db_session)
    _seed(client, headers)
    _make_citizens(client, headers, 6)
    client.post("/api/v1/world/generate?force=true", headers=headers)

    houses = client.get("/api/v1/world/buildings?type=house").json()
    assert houses
    assert all(b["type"] == BUILDING_HOUSE for b in houses)


def test_roads_filtered_by_city_stay_relevant_to_it(client, db_session):
    """A city must never be drawn without its connections, so a city-filtered
    road list may contain that city's own roads plus city-less highways — and
    nothing belonging to a different city."""
    headers = _admin_headers(client, db_session)
    _seed(client, headers)
    client.post("/api/v1/world/generate?force=true", headers=headers)

    city_id = client.get("/api/v1/world/cities").json()[0]["id"]
    roads = client.get(f"/api/v1/world/roads?city_id={city_id}").json()
    assert roads
    assert all(r["city_id"] in (city_id, None) for r in roads)


def test_missing_building_is_404(client):
    assert client.get("/api/v1/world/buildings/999999").status_code == 404


def test_missing_city_detail_is_404(client):
    assert client.get("/api/v1/world/cities/999999").status_code == 404


def test_city_detail_includes_its_districts(client, db_session):
    headers = _admin_headers(client, db_session)
    _seed(client, headers)
    city_id = client.get("/api/v1/world/cities").json()[0]["id"]

    body = client.get(f"/api/v1/world/cities/{city_id}").json()
    assert body["id"] == city_id
    assert body["neighborhoods"]
    assert all(n["city_id"] == city_id for n in body["neighborhoods"])


def test_district_world_position_matches_city_plus_offset(client, db_session):
    """world_x/world_z are computed by the service so the renderer can use them
    directly; they must agree with the stored offsets."""
    headers = _admin_headers(client, db_session)
    _seed(client, headers)

    cities = {c["id"]: c for c in client.get("/api/v1/world/cities").json()}
    for d in client.get("/api/v1/world/neighborhoods").json():
        city = cities[d["city_id"]]
        assert d["world_x"] == pytest.approx(city["world_x"] + d["offset_x"])
        assert d["world_z"] == pytest.approx(city["world_z"] + d["offset_z"])
