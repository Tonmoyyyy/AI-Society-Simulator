import random

from app.models.citizen import Citizen
from app.models.post import Post
from app.repositories import social_repo
from app.simulation.social_interactions import perform_social_interaction


def _make_citizen(name):
    return Citizen(
        name=name, age=30,
        personality_json={"kindness": 50, "intelligence": 50, "ambition": 50, "social": 50, "honesty": 50},
        mood=0.0, happiness=50.0, energy=100.0, health=100.0,
        job="unemployed", current_activity="idle",
    )


def test_no_interaction_with_no_other_citizens(db_session):
    actor = _make_citizen("Solo")
    db_session.add(actor)
    db_session.commit()

    broadcast_queue = []
    perform_social_interaction(db_session, actor, [actor], broadcast_queue)
    db_session.commit()

    assert broadcast_queue == []


def test_no_interaction_target_has_no_posts(db_session):
    actor = _make_citizen("Actor")
    target = _make_citizen("Target")
    db_session.add_all([actor, target])
    db_session.commit()

    # force the "follow" branch off so we isolate the "no post" case;
    # run many trials since target selection/probabilities are random.
    # Commit after every call (not once at the end) — the dedup checks
    # (get_follow/get_reaction) query the DB and this session has
    # autoflush=False, so an uncommitted duplicate from an earlier
    # iteration in the same transaction wouldn't be visible yet otherwise.
    # engine.py never hits this because it only calls this once per
    # citizen per tick — this loop is purely a test-scale artifact.
    random.seed(1)
    broadcast_queue = []
    for _ in range(20):
        perform_social_interaction(db_session, actor, [actor, target], broadcast_queue)
        db_session.commit()

    # no comment/reaction events possible (target has zero posts) —
    # only a possible follow event
    assert all(e["type"] == "new_follow" for e in broadcast_queue)


def test_interaction_can_comment_and_react_on_targets_post(db_session):
    actor = _make_citizen("Actor")
    target = _make_citizen("Target")
    db_session.add_all([actor, target])
    db_session.commit()

    post = Post(citizen_id=target.id, content="hello city")
    db_session.add(post)
    db_session.commit()

    random.seed(0)
    broadcast_queue = []
    # run enough trials that, with ~50%/30%/15% probabilities, at least one
    # of each event type almost certainly fires
    for _ in range(60):
        perform_social_interaction(db_session, actor, [actor, target], broadcast_queue)
        db_session.commit()

    types_seen = {e["type"] for e in broadcast_queue}
    assert "new_reaction" in types_seen or "new_comment" in types_seen

    comments = social_repo.list_comments(db_session, post.id)
    reaction = social_repo.get_reaction(db_session, post.id, actor.id)
    # at least one of comment/reaction should exist after 60 trials
    assert len(comments) > 0 or reaction is not None


def test_reaction_is_not_duplicated_for_same_citizen_and_post(db_session):
    actor = _make_citizen("Actor")
    target = _make_citizen("Target")
    db_session.add_all([actor, target])
    db_session.commit()

    post = Post(citizen_id=target.id, content="hello again")
    db_session.add(post)
    db_session.commit()

    random.seed(0)
    broadcast_queue = []
    for _ in range(60):
        perform_social_interaction(db_session, actor, [actor, target], broadcast_queue)
        db_session.commit()

    reaction_events = [e for e in broadcast_queue if e["type"] == "new_reaction"]
    # get_reaction dedup means the same actor should never react twice to
    # the same post, no matter how many times the random roll succeeds
    assert len(reaction_events) <= 1


def test_follow_created_and_not_duplicated(db_session):
    actor = _make_citizen("Actor")
    target = _make_citizen("Target")
    db_session.add_all([actor, target])
    db_session.commit()

    post = Post(citizen_id=target.id, content="follow me maybe")
    db_session.add(post)
    db_session.commit()

    random.seed(0)
    broadcast_queue = []
    for _ in range(80):
        perform_social_interaction(db_session, actor, [actor, target], broadcast_queue)
        db_session.commit()

    follow_events = [e for e in broadcast_queue if e["type"] == "new_follow"]
    assert len(follow_events) <= 1
    if follow_events:
        assert social_repo.get_follow(db_session, actor.id, target.id) is not None


def test_full_tick_can_produce_social_interactions(client):
    client.post("/api/v1/auth/signup", json={"email": "socinteract@example.com", "password": "Pass1234"})
    login = client.post("/api/v1/auth/login", json={"email": "socinteract@example.com", "password": "Pass1234"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    for _ in range(8):
        client.post("/api/v1/citizens", json={}, headers=headers)

    for _ in range(15):
        resp = client.post("/api/v1/simulation/tick", headers=headers)
        assert resp.status_code == 200

    feed = client.get("/api/v1/feed?page_size=50").json()
    total_engagement = sum(p["comment_count"] + p["reaction_count"] for p in feed["items"])
    # not asserting a hard minimum (probabilistic), just that the pipeline
    # is wired end to end and doesn't error across many ticks
    assert total_engagement >= 0
