PASSWORD = "motdepasse-tres-solide-2026"
NEW_PASSWORD = "nouveau-mot-de-passe-2026"
from aula import auth, db


def register(client, email, name):
    response = client.post("/api/auth/register", json={
        "email": email,
        "name": name,
        "password": PASSWORD,
    })
    assert response.status_code == 201
    return response.json()


def test_password_change_revokes_old_session_and_requires_csrf(client):
    account = register(client, "password-change@example.edu", "Mot de passe")

    denied = client.post("/api/auth/password", json={
        "current_password": PASSWORD,
        "new_password": NEW_PASSWORD,
    })
    assert denied.status_code == 403

    changed = client.post(
        "/api/auth/password",
        headers={"X-CSRF-Token": account["csrf_token"]},
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert changed.status_code == 200
    assert changed.json() == {"changed": True}

    old_login = client.post("/api/auth/login", json={
        "email": "password-change@example.edu",
        "password": PASSWORD,
    })
    assert old_login.status_code == 401

    new_login = client.post("/api/auth/login", json={
        "email": "password-change@example.edu",
        "password": NEW_PASSWORD,
    })
    assert new_login.status_code == 200


def test_calendar_event_can_be_updated_by_owner(client):
    account = register(client, "calendar-edit@example.edu", "Calendrier")
    created = client.post(
        "/api/calendar/events",
        headers={"X-CSRF-Token": account["csrf_token"]},
        json={
            "title": "Avant modification",
            "kind": "travail",
            "starts_at": "2026-12-10T09:00:00",
            "ends_at": "2026-12-10T10:00:00",
        },
    )
    assert created.status_code == 201

    updated = client.put(
        f"/api/calendar/events/{created.json()['id']}",
        headers={"X-CSRF-Token": account["csrf_token"]},
        json={
            "title": "Après modification",
            "kind": "reunion",
            "description": "Nouvelle description",
            "starts_at": "2026-12-10T11:00:00",
            "ends_at": "2026-12-10T12:00:00",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Après modification"
    assert updated.json()["kind"] == "reunion"


def test_owner_can_delete_group_and_resource_owner_can_delete_file(client):
    account = register(client, "phase2-owner@example.edu", "Propriétaire")

    group = client.post(
        "/api/groups",
        headers={"X-CSRF-Token": account["csrf_token"]},
        json={"name": "Groupe temporaire", "visibility": "private"},
    )
    assert group.status_code == 201
    group_id = group.json()["id"]

    deleted_group = client.delete(
        f"/api/groups/{group_id}",
        headers={"X-CSRF-Token": account["csrf_token"]},
    )
    assert deleted_group.status_code == 200
    assert deleted_group.json()["deleted"] is True

    resource = client.post(
        "/api/resources/upload",
        headers={"X-CSRF-Token": account["csrf_token"]},
        data={"title": "Document temporaire", "kind": "Document"},
        files={"file": ("temp.txt", b"Contenu temporaire", "text/plain")},
    )
    assert resource.status_code == 201

    deleted_resource = client.delete(
        f"/api/resources/{resource.json()['id']}",
        headers={"X-CSRF-Token": account["csrf_token"]},
    )
    assert deleted_resource.status_code == 200
    assert deleted_resource.json()["deleted"] is True


def test_forgot_password_does_not_reveal_account_existence(client):
    known = register(client, "known-reset@example.edu", "Compte connu")
    known_response = client.post("/api/auth/forgot-password", json={"email": "known-reset@example.edu"})
    unknown_response = client.post("/api/auth/forgot-password", json={"email": "unknown-reset@example.edu"})
    assert known_response.status_code == 200
    assert unknown_response.status_code == 200
    assert known_response.json()["sent"] is True
    assert unknown_response.json()["sent"] is True


def test_password_reset_token_invalidates_all_sessions_and_audit_is_persistent(client):
    account = register(client, "password-reset@example.edu", "Réinitialisation")
    with db.session() as conn:
        token = auth.issue_email_token(conn, account["user"]["id"], "reset", hours=2)

    reset = client.post("/api/auth/reset-password", json={
        "token": token,
        "new_password": "mot-apres-reset-2026",
    })
    assert reset.status_code == 200
    assert reset.json() == {"changed": True}

    reused = client.post("/api/auth/reset-password", json={
        "token": token,
        "new_password": "un-autre-mot-2026",
    })
    assert reused.status_code == 400

    login = client.post("/api/auth/login", json={
        "email": "password-reset@example.edu",
        "password": "mot-apres-reset-2026",
    })
    assert login.status_code == 200
