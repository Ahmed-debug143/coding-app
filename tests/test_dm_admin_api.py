from aula import auth, db, repo


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


def test_dm_contacts_include_connections_and_shared_group_members(client):
    alice = register(client, "alice-contact@example.edu")
    friend = register(client, "friend-contact@example.edu")
    groupmate = register(client, "groupmate-contact@example.edu")
    blocked = register(client, "blocked-contact@example.edu")
    unrelated = register(client, "unrelated-contact@example.edu")

    alice_session = login(client, "alice-contact@example.edu")
    requested = client.post(
        "/api/connections",
        headers={"X-CSRF-Token": alice_session["csrf_token"]},
        json={"user_id": friend["user"]["id"]},
    )
    assert requested.status_code == 201
    friend_session = login(client, "friend-contact@example.edu")
    accepted = client.post(
        f"/api/connections/{alice_session['user']['id']}/respond?accept=true",
        headers={"X-CSRF-Token": friend_session["csrf_token"]},
    )
    assert accepted.status_code == 200

    with db.session() as conn:
        group_id = conn.execute(
            "INSERT INTO groupes(name, owner_id, created_at) VALUES (?, ?, ?)",
            ("Groupe partagé", alice["user"]["id"], "2026-01-01T00:00:00"),
        ).lastrowid
        for user_id, role in (
            (alice["user"]["id"], "owner"),
            (groupmate["user"]["id"], "member"),
            (blocked["user"]["id"], "member"),
        ):
            conn.execute(
                "INSERT INTO group_members(group_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)",
                (group_id, user_id, role, "2026-01-01T00:00:00"),
            )
        repo.block_user(conn, alice["user"]["id"], blocked["user"]["id"])

    login(client, "alice-contact@example.edu")
    conversations = client.get("/api/dm/conversations")
    assert conversations.status_code == 200
    contacts = {
        item["id"]: item for item in conversations.json() if item["kind"] == "dm"
    }

    assert set(contacts) == {friend["user"]["id"], groupmate["user"]["id"]}
    assert contacts[friend["user"]["id"]]["last_body"] == ""
    assert contacts[friend["user"]["id"]]["is_connected"] == 1
    assert contacts[groupmate["user"]["id"]]["shared_group_count"] == 1
    assert client.get(f"/api/dm/{groupmate['user']['id']}/messages").json()["messages"] == []
    assert client.get(f"/api/dm/{blocked['user']['id']}/messages").status_code == 403
    assert unrelated["user"]["id"] not in contacts


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
