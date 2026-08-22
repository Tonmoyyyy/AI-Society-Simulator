"""
Tests for the Government / President / First Lady system.

Two things are being pinned down here:

  * the API contract of /api/v1/government — public read, admin writes, and the
    PATCH semantics where "omitted" and "null" mean DIFFERENT things
  * the integration point with the 3D map: `world_service.get_government_summary`
    must report real names, and a citizen RENAME must change the name on the map
    with no regeneration. That last test is the executable form of the original
    requirement ("renaming Tonmoy to Alex must update the 3D map without
    changing frontend code").

SEEDING: as in test_world.py, the database starts genuinely EMPTY under pytest —
the app's lifespan seeder goes through the real MySQL SessionLocal, which
conftest's override does not patch, and every startup step is try/except'd. So
these tests never rely on `ensure_government` having run; they either call it
directly with the test session or let PATCH create the row on demand.
"""

import pytest

from app.repositories import government_repo
from app.services import government_service, world_service


# --------------------------------------------------------------- helpers

def _admin_headers(client, db_session, email="govadmin@example.com"):
    """Sign up, then promote to admin directly in the DB — signup always creates
    role="spectator" and there is deliberately no self-service promotion route."""
    from app.models.user import User

    client.post("/api/v1/auth/signup", json={"email": email, "password": "Pass1234"})
    user = db_session.query(User).filter(User.email == email).first()
    user.role = "admin"
    db_session.commit()

    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Pass1234"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _spectator_headers(client, email="govspectator@example.com"):
    client.post("/api/v1/auth/signup", json={"email": email, "password": "Pass1234"})
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Pass1234"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_citizens(client, headers, n):
    return [
        client.post("/api/v1/citizens", json={}, headers=headers).json()["id"]
        for _ in range(n)
    ]


# ============================================================ seeding

def test_ensure_government_creates_one_row(db_session):
    result = government_service.ensure_government(db_session)
    assert result["created"] is True

    gov = government_repo.get_government(db_session)
    assert gov is not None
    assert gov.tax_rate == pytest.approx(0.10)
    assert gov.curfew_enabled is False


def test_ensure_government_is_idempotent(db_session):
    """The property that makes an admin's changes survive a restart."""
    first = government_service.ensure_government(db_session)
    second = government_service.ensure_government(db_session)

    assert first["created"] is True
    assert second["created"] is False
    assert second["government_id"] == first["government_id"]


def test_ensure_government_appoints_the_two_lowest_id_citizens(client, db_session):
    """First boot should leave the palace labelled, not empty."""
    headers = _admin_headers(client, db_session)
    ids = _make_citizens(client, headers, 3)

    government_service.ensure_government(db_session)
    gov = government_repo.get_government(db_session)

    assert gov.president_citizen_id == min(ids)
    assert gov.first_lady_citizen_id == sorted(ids)[1]


def test_ensure_government_tolerates_an_empty_society(db_session):
    """Booting before any citizen exists must still create the row, with both
    offices vacant — not crash and not skip the row."""
    government_service.ensure_government(db_session)
    gov = government_repo.get_government(db_session)

    assert gov is not None
    assert gov.president_citizen_id is None
    assert gov.first_lady_citizen_id is None


