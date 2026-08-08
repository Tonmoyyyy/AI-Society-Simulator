from app.core.config import settings


def _get_token(client, email="citizentest@example.com", password="Pass1234"):
    client.post("/api/v1/auth/signup", json={"email": email, "password": password})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


def test_create_citizen_fully_random(client):
    token = _get_token(client)
    resp = client.post(
        "/api/v1/citizens", json={}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"]
    assert 0 <= body["age"] <= 120
    assert set(body["personality_json"].keys()) == {
        "kindness", "intelligence", "ambition", "social", "honesty"
    }
    for score in body["personality_json"].values():
        assert 0 <= score <= 100
    # default state
    assert body["happiness"] == 50.0
    assert body["energy"] == 100.0
    assert body["health"] == 100.0
    assert body["job"] == "unemployed"
    assert body["current_activity"] == "idle"
    assert "money" not in body  # money must never appear on citizens (wallet is the source of truth)


def test_create_citizen_with_name_and_age(client):
    token = _get_token(client)
    resp = client.post(
        "/api/v1/citizens",
        json={"name": "Test Citizen", "age": 30},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Test Citizen"
    assert body["age"] == 30


def test_create_citizen_requires_auth(client):
    resp = client.post("/api/v1/citizens", json={})
    assert resp.status_code == 401


def test_list_citizens_is_public(client):
    token = _get_token(client)
    client.post("/api/v1/citizens", json={}, headers={"Authorization": f"Bearer {token}"})

    resp = client.get("/api/v1/citizens")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert len(body["items"]) >= 1


def test_list_citizens_pagination(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(5):
        client.post("/api/v1/citizens", json={}, headers=headers)

    resp = client.get("/api/v1/citizens?page=1&page_size=2")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["total"] >= 5


def test_get_citizen_by_id(client):
    token = _get_token(client)
    create_resp = client.post(
        "/api/v1/citizens", json={"name": "Findable"}, headers={"Authorization": f"Bearer {token}"}
    )
    citizen_id = create_resp.json()["id"]

    resp = client.get(f"/api/v1/citizens/{citizen_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Findable"


def test_get_citizen_not_found(client):
    resp = client.get("/api/v1/citizens/999999")
    assert resp.status_code == 404


def test_update_citizen_job_and_activity(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    create_resp = client.post("/api/v1/citizens", json={}, headers=headers)
    citizen_id = create_resp.json()["id"]

    resp = client.patch(
        f"/api/v1/citizens/{citizen_id}",
        json={"job": "teacher", "current_activity": "working"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["job"] == "teacher"
    assert body["current_activity"] == "working"


def test_update_citizen_requires_auth(client):
    token = _get_token(client)
    create_resp = client.post(
        "/api/v1/citizens", json={}, headers={"Authorization": f"Bearer {token}"}
    )
    citizen_id = create_resp.json()["id"]

    resp = client.patch(f"/api/v1/citizens/{citizen_id}", json={"job": "hacker"})
    assert resp.status_code == 401


def test_update_nonexistent_citizen(client):
    token = _get_token(client)
    resp = client.patch(
        "/api/v1/citizens/999999",
        json={"job": "ghost"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_delete_citizen(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    create_resp = client.post("/api/v1/citizens", json={}, headers=headers)
    citizen_id = create_resp.json()["id"]

    del_resp = client.delete(f"/api/v1/citizens/{citizen_id}", headers=headers)
    assert del_resp.status_code == 204

    get_resp = client.get(f"/api/v1/citizens/{citizen_id}")
    assert get_resp.status_code == 404


def test_delete_citizen_requires_auth(client):
    token = _get_token(client)
    create_resp = client.post(
        "/api/v1/citizens", json={}, headers={"Authorization": f"Bearer {token}"}
    )
    citizen_id = create_resp.json()["id"]

    resp = client.delete(f"/api/v1/citizens/{citizen_id}")
    assert resp.status_code == 401


def test_citizen_limit_enforced(client, monkeypatch):
    # Lower the cap for a fast test instead of creating 100 real citizens
    monkeypatch.setattr(settings, "MAX_CITIZENS_V0", 3)
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    for _ in range(3):
        resp = client.post("/api/v1/citizens", json={}, headers=headers)
        assert resp.status_code == 201

    resp = client.post("/api/v1/citizens", json={}, headers=headers)
    assert resp.status_code == 409
    assert "limit reached" in resp.json()["error"]["message"].lower()
