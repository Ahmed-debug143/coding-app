from aula import auth, db


PASSWORD = "motdepasse-tres-solide-2026"


def register(client, email):
    response = client.post("/api/auth/register", json={
        "email": email,
        "name": email.split("@")[0],
        "password": PASSWORD,
    })
    assert response.status_code == 201
    return response.json()


def login(client, email):
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return response.json()


def test_private_messages_require_an_accepted_connection_or_shared_group(client):
    alice = register(client, "alice-dm@example.edu")
    bob = register(client, "bob-dm@example.edu")

    alice_session = login(client, "alice-dm@example.edu")
    blocked = client.get("/api/dm/conversations")
    assert blocked.status_code == 200

    student_b = client.post(
        "/api/connections",
        headers={"X-CSRF-Token": alice_session["csrf_token"]},
        json={"user_id": bob["user"]["id"]},
    )
    assert student_b.status_code == 201

    bob_session = login(client, "bob-dm@example.edu")
    accepted = client.post(
        f"/api/connections/{alice_session['user']['id']}/respond?accept=true",
        headers={"X-CSRF-Token": bob_session["csrf_token"]},
    )
    assert accepted.status_code == 200

    alice_session = login(client, "alice-dm@example.edu")
    sent = client.post(
        f"/api/dm/{bob_session['user']['id']}/messages",
        headers={"X-CSRF-Token": alice_session["csrf_token"]},
        json={"body": "Bonjour, pouvons-nous collaborer ?"},
    )
    assert sent.status_code == 201
    assert sent.json()["body"] == "Bonjour, pouvons-nous collaborer ?"

    messages = client.get(f"/api/dm/{bob_session['user']['id']}/messages")
    assert messages.status_code == 200
    assert messages.json()["messages"][0]["body"] == "Bonjour, pouvons-nous collaborer ?"

    edited = client.put(
        f"/api/dm/{bob_session['user']['id']}/messages/{sent.json()['id']}",
        headers={"X-CSRF-Token": alice_session["csrf_token"]},
        json={"body": "Message privé modifié"},
    )
    assert edited.status_code == 200
    assert edited.json()["body"] == "Message privé modifié"

    deleted = client.delete(
        f"/api/dm/{bob_session['user']['id']}/messages/{sent.json()['id']}",
        headers={"X-CSRF-Token": alice_session["csrf_token"]},
    )
    assert deleted.status_code == 200


def test_admin_routes_are_server_restricted_and_suspend_persists(client):
    student = register(client, "student-admin-test@example.edu")
    forbidden = client.get("/api/admin/stats")
    assert forbidden.status_code == 403

    with db.session() as conn:
        admin = auth.create_user(
            conn,
            email="admin-campusia@example.edu",
            password=PASSWORD,
            name="Administrateur",
            role="admin",
            verified=1,
        )

    response = client.post("/api/auth/login", json={
        "email": "admin-campusia@example.edu",
        "password": PASSWORD,
    })
    assert response.status_code == 200
    csrf = response.json()["csrf_token"]

    stats = client.get("/api/admin/stats")
    assert stats.status_code == 200
    assert set(stats.json()) >= {"users", "groups", "tasks", "resources", "reports"}

    suspended = client.post(
        f"/api/admin/users/{student['user']['id']}/suspension",
        headers={"X-CSRF-Token": csrf},
        json={"suspended": True},
    )
    assert suspended.status_code == 200
    assert suspended.json()["suspended"] is True

    audit = client.get("/api/admin/audit")
    assert audit.status_code == 200
    assert any(
        item["action"] == "suspend"
        and item["target_type"] == "user"
        and item["target_id"] == student["user"]["id"]
        for item in audit.json()
    )
