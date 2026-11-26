import hashlib

from fastapi.testclient import TestClient

from aula import db
from aula.auth_routes import SESSION_COOKIE
from main import app


def register_payload(**overrides):
    payload = {
        "name": "Camille Étudiante",
        "email": "camille@example.edu",
        "password": "UnePhraseDePasse2026!",
    }
    payload.update(overrides)
    return payload


def create_account(client, **overrides):
    response = client.post("/api/auth/register", json=register_payload(**overrides))
    assert response.status_code == 201
    return response


def test_register_creates_student_and_persistent_cookie(client):
    response = create_account(client)
    body = response.json()
    cookie = response.headers["set-cookie"].lower()

    assert body["authenticated"] is True
    assert body["user"]["email"] == "camille@example.edu"
    assert body["user"]["role"] == "student"
    assert "password_hash" not in body["user"]
    assert body["csrf_token"]
    assert f"{SESSION_COOKIE}=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "max-age=" in cookie

    with db.session() as conn:
        user = db.one(conn, "SELECT * FROM users WHERE email = ?", ("camille@example.edu",))
        stored_token = db.one(conn, "SELECT token_hash FROM sessions WHERE user_id = ?", (user["id"],))
    assert user["role"] == "student"
    assert user["password_hash"] != "UnePhraseDePasse2026!"
    assert user["password_hash"].startswith("scrypt$")
    raw_cookie = client.cookies.get(SESSION_COOKIE)
    assert stored_token["token_hash"] == hashlib.sha256(raw_cookie.encode()).hexdigest()
    assert raw_cookie not in stored_token["token_hash"]


def test_registration_rejects_duplicate_email_case_insensitively(client):
    create_account(client)
    response = client.post(
        "/api/auth/register",
        json=register_payload(email="CAMILLE@example.edu", name="Camille Deux"),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["field"] == "email"


def test_registration_rejects_invalid_email_name_and_password(client):
    response = client.post(
        "/api/auth/register",
        json=register_payload(email="pas-une-adresse", name=" A ", password="court"),
    )
    assert response.status_code == 422
    assert response.json()["detail"]


def test_password_policy_accepts_long_passphrases_and_rejects_whitespace_or_oversize(client):
    whitespace = client.post(
        "/api/auth/register",
        json=register_payload(email="spaces@example.edu", password="          "),
    )
    too_long = client.post(
        "/api/auth/register",
        json=register_payload(email="long@example.edu", password="a" * 129),
    )
    accepted = client.post(
        "/api/auth/register",
        json=register_payload(email="passphrase@example.edu", password="une phrase longue sans contraintes"),
    )
    assert whitespace.status_code == 422
    assert too_long.status_code == 422
    assert accepted.status_code == 201


def test_registration_ignores_privileged_fields_from_client(client):
    create_account(client, role="admin", verified=True, is_demo=True)
    with db.session() as conn:
        user = db.one(conn, "SELECT role, email_verified, is_demo FROM users WHERE email = ?", ("camille@example.edu",))
    assert user == {"role": "student", "email_verified": 0, "is_demo": 0}


def test_login_accepts_valid_credentials_and_me_returns_current_user(client):
    create_account(client)
    client.post("/api/auth/logout", headers={"X-CSRF-Token": client.get("/api/auth/me").json()["csrf_token"]})

    response = client.post(
        "/api/auth/login",
        json={"email": " CAMILLE@example.edu ", "password": "UnePhraseDePasse2026!"},
    )
    assert response.status_code == 200
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "camille@example.edu"


def test_login_rejects_wrong_password_and_unknown_user(client):
    create_account(client)
    wrong_password = client.post(
        "/api/auth/login",
        json={"email": "camille@example.edu", "password": "mauvais-mot-de-passe"},
    )
    unknown_user = client.post(
        "/api/auth/login",
        json={"email": "absent@example.edu", "password": "mauvais-mot-de-passe"},
    )
    assert wrong_password.status_code == 401
    assert unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()


def test_current_user_and_workspace_are_protected(client):
    assert client.get("/api/auth/me").status_code == 401
    session_status = client.get("/api/auth/session")
    assert session_status.status_code == 200
    assert session_status.json() == {"authenticated": False}
    workspace = client.get("/app", follow_redirects=False)
    assert workspace.status_code == 303
    assert workspace.headers["location"] == "/?next=%2Fapp"


def test_session_survives_a_new_client_and_page_reload(client):
    create_account(client)
    raw_cookie = client.cookies.get(SESSION_COOKIE)

    with TestClient(app) as refreshed_client:
        refreshed_client.cookies.set(SESSION_COOKIE, raw_cookie)
        response = refreshed_client.get("/api/auth/session")
        workspace = refreshed_client.get("/app")

    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert response.json()["user"]["email"] == "camille@example.edu"
    assert workspace.status_code == 200
    assert 'id="appShell"' in workspace.text


def test_logout_requires_csrf_and_revokes_the_session(client):
    create_account(client)
    missing_csrf = client.post("/api/auth/logout")
    assert missing_csrf.status_code == 403

    csrf = client.get("/api/auth/me").json()["csrf_token"]
    response = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    assert response.json() == {"authenticated": False}
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/session").json() == {"authenticated": False}
    assert client.get("/app", follow_redirects=False).status_code == 303


def test_auth_mutations_reject_foreign_origins(client):
    response = client.post(
        "/api/auth/register",
        json=register_payload(),
        headers={"Origin": "https://attacker.example"},
    )
    assert response.status_code == 403


def test_login_rate_limit_is_enforced(client):
    for _ in range(8):
        response = client.post(
            "/api/auth/login",
            json={"email": "rate-limit@example.edu", "password": "un-mot-de-passe-faux"},
        )
        assert response.status_code == 401
    limited = client.post(
        "/api/auth/login",
        json={"email": "rate-limit@example.edu", "password": "un-mot-de-passe-faux"},
    )
    assert limited.status_code == 429


def test_expired_session_is_rejected_and_removed(client):
    create_account(client)
    with db.session() as conn:
        conn.execute("UPDATE sessions SET expires_at = '2000-01-01T00:00:00' ")
    assert client.get("/api/auth/me").status_code == 401
    with db.session() as conn:
        remaining = db.one(conn, "SELECT COUNT(*) AS count FROM sessions")
    assert remaining["count"] == 0


def test_https_session_cookie_is_marked_secure(client):
    with TestClient(app, base_url="https://testserver") as secure_client:
        response = create_account(secure_client, email="secure@example.edu")
    assert "secure" in response.headers["set-cookie"].lower()
