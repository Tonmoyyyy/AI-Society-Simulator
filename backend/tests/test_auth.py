def test_signup_creates_user(client):
    resp = client.post(
        "/api/v1/auth/signup",
        json={"email": "alice@example.com", "password": "StrongPass123"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "alice@example.com"
    assert body["role"] == "spectator"
    assert "id" in body
    assert "password" not in body  # never leak the password/hash


def test_signup_duplicate_email_rejected(client):
    client.post("/api/v1/auth/signup", json={"email": "bob@example.com", "password": "x"})
    resp = client.post("/api/v1/auth/signup", json={"email": "bob@example.com", "password": "y"})
    assert resp.status_code == 400
    assert "already exists" in resp.json()["error"]["message"]


def test_login_success_returns_tokens(client):
    client.post("/api/v1/auth/signup", json={"email": "carol@example.com", "password": "MyPass123"})
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "carol@example.com", "password": "MyPass123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


def test_login_wrong_password_rejected(client):
    client.post("/api/v1/auth/signup", json={"email": "dave@example.com", "password": "Correct123"})
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "dave@example.com", "password": "Wrong123"},
    )
    assert resp.status_code == 401


def test_login_unknown_email_rejected(client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "whatever"},
    )
    assert resp.status_code == 401


def test_me_requires_token(client):
    resp = client.get("/api/v1/auth/me")
    # HTTPBearer (not OAuth2PasswordBearer) returns 403 when no
    # Authorization header is present at all; an invalid/expired token
    # still gets 401 from our own credentials check (see test below).
    assert resp.status_code == 403


def test_me_returns_current_user_with_valid_token(client):
    client.post("/api/v1/auth/signup", json={"email": "erin@example.com", "password": "Pass1234"})
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "erin@example.com", "password": "Pass1234"},
    )
    access_token = login_resp.json()["access_token"]

    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "erin@example.com"


def test_me_rejects_invalid_token(client):
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_refresh_returns_new_access_token(client):
    client.post("/api/v1/auth/signup", json={"email": "frank@example.com", "password": "Pass1234"})
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "frank@example.com", "password": "Pass1234"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_refresh_rejects_access_token_used_as_refresh(client):
    client.post("/api/v1/auth/signup", json={"email": "grace@example.com", "password": "Pass1234"})
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "grace@example.com", "password": "Pass1234"},
    )
    access_token = login_resp.json()["access_token"]

    # using an access token where a refresh token is expected must fail
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
