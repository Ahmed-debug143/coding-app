from aula import auth, db


PASSWORD = "motdepasse-tres-solide-2026"


def register(client, email, name):
    response = client.post("/api/auth/register", json={
        "email": email,
        "name": name,
        "password": PASSWORD,
    })
    assert response.status_code == 201
    result = response.json()
    return {
        "user": result["user"],
        "csrf": result["csrf_token"],
        "cookie": client.cookies.get("campusia_session"),
    }


def switch_user(client, identity):
    client.cookies.clear()
    client.cookies.set("campusia_session", identity["cookie"])


def test_two_student_realistic_journey_persists_across_relogin(client):
    alice = register(client, "alice-final@example.edu", "Alice Étudiante")
    bob = register(client, "bob-final@example.edu", "Bob Étudiant")

    switch_user(client, alice)
    profile = client.put("/api/profile/me", headers={"X-CSRF-Token": alice["csrf"]}, json={
        "name": "Alice Étudiante",
        "school": "Université Campus",
        "faculty": "Science",
        "filiere": "Informatique",
        "level": "L3",
        "skills": ["Python", "FastAPI"],
        "interests": ["IA", "robotique"],
        "project_types": ["Hackathon"],
        "availability": "soir",
    })
    assert profile.status_code == 200
    assert "Python" in profile.json()["skills"]

    switch_user(client, bob)
    bob_profile = client.put("/api/profile/me", headers={"X-CSRF-Token": bob["csrf"]}, json={
        "name": "Bob Étudiant",
        "school": "Université Campus",
        "faculty": "Science",
        "filiere": "Informatique",
        "level": "L3",
        "skills": ["Python", "SQL"],
        "interests": ["IA"],
        "project_types": ["Hackathon"],
        "availability": "week-end",
    })
    assert bob_profile.status_code == 200

    switch_user(client, alice)

    found = client.get("/api/students?q=Informatique")
    assert found.status_code == 200
    assert any(item["id"] == bob["user"]["id"] for item in found.json())

    requested = client.post(
        "/api/connections",
        headers={"X-CSRF-Token": alice["csrf"]},
        json={"user_id": bob["user"]["id"]},
    )
    assert requested.status_code == 201

    switch_user(client, bob)
    accepted = client.post(
        f"/api/connections/{alice['user']['id']}/respond?accept=true",
        headers={"X-CSRF-Token": bob["csrf"]},
    )
    assert accepted.status_code == 200

    dm = client.post(
        f"/api/dm/{alice['user']['id']}/messages",
        headers={"X-CSRF-Token": bob["csrf"]},
        json={"body": "Bonjour Alice, notre projet peut commencer."},
    )
    assert dm.status_code == 201

    switch_user(client, alice)
    group = client.post(
        "/api/groups",
        headers={"X-CSRF-Token": alice["csrf"]},
        json={
            "name": "Projet concours",
            "project_name": "Campusia Demo",
            "subject": "Informatique",
            "filiere": "Informatique",
            "description": "Projet de démonstration",
            "objective": "Présenter une application universitaire",
            "max_members": 8,
            "skills_wanted": ["Python"],
            "visibility": "public",
            "recruitment_open": True,
        },
    )
    assert group.status_code == 201
    group_id = group.json()["id"]

    invitation = client.post(
        f"/api/groups/{group_id}/invitations",
        headers={"X-CSRF-Token": alice["csrf"]},
        json={"user_id": bob["user"]["id"]},
    )
    assert invitation.status_code == 200

    switch_user(client, bob)
    invitations = client.get("/api/group-invitations")
    assert invitations.status_code == 200
    invitation_id = next(item["id"] for item in invitations.json() if item["group_name"] == "Projet concours")
    join = client.post(
        f"/api/group-invitations/{invitation_id}/respond?accept=true",
        headers={"X-CSRF-Token": bob["csrf"]},
    )
    assert join.status_code == 200

    chat = client.post(
        f"/api/groups/{group_id}/messages",
        headers={"X-CSRF-Token": bob["csrf"]},
        json={"body": "Je commence les développements."},
    )
    assert chat.status_code == 201

    uploaded = client.post(
        f"/api/groups/{group_id}/files",
        headers={"X-CSRF-Token": bob["csrf"]},
        files={"file": ("cahier.txt", b"Cahier des charges du projet", "text/plain")},
    )
    assert uploaded.status_code == 201
    assert client.get(uploaded.json()["url"]).status_code == 200

    switch_user(client, alice)
    task = client.post(
        f"/api/groups/{group_id}/tasks",
        headers={"X-CSRF-Token": alice["csrf"]},
        json={
            "title": "Préparer la démonstration",
            "description": "Préparer les écrans du jury",
            "priority": "high",
            "due_at": "2026-12-15",
            "assignee_ids": [bob["user"]["id"]],
        },
    )
    assert task.status_code == 201
    task_id = task.json()["id"]

    switch_user(client, bob)
    status = client.post(
        f"/api/tasks/{task_id}/status",
        headers={"X-CSRF-Token": bob["csrf"]},
        json={"status": "done"},
    )
    assert status.status_code == 200

    event = client.post(
        "/api/calendar/events",
        headers={"X-CSRF-Token": bob["csrf"]},
        json={
            "title": "Réunion jury",
            "kind": "reunion",
            "description": "Préparation finale",
            "starts_at": "2026-12-10T14:00:00",
            "ends_at": "2026-12-10T15:00:00",
            "group_id": group_id,
        },
    )
    assert event.status_code == 403

    resource = client.post(
        "/api/resources/upload",
        headers={"X-CSRF-Token": bob["csrf"]},
        data={"title": "Support jury", "kind": "Document", "group_id": str(group_id)},
        files={"file": ("support.txt", b"Support du concours", "text/plain")},
    )
    assert resource.status_code == 201

    publication = client.post(
        "/api/publications",
        headers={"X-CSRF-Token": bob["csrf"]},
        json={"body": "Notre équipe finalise le projet pour le concours"},
    )
    assert publication.status_code == 201
    publication_id = publication.json()["id"]

    comment = client.post(
        f"/api/publications/{publication_id}/comments",
        headers={"X-CSRF-Token": bob["csrf"]},
        json={"body": "La démonstration est prête"},
    )
    assert comment.status_code == 201
    reaction = client.post(
        f"/api/publications/{publication_id}/reactions",
        headers={"X-CSRF-Token": bob["csrf"]},
        json={"emoji": "👍"},
    )
    assert reaction.status_code == 200

    switch_user(client, alice)
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["profile_completion"]["percent"] >= 8

    logout = client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": alice["csrf"]},
    )
    assert logout.status_code == 200
    relogin = client.post("/api/auth/login", json={
        "email": "alice-final@example.edu",
        "password": PASSWORD,
    })
    assert relogin.status_code == 200
    persisted = client.get("/api/profile/me")
    assert persisted.status_code == 200
    assert persisted.json()["filiere"] == "Informatique"
