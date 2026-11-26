from fastapi.testclient import TestClient

from main import app


def register(client, email, name):
    response = client.post("/api/auth/register", json={
        "name": name,
        "email": email,
        "password": "UnePhraseDePasse2026!",
    })
    assert response.status_code == 201
    return response.json()["csrf_token"]


def set_level(client, csrf, level):
    response = client.put(
        "/api/profile/me",
        headers={"X-CSRF-Token": csrf},
        json={"level": level},
    )
    assert response.status_code == 200


def test_help_requests_are_targeted_to_external_students_at_selected_level(client):
    asker_csrf = register(client, "help-asker@example.edu", "Étudiante demandeuse")
    group = client.post(
        "/api/groups",
        headers={"X-CSRF-Token": asker_csrf},
        json={"name": "Projet campus"},
    )
    assert group.status_code == 201
    with TestClient(app) as responder:
        responder_csrf = register(responder, "help-responder@example.edu", "Étudiant L2")
        set_level(responder, responder_csrf, "L2")
        created = client.post(
            "/api/help/requests",
            headers={"X-CSRF-Token": asker_csrf},
            json={
                "group_id": group.json()["id"],
                "target_level": "L2",
                "title": "Blocage sur notre enquête",
                "description": "Nous ne savons pas comment organiser les résultats recueillis.",
            },
        )
        assert created.status_code == 201, created.text
        request_id = created.json()["id"]
        assert created.json()["notified_count"] == 1
        notifications = responder.get("/api/notifications").json()["notifications"]
        assert any(item["kind"] == "help_request" for item in notifications)
        visible = responder.get("/api/help/requests").json()
        assert [item["id"] for item in visible] == [request_id]
        assert visible[0]["can_respond"] is True
        response = responder.post(
            f"/api/help/requests/{request_id}/responses",
            headers={"X-CSRF-Token": responder_csrf},
            json={"body": "Essayez de classer les réponses par thème avant de les comparer."},
        )
        assert response.status_code == 201, response.text

    asker_notifications = client.get("/api/notifications").json()["notifications"]
    assert any(item["kind"] == "help_response" for item in asker_notifications)
    asker_view = client.get("/api/help/requests").json()[0]
    assert asker_view["responses"][0]["author_name"] == "Étudiant L2"

    with TestClient(app) as unrelated:
        unrelated_csrf = register(unrelated, "help-unrelated@example.edu", "Étudiant L3")
        set_level(unrelated, unrelated_csrf, "L3")
        assert unrelated.get("/api/help/requests").json() == []
        denied = unrelated.post(
            f"/api/help/requests/{request_id}/responses",
            headers={"X-CSRF-Token": unrelated_csrf},
            json={"body": "Je veux répondre même si le niveau ne correspond pas."},
        )
        assert denied.status_code == 404