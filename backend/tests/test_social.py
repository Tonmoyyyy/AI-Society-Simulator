import random

from app.models.citizen import Citizen
from app.simulation.actions import ACTIONS


def _get_token(client, email="socialtest@example.com", password="Pass1234"):
    client.post("/api/v1/auth/signup", json={"email": email, "password": password})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


def _make_citizen(client, headers, name=None):
    payload = {"name": name} if name else {}
    resp = client.post("/api/v1/citizens", json=payload, headers=headers)
    return resp.json()["id"]


# ---- balance check: create_post must be a genuine contender, not a rare edge case ----

def test_create_post_and_socialize_are_both_competitive():
    """Regression test for the Phase 4 balance bug: create_post originally
    won against socialize only ~1.5% of the time across random personalities,
    meaning the simulation almost never generated its own posts. After the
    fix it should win a meaningful (not dominant) share."""
    post_action = next(a for a in ACTIONS if a.name == "create_post")
    social_action = next(a for a in ACTIONS if a.name == "socialize")

    wins = 0
    trials = 1000
    rng = random.Random(42)
    for _ in range(trials):
        personality = {
            "kindness": rng.randint(0, 100),
            "intelligence": rng.randint(0, 100),
            "ambition": rng.randint(0, 100),
            "social": rng.randint(0, 100),
            "honesty": rng.randint(0, 100),
        }
        happiness = rng.uniform(0, 100)
        c = Citizen(
            name="X", age=30, personality_json=personality, mood=0.0,
            happiness=happiness, energy=100.0, health=100.0,
            job="unemployed", current_activity="idle",
        )
        if post_action.utility(c) > social_action.utility(c):
            wins += 1

    win_rate = wins / trials
    # Range widened downward after socialize's utility weights were bumped
    # (0.5/0.15 -> 0.65/0.2) to fix a separate bug: work's utility used to
    # spike right after every sleep, effectively locking citizens into a
    # work<->sleep loop that starved both socialize AND create_post. With
    # that fixed, socialize is now meaningfully stronger on average, which
    # correctly pulls create_post's relative win rate down — the guard here
    # is still "not near-zero" (the original bug) and "not dominant",
    # not a fixed midpoint.
    assert 0.05 < win_rate < 0.5, f"create_post win rate {win_rate:.1%} is out of the intended balanced range"


# ---- posts ----

def test_create_post_requires_auth(client):
    resp = client.post("/api/v1/citizens/1/posts", json={"content": "hi"})
    assert resp.status_code == 403  # HTTPBearer: no Authorization header at all


