from app.models.citizen import Citizen
from app.models.wallet import Wallet
from app.simulation import milestones


def _get_token(client, email="dashboardtest@example.com", password="Pass1234"):
    client.post("/api/v1/auth/signup", json={"email": email, "password": password})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


def _make_citizen(client, headers, name=None, job=None):
    payload = {"name": name} if name else {}
    citizen_id = client.post("/api/v1/citizens", json=payload, headers=headers).json()["id"]
    if job:
        client.patch(f"/api/v1/citizens/{citizen_id}", json={"job": job}, headers=headers)
    return citizen_id


# ---- dashboard stats ----

def test_dashboard_stats_empty_state(client):
    resp = client.get("/api/v1/dashboard/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["population"] == 0
    assert body["richest_citizen"] is None


def test_dashboard_stats_reflects_citizens(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    _make_citizen(client, headers, job="engineer")
    _make_citizen(client, headers)  # unemployed

    resp = client.get("/api/v1/dashboard/stats")
    body = resp.json()
    assert body["population"] == 2
    assert body["employed_count"] == 1
    assert body["unemployed_count"] == 1
    assert 0 <= body["average_happiness"] <= 100


def test_dashboard_stats_is_public(client):
    # no auth header at all — should still work
    resp = client.get("/api/v1/dashboard/stats")
    assert resp.status_code == 200


# ---- trending posts ----

def test_trending_posts_ranked_by_engagement(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    author = _make_citizen(client, headers)
    engager = _make_citizen(client, headers)

    quiet_post = client.post(
        f"/api/v1/citizens/{author}/posts", json={"content": "quiet post"}, headers=headers
    ).json()["id"]
    popular_post = client.post(
        f"/api/v1/citizens/{author}/posts", json={"content": "popular post"}, headers=headers
    ).json()["id"]
    client.post(
        f"/api/v1/posts/{popular_post}/comments",
        json={"citizen_id": engager, "content": "nice!"},
        headers=headers,
    )
    client.post(
        f"/api/v1/posts/{popular_post}/reactions", json={"citizen_id": engager}, headers=headers
    )

    resp = client.get("/api/v1/dashboard/trending?limit=5")
    assert resp.status_code == 200
    items = resp.json()
    ids = [i["id"] for i in items]
    assert popular_post in ids
    popular_item = next(i for i in items if i["id"] == popular_post)
    assert popular_item["score"] == 2
    # popular post should rank above the quiet one if both appear
    if quiet_post in ids:
        assert ids.index(popular_post) < ids.index(quiet_post)


# ---- timeline / milestone detectors (unit-level, no tick needed) ----

def test_population_milestone_fires_once(db_session):
    for i in range(10):
        c = Citizen(
            name=f"C{i}", age=30,
            personality_json={"kindness": 50, "intelligence": 50, "ambition": 50, "social": 50, "honesty": 50},
            mood=0.0, happiness=50.0, energy=100.0, health=100.0,
            job="unemployed", current_activity="idle",
        )
        db_session.add(c)
    db_session.commit()

    created_first = milestones.run_all_detectors(db_session, tick_number=1)
    db_session.commit()
    titles_first = [e.title for e in created_first]
    assert "Population reached 10" in titles_first

    # running again with the same population must NOT re-fire it
    created_second = milestones.run_all_detectors(db_session, tick_number=2)
    titles_second = [e.title for e in created_second]
    assert "Population reached 10" not in titles_second


def test_richest_citizen_milestone_fires_on_change(db_session):
    c1 = Citizen(
        name="Rich1", age=30,
        personality_json={"kindness": 50, "intelligence": 50, "ambition": 50, "social": 50, "honesty": 50},
        mood=0.0, happiness=50.0, energy=100.0, health=100.0, job="unemployed", current_activity="idle",
    )
    c2 = Citizen(
        name="Rich2", age=30,
        personality_json={"kindness": 50, "intelligence": 50, "ambition": 50, "social": 50, "honesty": 50},
        mood=0.0, happiness=50.0, energy=100.0, health=100.0, job="unemployed", current_activity="idle",
    )
    db_session.add_all([c1, c2])
    db_session.commit()
    db_session.add(Wallet(citizen_id=c1.id, balance=100))
    db_session.add(Wallet(citizen_id=c2.id, balance=50))
    db_session.commit()

    created = milestones.run_all_detectors(db_session, tick_number=1)
    db_session.commit()
    assert any("Rich1 became the richest citizen" in e.title for e in created)

    # no change in leader -> no new event
    created_again = milestones.run_all_detectors(db_session, tick_number=2)
    assert not any(e.category == "richest_citizen" for e in created_again)

    # c2 overtakes -> new event
    wallet2 = db_session.query(Wallet).filter(Wallet.citizen_id == c2.id).first()
    wallet2.balance = 200
    db_session.commit()
    created_change = milestones.run_all_detectors(db_session, tick_number=3)
    assert any("Rich2 became the richest citizen" in e.title for e in created_change)


# ---- timeline API ----

def test_timeline_endpoint_public_and_paginated(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(12):
        _make_citizen(client, headers)
    client.post("/api/v1/simulation/tick", headers=headers)

    resp = client.get("/api/v1/timeline")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert any(item["category"] == "population" for item in body["items"])


def test_timeline_category_filter(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(12):
        _make_citizen(client, headers)
    client.post("/api/v1/simulation/tick", headers=headers)

    resp = client.get("/api/v1/timeline?category=population")
    assert resp.status_code == 200
    body = resp.json()
    assert all(item["category"] == "population" for item in body["items"])


def test_timeline_unknown_category_returns_empty(client):
    resp = client.get("/api/v1/timeline?category=nonexistent_category")
    assert resp.status_code == 200
    assert resp.json()["items"] == []
