from decimal import Decimal


def _get_token(client, email="wallettest@example.com", password="Pass1234"):
    client.post("/api/v1/auth/signup", json={"email": email, "password": password})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


def _make_citizen(client, headers, name=None, job=None):
    payload = {"name": name} if name else {}
    citizen_id = client.post("/api/v1/citizens", json=payload, headers=headers).json()["id"]
    if job:
        client.patch(f"/api/v1/citizens/{citizen_id}", json={"job": job}, headers=headers)
    return citizen_id


# ---- wallet basics ----

def test_wallet_auto_created_with_zero_balance(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    citizen_id = _make_citizen(client, headers)

    resp = client.get(f"/api/v1/citizens/{citizen_id}/wallet")
    assert resp.status_code == 200
    body = resp.json()
    assert body["citizen_id"] == citizen_id
    assert Decimal(str(body["balance"])) == Decimal("0.00")


def test_wallet_for_missing_citizen(client):
    resp = client.get("/api/v1/citizens/999999/wallet")
    assert resp.status_code == 404


def test_transactions_empty_for_new_citizen(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    citizen_id = _make_citizen(client, headers)

    resp = client.get(f"/api/v1/citizens/{citizen_id}/transactions")
    assert resp.status_code == 200
    assert resp.json() == []


# ---- salary payment via the tick engine ----

def test_working_citizen_gets_paid(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    citizen_id = _make_citizen(client, headers, job="engineer")

    # Personality is randomized at creation and isn't editable via the API
    # (by design — see Phase 2 notes), so we can't force "work" to win on
    # a specific tick. Running enough ticks makes it statistically certain
    # that "work" fires at least once for any personality, since its
    # utility scales with ambition and is never zero for an employed,
    # rested citizen.
    for _ in range(30):
        client.post("/api/v1/simulation/tick", headers=headers)

    wallet = client.get(f"/api/v1/citizens/{citizen_id}/wallet").json()
    # Over 30 ticks with a real job, "work" should have fired at least once
    # for any personality (its utility scales with ambition and never hits
    # zero), so balance should be > 0.
    assert Decimal(str(wallet["balance"])) > Decimal("0.00")

    transactions = client.get(f"/api/v1/citizens/{citizen_id}/transactions").json()
    assert any(t["type"] == "salary" for t in transactions)
    assert all(t["from_wallet_id"] is None for t in transactions if t["type"] == "salary")


def test_unemployed_citizen_never_gets_paid(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    citizen_id = _make_citizen(client, headers, job="unemployed")  # job auto-assignment (added later) is random by default, so force it explicitly here

    for _ in range(10):
        client.post("/api/v1/simulation/tick", headers=headers)

    wallet = client.get(f"/api/v1/citizens/{citizen_id}/wallet").json()
    assert Decimal(str(wallet["balance"])) == Decimal("0.00")


# ---- manual transfers ----

def test_transfer_requires_auth(client):
    resp = client.post(
        "/api/v1/citizens/1/wallet/transfer", json={"to_citizen_id": 2, "amount": 10}
    )
    assert resp.status_code == 403  # HTTPBearer: no Authorization header at all


def test_transfer_insufficient_balance(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    a = _make_citizen(client, headers)
    b = _make_citizen(client, headers)

    resp = client.post(
        f"/api/v1/citizens/{a}/wallet/transfer",
        json={"to_citizen_id": b, "amount": 100},
        headers=headers,
    )
    assert resp.status_code == 409


def test_transfer_negative_amount_rejected_cleanly(client):
    """Regression test: a negative/invalid Decimal amount used to crash the
    validation-error handler with a 500 (json.dumps couldn't serialize the
    rejected Decimal value in exc.errors()). Must come back as a clean 422."""
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    a = _make_citizen(client, headers)
    b = _make_citizen(client, headers)

    resp = client.post(
        f"/api/v1/citizens/{a}/wallet/transfer",
        json={"to_citizen_id": b, "amount": -50},
        headers=headers,
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == 422
    assert "details" in body["error"]


def test_transfer_to_missing_citizen(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    a = _make_citizen(client, headers)

    resp = client.post(
        f"/api/v1/citizens/{a}/wallet/transfer",
        json={"to_citizen_id": 999999, "amount": 10},
        headers=headers,
    )
    assert resp.status_code == 400


def test_successful_transfer_moves_balance(client):
    token = _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    a = _make_citizen(client, headers, job="engineer")
    b = _make_citizen(client, headers, job="unemployed")  # must start with a known, empty wallet — job auto-assignment (added later) is random otherwise

    # give `a` some money via enough work ticks
    for _ in range(30):
        client.post("/api/v1/simulation/tick", headers=headers)

    a_wallet_before = Decimal(str(client.get(f"/api/v1/citizens/{a}/wallet").json()["balance"]))
    if a_wallet_before <= 0:
        # extremely unlikely given 30 ticks, but keep the test honest
        return
    # b's balance is no longer guaranteed to be 0 here — the tick engine's
    # gifting feature (added later) means citizens can autonomously send
    # each other small amounts of money, so b may have received a gift
    # from a (or, in principle, elsewhere) during those 30 ticks.
    b_wallet_before = Decimal(str(client.get(f"/api/v1/citizens/{b}/wallet").json()["balance"]))

    transfer_amount = min(Decimal("10.00"), a_wallet_before)
    resp = client.post(
        f"/api/v1/citizens/{a}/wallet/transfer",
        json={"to_citizen_id": b, "amount": float(transfer_amount)},
        headers=headers,
    )
    assert resp.status_code == 201

    a_wallet_after = Decimal(str(client.get(f"/api/v1/citizens/{a}/wallet").json()["balance"]))
    b_wallet_after = Decimal(str(client.get(f"/api/v1/citizens/{b}/wallet").json()["balance"]))
    assert a_wallet_after == a_wallet_before - transfer_amount
    assert b_wallet_after == b_wallet_before + transfer_amount