def test_create_post_for_missing_citizen(client):
    token = _get_token(client)
    resp = client.post(
        "/api/v1/citizens/999999/posts",
        json={"content": "ghost post"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_create_and_read_post(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    citizen_id = _make_citizen(client, headers, name="Alice")

    resp = client.post(
        f"/api/v1/citizens/{citizen_id}/posts",
        json={"content": "Hello world!"},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["citizen_id"] == citizen_id
    assert body["content"] == "Hello world!"


# ---- feed ----

def test_feed_is_public_and_paginated(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    citizen_id = _make_citizen(client, headers)
    for i in range(3):
        client.post(f"/api/v1/citizens/{citizen_id}/posts", json={"content": f"post {i}"}, headers=headers)

    resp = client.get("/api/v1/feed?page=1&page_size=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 3
    assert len(body["items"]) == 2
    # newest first
    assert body["items"][0]["content"] == "post 2"


def test_feed_includes_citizen_name_and_counts(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    author_id = _make_citizen(client, headers, name="Feed Author")
    commenter_id = _make_citizen(client, headers, name="Feed Commenter")

    post_resp = client.post(
        f"/api/v1/citizens/{author_id}/posts", json={"content": "look at this"}, headers=headers
    )
    post_id = post_resp.json()["id"]
    client.post(
        f"/api/v1/posts/{post_id}/comments",
        json={"citizen_id": commenter_id, "content": "nice!"},
        headers=headers,
    )
    client.post(
        f"/api/v1/posts/{post_id}/reactions",
        json={"citizen_id": commenter_id},
        headers=headers,
    )

    feed = client.get("/api/v1/feed").json()
    item = next(i for i in feed["items"] if i["id"] == post_id)
    assert item["citizen_name"] == "Feed Author"
    assert item["comment_count"] == 1
    assert item["reaction_count"] == 1


# ---- comments ----

def test_comment_on_missing_post(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    citizen_id = _make_citizen(client, headers)
    resp = client.post(
        "/api/v1/posts/999999/comments",
        json={"citizen_id": citizen_id, "content": "hi"},
        headers=headers,
    )
    assert resp.status_code == 404


def test_comment_requires_auth(client):
    resp = client.post("/api/v1/posts/1/comments", json={"citizen_id": 1, "content": "hi"})
    assert resp.status_code == 403  # HTTPBearer: no Authorization header at all


def test_list_comments_public(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    citizen_id = _make_citizen(client, headers)
    post_id = client.post(
        f"/api/v1/citizens/{citizen_id}/posts", json={"content": "commentable"}, headers=headers
    ).json()["id"]
    client.post(
        f"/api/v1/posts/{post_id}/comments",
        json={"citizen_id": citizen_id, "content": "self-comment"},
        headers=headers,
    )

    resp = client.get(f"/api/v1/posts/{post_id}/comments")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ---- reactions ----

def test_reaction_duplicate_rejected(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    author_id = _make_citizen(client, headers)
    liker_id = _make_citizen(client, headers)
    post_id = client.post(
        f"/api/v1/citizens/{author_id}/posts", json={"content": "likeable"}, headers=headers
    ).json()["id"]

    first = client.post(
        f"/api/v1/posts/{post_id}/reactions", json={"citizen_id": liker_id}, headers=headers
    )
    assert first.status_code == 201

    second = client.post(
        f"/api/v1/posts/{post_id}/reactions", json={"citizen_id": liker_id}, headers=headers
    )
    assert second.status_code == 409


def test_reaction_remove(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    author_id = _make_citizen(client, headers)
    liker_id = _make_citizen(client, headers)
    post_id = client.post(
        f"/api/v1/citizens/{author_id}/posts", json={"content": "likeable"}, headers=headers
    ).json()["id"]
    client.post(f"/api/v1/posts/{post_id}/reactions", json={"citizen_id": liker_id}, headers=headers)

    resp = client.delete(f"/api/v1/posts/{post_id}/reactions/{liker_id}", headers=headers)
    assert resp.status_code == 204

    resp2 = client.delete(f"/api/v1/posts/{post_id}/reactions/{liker_id}", headers=headers)
    assert resp2.status_code == 404


# ---- follows ----

def test_follow_self_rejected(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    citizen_id = _make_citizen(client, headers)
    resp = client.post(f"/api/v1/citizens/{citizen_id}/follow/{citizen_id}", headers=headers)
    assert resp.status_code == 400


def test_follow_duplicate_rejected(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    a = _make_citizen(client, headers)
    b = _make_citizen(client, headers)

    first = client.post(f"/api/v1/citizens/{a}/follow/{b}", headers=headers)
    assert first.status_code == 201
    second = client.post(f"/api/v1/citizens/{a}/follow/{b}", headers=headers)
    assert second.status_code == 409


def test_follow_missing_citizen(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    a = _make_citizen(client, headers)
    resp = client.post(f"/api/v1/citizens/{a}/follow/999999", headers=headers)
    assert resp.status_code == 404


def test_unfollow(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    a = _make_citizen(client, headers)
    b = _make_citizen(client, headers)
    client.post(f"/api/v1/citizens/{a}/follow/{b}", headers=headers)

    resp = client.delete(f"/api/v1/citizens/{a}/follow/{b}", headers=headers)
    assert resp.status_code == 204

    resp2 = client.delete(f"/api/v1/citizens/{a}/follow/{b}", headers=headers)
    assert resp2.status_code == 404


def test_followers_and_following_lists(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    a = _make_citizen(client, headers)
    b = _make_citizen(client, headers)
    client.post(f"/api/v1/citizens/{a}/follow/{b}", headers=headers)

    followers_of_b = client.get(f"/api/v1/citizens/{b}/followers").json()
    assert any(f["follower_id"] == a for f in followers_of_b)

    following_of_a = client.get(f"/api/v1/citizens/{a}/following").json()
    assert any(f["followee_id"] == b for f in following_of_a)


# ---- tick engine integration: create_post writes a real post row ----

def test_tick_can_generate_real_posts(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    # Craft a personality that reliably favors create_post over the other
    # actions (low social + high honesty + unemployed so work never
    # competes) instead of relying on enough random citizens/ticks to make
    # a zero-post outcome merely unlikely — the latter was measured to
    # still fail ~5-20% of the time depending on trial count after the
    # work/socialize utility rebalance (see simulation/actions.py),
    # which is too flaky for a test suite.
    headers_auth = headers
    payload = {
        "name": "Poster",
        "job": "unemployed",
        "personality_json": {
            "kindness": 50, "intelligence": 50, "ambition": 0, "social": 20, "honesty": 100,
        },
    }
    client.post("/api/v1/citizens", json=payload, headers=headers_auth)

    for _ in range(20):
        client.post("/api/v1/simulation/tick", headers=headers)

    feed = client.get("/api/v1/feed?page_size=100").json()
    assert feed["total"] > 0, "tick engine never generated a single post across 20 ticks for a post-favoring citizen"


# ---- websocket ----

def test_websocket_receives_new_post_broadcast(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    citizen_id = _make_citizen(client, headers)

    with client.websocket_connect("/ws/feed") as ws:
        client.post(
            f"/api/v1/citizens/{citizen_id}/posts",
            json={"content": "ws test post"},
            headers=headers,
        )
        message = ws.receive_json()
        assert message["type"] == "new_post"
        assert message["content"] == "ws test post"
        assert message["citizen_id"] == citizen_id
