from fastapi.testclient import TestClient

from aula import db
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
    deleted = client.delete(
        f"/api/help/requests/{request_id}",
        headers={"X-CSRF-Token": asker_csrf},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get("/api/help/requests").json() == []

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


def test_help_requests_target_multiple_levels_and_contact_all_group_members(client):
    asker_csrf = register(client, "help-multi-asker@example.edu", "Étudiante demandeuse")
    group = client.post(
        "/api/groups",
        headers={"X-CSRF-Token": asker_csrf},
        json={"name": "Projet multi-niveaux"},
    )
    assert group.status_code == 201
    group_id = group.json()["id"]

    with TestClient(app) as groupmate:
        groupmate_csrf = register(groupmate, "help-multi-groupmate@example.edu", "Membre du groupe")
        set_level(groupmate, groupmate_csrf, "M1")
        with db.session() as conn:
            groupmate_id = db.one(
                conn, "SELECT id FROM users WHERE email=?", ("help-multi-groupmate@example.edu",)
            )["id"]
            conn.execute(
                "INSERT INTO group_members(group_id, user_id, role, joined_at) VALUES (?, ?, 'member', ?)",
                (group_id, groupmate_id, "2026-01-01T00:00:00"),
            )

        with TestClient(app) as l2_student, TestClient(app) as m1_student, TestClient(app) as other_student:
            l2_csrf = register(l2_student, "help-multi-l2@example.edu", "Étudiant L2")
            m1_csrf = register(m1_student, "help-multi-m1@example.edu", "Étudiante M1")
            other_csrf = register(other_student, "help-multi-other@example.edu", "Étudiant L3")
            set_level(l2_student, l2_csrf, "L2")
            set_level(m1_student, m1_csrf, "M1")
            set_level(other_student, other_csrf, "L3")

            created = client.post(
                "/api/help/requests",
                headers={"X-CSRF-Token": asker_csrf},
                json={
                    "group_id": group_id,
                    "target_levels": ["L2", "M1"],
                    "title": "Besoin d’aide sur les données",
                    "description": "Nous avons besoin d’un avis sur notre analyse.",
                },
            )
            assert created.status_code == 201, created.text
            request_id = created.json()["id"]
            assert created.json()["target_levels"] == ["L2", "M1"]
            assert created.json()["notified_count"] == 3
            assert any(n["kind"] == "help_request" for n in l2_student.get("/api/notifications").json()["notifications"])
            assert any(n["kind"] == "help_request" for n in m1_student.get("/api/notifications").json()["notifications"])
            assert any(n["kind"] == "help_request" for n in groupmate.get("/api/notifications").json()["notifications"])
            assert not any(n["kind"] == "help_request" for n in other_student.get("/api/notifications").json()["notifications"])

            for student in (l2_student, m1_student):
                visible = student.get("/api/help/requests").json()
                assert visible[0]["id"] == request_id
                assert visible[0]["can_respond"] is True
            assert other_student.get("/api/help/requests").json() == []
            assert groupmate.get("/api/help/requests").json()[0]["can_respond"] is True

            response = l2_student.post(
                f"/api/help/requests/{request_id}/responses",
                headers={"X-CSRF-Token": l2_csrf},
                json={"body": "Bonjour, je peux vous accompagner pour analyser les résultats."},
            )
            assert response.status_code == 201, response.text
            group_notifications = groupmate.get("/api/notifications").json()["notifications"]
            assert any(item["kind"] == "help_response" for item in group_notifications)
            assert any(
                item["kind"] == "help_response"
                for item in client.get("/api/notifications").json()["notifications"]
            )

            no_levels = client.post(
                "/api/help/requests",
                headers={"X-CSRF-Token": asker_csrf},
                json={
                    "group_id": group_id,
                    "target_levels": [],
                    "title": "Demande sans niveau",
                    "description": "Cette demande ne précise aucun niveau.",
                },
            )
            assert no_levels.status_code == 422