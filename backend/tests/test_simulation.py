from app.models.citizen import Citizen
from app.simulation.actions import ACTIONS
from app.simulation.decision_pipeline import decide_and_act


def _get_token(client, email="simtest@example.com", password="Pass1234"):
    client.post("/api/v1/auth/signup", json={"email": email, "password": password})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


def _make_citizen(**overrides) -> Citizen:
    defaults = dict(
        name="Test Citizen",
        age=30,
        personality_json={"kindness": 50, "intelligence": 50, "ambition": 50, "social": 50, "honesty": 50},
        mood=0.0,
        happiness=50.0,
        energy=100.0,
        health=100.0,
        job="unemployed",
        current_activity="idle",
    )
    defaults.update(overrides)
    return Citizen(**defaults)


# ---- decision_pipeline / actions unit tests (no DB needed) ----

def test_low_energy_citizen_chooses_sleep():
    citizen = _make_citizen(energy=5.0, health=100.0)
    result = decide_and_act(citizen)
    assert citizen.current_activity == "sleeping"
    assert citizen.energy > 5.0  # sleep restored energy
    assert result is None or result.activity == "sleeping"


def test_low_health_citizen_chooses_eat_over_socializing():
    citizen = _make_citizen(energy=100.0, health=5.0, personality_json={
        "kindness": 50, "intelligence": 50, "ambition": 50, "social": 90, "honesty": 50
    })
    decide_and_act(citizen)
    assert citizen.current_activity == "eating"
    assert citizen.health > 5.0


def test_unemployed_citizen_never_works():
    citizen = _make_citizen(job="unemployed", energy=100.0, health=100.0)
    for _ in range(10):
        citizen.energy = 100.0
        citizen.health = 100.0
        decide_and_act(citizen)
        assert citizen.current_activity != "working"


def test_employed_high_ambition_citizen_can_work():
    citizen = _make_citizen(
        job="engineer",
        energy=100.0,
        health=100.0,
        personality_json={"kindness": 50, "intelligence": 50, "ambition": 95, "social": 5, "honesty": 50},
    )
    decide_and_act(citizen)
    # very ambitious + not sociable should favor work over socializing
    assert citizen.current_activity == "working"


def test_action_state_changes_stay_within_bounds():
    citizen = _make_citizen(energy=95.0, health=95.0, happiness=98.0, mood=0.95)
    for _ in range(20):
        decide_and_act(citizen)
        assert 0.0 <= citizen.energy <= 100.0
        assert 0.0 <= citizen.health <= 100.0
        assert 0.0 <= citizen.happiness <= 100.0
        assert -1.0 <= citizen.mood <= 1.0


def test_all_actions_registered():
    names = {a.name for a in ACTIONS}
    assert names == {"sleep", "eat", "work", "socialize", "create_post"}


# ---- API / engine integration tests (use the test DB via client fixture) ----

def test_trigger_tick_requires_auth(client):
    resp = client.post("/api/v1/simulation/tick")
    assert resp.status_code == 401


def test_trigger_tick_processes_all_citizens(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(3):
        client.post("/api/v1/citizens", json={}, headers=headers)

    resp = client.post("/api/v1/simulation/tick", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["citizens_processed"] == 3
    assert body["status"] == "completed"
    assert body["tick_number"] == 1


def test_tick_number_increments(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/v1/citizens", json={}, headers=headers)

    first = client.post("/api/v1/simulation/tick", headers=headers).json()
    second = client.post("/api/v1/simulation/tick", headers=headers).json()
    assert second["tick_number"] == first["tick_number"] + 1


def test_tick_changes_citizen_state(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    create_resp = client.post("/api/v1/citizens", json={}, headers=headers)
    citizen_id = create_resp.json()["id"]

    client.post("/api/v1/simulation/tick", headers=headers)

    after = client.get(f"/api/v1/citizens/{citizen_id}").json()
    assert after["current_activity"] != "idle"


def test_list_ticks_is_public(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/v1/citizens", json={}, headers=headers)
    client.post("/api/v1/simulation/tick", headers=headers)

    resp = client.get("/api/v1/simulation/ticks")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1
    assert body[0]["status"] == "completed"


def test_citizen_memories_endpoint(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    # give the citizen a job + high ambition so "work" is likely picked and logged
    create_resp = client.post(
        "/api/v1/citizens", json={"name": "Worker Bee"}, headers=headers
    )
    citizen_id = create_resp.json()["id"]
    client.patch(f"/api/v1/citizens/{citizen_id}", json={"job": "baker"}, headers=headers)

    # run several ticks to give some action a chance to log a memory
    for _ in range(5):
        client.post("/api/v1/simulation/tick", headers=headers)

    resp = client.get(f"/api/v1/citizens/{citizen_id}/memories")
    assert resp.status_code == 200
    # not asserting non-empty (sleep/eat ticks don't log memories by design),
    # just that the endpoint works and returns a list
    assert isinstance(resp.json(), list)


def test_memories_endpoint_404_for_missing_citizen(client):
    resp = client.get("/api/v1/citizens/999999/memories")
    assert resp.status_code == 404


def test_scheduler_status_defaults_to_not_running(client):
    resp = client.get("/api/v1/simulation/scheduler/status")
    assert resp.status_code == 200
    assert resp.json()["running"] is False


def test_scheduler_start_stop_requires_auth(client):
    assert client.post("/api/v1/simulation/scheduler/start").status_code == 401
    assert client.post("/api/v1/simulation/scheduler/stop").status_code == 401
