def register(client, email, name="Étudiant"):
    response = client.post("/api/auth/register", json={
        "email": email,
        "name": name,
        "password": "motdepasse-tres-solide-2026",
    })
    assert response.status_code == 201
    return response.json()


def test_resources_support_links_upload_favorites_reports_and_download(client):
    account = register(client, "resource@example.edu")
    csrf = account["csrf_token"]

    link = client.post("/api/resources", headers={"X-CSRF-Token": csrf}, json={
        "title": "Support IA",
        "kind": "Cours",
        "description": "Cours introductif",
        "subject": "Intelligence artificielle",
        "filiere": "Informatique",
        "level": "M1",
        "tags": ["IA", "cours"],
        "link_url": "https://example.edu/ia",
    })
    assert link.status_code == 201
    resource = link.json()

    listed = client.get("/api/resources?subject=Intelligence")
    assert listed.status_code == 200
    assert any(item["id"] == resource["id"] for item in listed.json())

    favorite = client.post(
        f"/api/resources/{resource['id']}/favorite",
        headers={"X-CSRF-Token": csrf},
    )
    assert favorite.status_code == 200
    assert favorite.json()["favorited"] is True

    report = client.post(
        f"/api/resources/{resource['id']}/report",
        headers={"X-CSRF-Token": csrf},
        json={"reason": "Ce lien contient une indication trompeuse."},
    )
    assert report.status_code == 201
    assert report.json() == {"reported": True}

    upload = client.post(
        "/api/resources/upload",
        headers={"X-CSRF-Token": csrf},
        data={
            "title": "Synthèse Python",
            "kind": "Résumé",
            "subject": "Programmation",
            "filiere": "Informatique",
            "level": "L3",
            "tags": "Python, algorithmes",
        },
        files={"file": ("cours.txt", b"Contenu de cours valide", "text/plain")},
    )
    assert upload.status_code == 201
    uploaded = upload.json()

    download = client.get(f"/api/resources/{uploaded['id']}/download")
    assert download.status_code == 200
    assert download.content == b"Contenu de cours valide"


def test_resource_and_calendar_permissions(client):
    owner = register(client, "owner-resource@example.edu")

    group = client.post("/api/groups", headers={"X-CSRF-Token": owner["csrf_token"]}, json={
        "name": "Projet privé",
        "visibility": "private",
        "recruitment_open": False,
    })
    assert group.status_code == 201
    group_id = group.json()["id"]

    uploaded = client.post(
        "/api/resources/upload",
        headers={"X-CSRF-Token": owner["csrf_token"]},
        data={
            "title": "Document privé",
            "kind": "Document",
            "group_id": str(group_id),
        },
        files={"file": ("document.txt", b"Secret du groupe", "text/plain")},
    )
    assert uploaded.status_code == 201
    resource_id = uploaded.json()["id"]
    assert client.get(f"/api/resources/{resource_id}").status_code == 200

    personal = client.post("/api/calendar/events", headers={"X-CSRF-Token": owner["csrf_token"]}, json={
        "title": "Révision",
        "kind": "travail",
        "starts_at": "2026-12-01T09:00:00",
        "ends_at": "2026-12-01T10:00:00",
    })
    assert personal.status_code == 201

    period = client.get("/api/calendar?start=2026-12-01T00:00:00&end=2026-12-02T00:00:00")
    assert period.status_code == 200
    assert any(item["title"] == "Révision" for item in period.json()["events"])


def test_assistant_falls_back_to_explicit_local_analysis(client):
    account = register(client, "assistant@example.edu")
    response = client.post(
        "/api/assistant/answer",
        headers={"X-CSRF-Token": account["csrf_token"]},
        json={"action": "study", "question": "Comment préparer le projet ?"},
    )
    assert response.status_code == 200
    assert response.json()["mode"] == "local"
    assert "Aucun modèle de langage" in response.json()["intro"]


def test_assistant_group_actions_require_a_group(client):
    account = register(client, "assistant-group@example.edu")
    for action in ("summary", "tasks", "organize"):
        response = client.post(
            "/api/assistant/answer",
            headers={"X-CSRF-Token": account["csrf_token"]},
            json={"action": action},
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "Choisissez un groupe pour cette action."


def test_assistant_partner_action_returns_recommendations_or_guidance(client):
    account = register(client, "assistant-partners@example.edu")
    response = client.post(
        "/api/assistant/answer",
        headers={"X-CSRF-Token": account["csrf_token"]},
        json={"action": "partners"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["title"] == "Profils recommandés"
    assert result["sections"][0]["items"]


def test_private_group_resources_are_hidden_from_list_dashboard_and_favorites(client):
    owner = register(client, "private-resource-owner@example.edu")
    group = client.post(
        "/api/groups",
        headers={"X-CSRF-Token": owner["csrf_token"]},
        json={"name": "Projet confidentiel", "visibility": "private", "recruitment_open": False},
    )
    assert group.status_code == 201
    group_id = group.json()["id"]

    resource = client.post(
        "/api/resources/upload",
        headers={"X-CSRF-Token": owner["csrf_token"]},
        data={"title": "Secret privé", "kind": "Document", "group_id": str(group_id)},
        files={"file": ("secret.txt", b"contenu confidentiel", "text/plain")},
    )
    assert resource.status_code == 201
    resource_id = resource.json()["id"]

    outsider = register(client, "private-resource-outsider@example.edu")
    listed = client.get("/api/resources")
    assert listed.status_code == 200
    assert all(item["id"] != resource_id for item in listed.json())

    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    assert all(item["id"] != resource_id for item in dashboard.json()["resources"])

    detail = client.get(f"/api/resources/{resource_id}")
    assert detail.status_code == 404
    download = client.get(f"/api/resources/{resource_id}/download")
    assert download.status_code == 404
