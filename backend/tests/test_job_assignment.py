from collections import Counter

from app.services.citizen_service import _assign_starting_job
from app.simulation.jobs import JOB_NAMES


def _get_token(client, email="jobtest@example.com", password="Pass1234"):
    client.post("/api/v1/auth/signup", json={"email": email, "password": password})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


def test_assign_starting_job_only_returns_known_jobs_or_unemployed():
    seen = {_assign_starting_job() for _ in range(200)}
    assert seen <= set(JOB_NAMES) | {"unemployed"}


def test_assign_starting_job_distribution_is_not_all_unemployed():
    # Regression test for the original bug: every new citizen defaulted to
    # "unemployed" with no assignment logic at all.
    jobs = [_assign_starting_job() for _ in range(300)]
    counts = Counter(jobs)
    assert counts["unemployed"] < len(jobs)  # not literally everyone unemployed
    # roughly 25% unemployed by design — allow generous statistical slack
    unemployed_rate = counts["unemployed"] / len(jobs)
    assert 0.10 < unemployed_rate < 0.45


def test_created_citizens_get_varied_jobs_via_api(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    jobs = []
    for _ in range(30):
        resp = client.post("/api/v1/citizens", json={}, headers=headers)
        jobs.append(resp.json()["job"])

    distinct_jobs = set(jobs)
    # with 30 citizens and 10+ possible jobs plus unemployed, seeing only
    # one job value would indicate assignment isn't actually randomized
    assert len(distinct_jobs) > 1