def test_ensure_government_never_refills_a_deliberate_vacancy(client, db_session):
    """The reason ensure_government checks for the ROW, not for a President.

    An admin who dissolves the government must not find it restored on the next
    restart.
    """
    headers = _admin_headers(client, db_session)
    _make_citizens(client, headers, 2)
    government_service.ensure_government(db_session)

    resp = client.patch(
        "/api/v1/government",
        json={"president_citizen_id": None, "first_lady_citizen_id": None},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["president"] is None

    # Simulates the next app boot.
    government_service.ensure_government(db_session)

    assert client.get("/api/v1/government").json()["president"] is None


# ============================================================ reads

def test_get_government_404s_when_none_exists(client):
    resp = client.get("/api/v1/government")
    assert resp.status_code == 404


def test_get_government_is_public(client, db_session):
    """Read-is-public, matching citizens / posts / shops / dashboard / world."""
    government_service.ensure_government(db_session)

    resp = client.get("/api/v1/government")  # no Authorization header
    assert resp.status_code == 200, resp.text
    assert set(resp.json()) == {
        "id",
        "president",
        "first_lady",
        "tax_rate",
        "curfew_enabled",
        "term_started_tick",
        "capital_city_id",
        "capital_city_name",
        "created_at",
        "updated_at",
    }


def test_office_holder_carries_only_id_and_name(client, db_session):
    """§14 — a government response must not leak personality JSON or energy."""
    headers = _admin_headers(client, db_session)
    _make_citizens(client, headers, 1)
    government_service.ensure_government(db_session)

    president = client.get("/api/v1/government").json()["president"]
    assert set(president) == {"citizen_id", "name"}


def test_capital_comes_from_the_world_not_the_government_row(client, db_session):
    """`governments` has no capital_city_id column on purpose; the capital is
    read from cities.is_capital so the two can never disagree."""
    headers = _admin_headers(client, db_session)
    client.post("/api/v1/world/seed", headers=headers)
    government_service.ensure_government(db_session)

    body = client.get("/api/v1/government").json()
    assert body["capital_city_id"] is not None

    capital = next(
        c for c in client.get("/api/v1/world/cities").json() if c["is_capital"]
    )
    assert body["capital_city_id"] == capital["id"]
    assert body["capital_city_name"] == capital["name"]


# ============================================================ writes

def test_patch_requires_admin(client):
    resp = client.patch("/api/v1/government", json={"tax_rate": 0.2})
    assert resp.status_code in (401, 403)


def test_patch_rejects_a_spectator(client):
    headers = _spectator_headers(client)
    resp = client.patch("/api/v1/government", json={"tax_rate": 0.2}, headers=headers)
    assert resp.status_code == 403


def test_patch_creates_the_government_when_missing(client, db_session):
    """So an admin can establish a government on a database where startup
    seeding never ran."""
    headers = _admin_headers(client, db_session)
    assert government_repo.get_government(db_session) is None

    resp = client.patch("/api/v1/government", json={"tax_rate": 0.25}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["tax_rate"] == pytest.approx(0.25)


def test_patch_appoints_a_president(client, db_session):
    headers = _admin_headers(client, db_session)
    ids = _make_citizens(client, headers, 3)
    government_service.ensure_government(db_session)

    resp = client.patch(
        "/api/v1/government", json={"president_citizen_id": ids[2]}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["president"]["citizen_id"] == ids[2]


def test_omitted_field_is_left_alone(client, db_session):
    """The `exclude_unset` contract, half one: a PATCH that only sets the tax
    rate must NOT vacate the presidency."""
    headers = _admin_headers(client, db_session)
    _make_citizens(client, headers, 2)
    government_service.ensure_government(db_session)
    before = client.get("/api/v1/government").json()["president"]
    assert before is not None

    resp = client.patch("/api/v1/government", json={"tax_rate": 0.3}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["president"] == before


def test_explicit_null_vacates_the_office(client, db_session):
    """The `exclude_unset` contract, half two: sending null IS an instruction.

    If update_government ever switches to a plain model_dump, or the repo starts
    skipping None like citizen_repo.update does, this test fails.
    """
    headers = _admin_headers(client, db_session)
    _make_citizens(client, headers, 2)
    government_service.ensure_government(db_session)

    resp = client.patch(
        "/api/v1/government", json={"president_citizen_id": None}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["president"] is None
    # The other office is untouched.
    assert body["first_lady"] is not None


def test_patch_404s_on_an_unknown_citizen(client, db_session):
    headers = _admin_headers(client, db_session)
    government_service.ensure_government(db_session)

    resp = client.patch(
        "/api/v1/government", json={"president_citizen_id": 99999}, headers=headers
    )
    assert resp.status_code == 404


def test_patch_validates_before_writing_anything(client, db_session):
    """One good id and one bogus id must change NOTHING — not even the good one."""
    headers = _admin_headers(client, db_session)
    ids = _make_citizens(client, headers, 2)
    government_service.ensure_government(db_session)
    before = client.get("/api/v1/government").json()

    resp = client.patch(
        "/api/v1/government",
        json={"president_citizen_id": ids[1], "first_lady_citizen_id": 99999},
        headers=headers,
    )
    assert resp.status_code == 404
    assert client.get("/api/v1/government").json() == before


def test_one_citizen_cannot_hold_both_offices(client, db_session):
    headers = _admin_headers(client, db_session)
    ids = _make_citizens(client, headers, 2)
    government_service.ensure_government(db_session)

    resp = client.patch(
        "/api/v1/government",
        json={"president_citizen_id": ids[0], "first_lady_citizen_id": ids[0]},
        headers=headers,
    )
    assert resp.status_code == 422


def test_promoting_the_first_lady_without_vacating_is_rejected(client, db_session):
    """The conflict check compares POST-patch state, not just the sent fields."""
    headers = _admin_headers(client, db_session)
    _make_citizens(client, headers, 2)
    government_service.ensure_government(db_session)
    first_lady_id = client.get("/api/v1/government").json()["first_lady"]["citizen_id"]

    resp = client.patch(
        "/api/v1/government",
        json={"president_citizen_id": first_lady_id},
        headers=headers,
    )
    assert resp.status_code == 422

    # ...and it succeeds when the old office is vacated in the same request.
    resp = client.patch(
        "/api/v1/government",
        json={"president_citizen_id": first_lady_id, "first_lady_citizen_id": None},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["president"]["citizen_id"] == first_lady_id


@pytest.mark.parametrize("bad_rate", [1.5, 15, -0.1])
def test_tax_rate_must_be_a_fraction(client, db_session, bad_rate):
    """Catches the likeliest client mistake: 15 meaning 15% instead of 0.15."""
    headers = _admin_headers(client, db_session)
    resp = client.patch(
        "/api/v1/government", json={"tax_rate": bad_rate}, headers=headers
    )
    assert resp.status_code == 422


def test_tax_rate_boundaries_are_accepted(client, db_session):
    headers = _admin_headers(client, db_session)
    for rate in (0.0, 1.0):
        resp = client.patch(
            "/api/v1/government", json={"tax_rate": rate}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["tax_rate"] == pytest.approx(rate)


def test_curfew_toggles(client, db_session):
    headers = _admin_headers(client, db_session)
    resp = client.patch(
        "/api/v1/government", json={"curfew_enabled": True}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["curfew_enabled"] is True


# ============================================================ auto-appoint

def test_auto_appoint_requires_admin(client):
    resp = client.post("/api/v1/government/auto-appoint")
    assert resp.status_code in (401, 403)


def test_auto_appoint_fills_vacant_offices(client, db_session):
    """The path for a database whose citizens arrived after the government row."""
    headers = _admin_headers(client, db_session)
    government_service.ensure_government(db_session)  # no citizens yet -> vacant
    _make_citizens(client, headers, 2)

    resp = client.post("/api/v1/government/auto-appoint", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["president"] is not None
    assert body["first_lady"] is not None
    assert body["president"]["citizen_id"] != body["first_lady"]["citizen_id"]


def test_auto_appoint_leaves_a_filled_office_alone(client, db_session):
    headers = _admin_headers(client, db_session)
    ids = _make_citizens(client, headers, 3)
    government_service.ensure_government(db_session)
    client.patch(
        "/api/v1/government",
        json={"president_citizen_id": ids[2], "first_lady_citizen_id": None},
        headers=headers,
    )

    body = client.post("/api/v1/government/auto-appoint", headers=headers).json()
    assert body["president"]["citizen_id"] == ids[2]
    assert body["first_lady"] is not None
    assert body["first_lady"]["citizen_id"] != ids[2]


def test_auto_appoint_is_idempotent(client, db_session):
    headers = _admin_headers(client, db_session)
    _make_citizens(client, headers, 4)
    government_service.ensure_government(db_session)

    first = client.post("/api/v1/government/auto-appoint", headers=headers).json()
    second = client.post("/api/v1/government/auto-appoint", headers=headers).json()
    assert first["president"] == second["president"]
    assert first["first_lady"] == second["first_lady"]


def test_auto_appoint_with_no_citizens_is_not_an_error(client, db_session):
    headers = _admin_headers(client, db_session)
    resp = client.post("/api/v1/government/auto-appoint", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["president"] is None


# ============================================================ map integration

def test_world_summary_reports_system_unavailable_without_a_government(client, db_session):
    """A never-seeded database must still render the map, with the government UI
    hidden — not 500."""
    headers = _admin_headers(client, db_session)
    client.post("/api/v1/world/seed", headers=headers)

    gov = client.get("/api/v1/world").json()["government"]
    assert gov["system_available"] is False
    assert gov["president_name"] is None
    # The LOCATION facts still come through, because they're world data.
    assert gov["capital_city_id"] is not None


def test_world_summary_reports_real_names(client, db_session):
    headers = _admin_headers(client, db_session)
    client.post("/api/v1/world/seed", headers=headers)
    _make_citizens(client, headers, 2)
    government_service.ensure_government(db_session)

    gov = client.get("/api/v1/world").json()["government"]
    assert gov["system_available"] is True
    assert isinstance(gov["president_name"], str) and gov["president_name"]
    assert isinstance(gov["first_lady_name"], str) and gov["first_lady_name"]
    assert gov["tax_rate"] == pytest.approx(0.10)
    assert gov["curfew_enabled"] is False


def test_world_summary_keeps_the_presidential_district(client, db_session):
    """The government wiring must not have displaced the location fields the
    map already relied on."""
    headers = _admin_headers(client, db_session)
    client.post("/api/v1/world/seed", headers=headers)
    government_service.ensure_government(db_session)

    gov = client.get("/api/v1/world").json()["government"]
    assert gov["presidential_neighborhood_id"] is not None
    assert gov["presidential_neighborhood_name"]


def test_renaming_the_president_renames_them_on_the_map(client, db_session):
    """THE requirement, executable.

    Renaming citizen "Tonmoy" to "Alex" must change the 3D map's palace label
    with no regeneration and no frontend change. It works because
    `governments` stores a citizen id and the name is resolved by join on every
    request — if anyone ever adds a cached `president_name` column, this fails.
    """
    headers = _admin_headers(client, db_session)
    client.post("/api/v1/world/seed", headers=headers)
    citizen_id = client.post(
        "/api/v1/citizens", json={"name": "Tonmoy"}, headers=headers
    ).json()["id"]
    government_service.ensure_government(db_session)

    assert client.get("/api/v1/world").json()["government"]["president_name"] == "Tonmoy"

    resp = client.patch(
        f"/api/v1/citizens/{citizen_id}", json={"name": "Alex"}, headers=headers
    )
    assert resp.status_code == 200, resp.text

    assert client.get("/api/v1/world").json()["government"]["president_name"] == "Alex"


def test_president_marker_is_flagged(client, db_session):
    """Powers the crown badge on the citizen panel. Matched by id, never by
    name, so a rename cannot break it."""
    headers = _admin_headers(client, db_session)
    client.post("/api/v1/world/seed", headers=headers)
    ids = _make_citizens(client, headers, 3)
    government_service.ensure_government(db_session)

    citizens = client.get("/api/v1/world").json()["citizens"]
    flagged = [c for c in citizens if c["is_president"]]
    assert len(flagged) == 1
    assert flagged[0]["id"] == min(ids)

    first_ladies = [c for c in citizens if c["is_first_lady"]]
    assert len(first_ladies) == 1
    assert first_ladies[0]["id"] == sorted(ids)[1]


def test_no_marker_is_flagged_without_a_government(client, db_session):
    headers = _admin_headers(client, db_session)
    client.post("/api/v1/world/seed", headers=headers)
    _make_citizens(client, headers, 2)

    citizens = client.get("/api/v1/world").json()["citizens"]
    assert citizens
    assert not any(c["is_president"] or c["is_first_lady"] for c in citizens)


def test_vacating_the_presidency_clears_the_map_label(client, db_session):
    headers = _admin_headers(client, db_session)
    client.post("/api/v1/world/seed", headers=headers)
    _make_citizens(client, headers, 2)
    government_service.ensure_government(db_session)
    client.patch(
        "/api/v1/government", json={"president_citizen_id": None}, headers=headers
    )

    gov = client.get("/api/v1/world").json()["government"]
    # Still "available" — a government exists, the office is simply empty.
    assert gov["system_available"] is True
    assert gov["president_name"] is None


def test_get_summary_has_no_location_keys(db_session):
    """Guards the module split: government_service owns the government's own
    facts, world_service owns the location facts. If these keys reappear here,
    the two modules have two sources of truth for the capital again."""
    government_service.ensure_government(db_session)
    summary = government_service.get_summary(db_session)

    assert set(summary) == {
        "president_name",
        "first_lady_name",
        "tax_rate",
        "curfew_enabled",
        "system_available",
    }


# ============================================================ tick/day maths

@pytest.mark.parametrize(
    "tick, expected_day",
    [
        (0, 1),   # nothing has run yet — still day 1, not day 0
        (1, 1),   # ticks are 1-BASED (simulation_tick_repo.next_tick_number)
        (24, 1),  # last hour of day 1
        (25, 2),  # first hour of day 2
        (48, 2),
        (49, 3),
    ],
)
def test_day_for_tick(tick, expected_day):
    """Regression guard for an off-by-one: the old formula was
    `(tick // 24) + 1`, which assumed 0-based ticks and made day 1 23 hours
    long."""
    assert world_service._day_for_tick(tick) == expected_day
