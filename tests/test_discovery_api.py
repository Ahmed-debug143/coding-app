from fastapi.testclient import TestClient

from main import app


def register(client, email, name):
    response = client.post("/api/auth/register", json={"email": email, "name": name, "password": "motdepasse-tres-solide-2026"})
    assert response.status_code == 201, response.text
    return client.get("/api/auth/me").json()


def update_profile(client, csrf, **fields):
    response = client.put("/api/profile/me", json=fields, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200, response.text
    return response.json()


def test_student_search_filters_privacy_and_discoverability(client):
    me = register(client, "discover-me@example.edu", "Moi")
    with TestClient(app) as other:
        them = register(other, "private@email.example", "Coéquipière")
        update_profile(other, them["csrf_token"], school="Université A", faculty="Sciences", filiere="Informatique", level="L3", bio="Aime créer", skills=["Python", "Design"], interests=["Environnement"], project_types=["Recherche"], focus_goal="Créer un outil durable")
        result = client.get("/api/students?school=Université%20A&skill=python&interest=Environnement&project_type=Recherche")
        assert result.status_code == 200
        assert len(result.json()) == 1
        card = result.json()[0]
        assert card["name"] == "Coéquipière"
        assert "focus_goal" in card
        assert "email" not in card and "availability" not in card
        assert "password_hash" not in card and "discoverable" not in card
        update_profile(other, them["csrf_token"], discoverable=False)
        assert client.get("/api/students?q=Coéquipière").json() == []
        assert client.get("/api/students/recommendations").json() == []


def test_recommendations_explain_criteria_without_probability(client):
    me = register(client, "rec-me@example.edu", "Alice")
    update_profile(client, me["csrf_token"], filiere="Informatique", school="Campus A", level="L3", skills=["Python"], interests=["Climat"], project_types=["Recherche"], focus_goal="Analyser les données climatiques", collaboration_preferences=["hybrid"])
    with TestClient(app) as other:
        them = register(other, "rec-other@example.edu", "Benoît")
        update_profile(other, them["csrf_token"], filiere="Informatique", school="Campus A", level="M1", skills=["Analyse de données"], interests=["Climat"], project_types=["Recherche"], focus_goal="Analyser les données du climat", collaboration_preferences=["hybrid"])
    recommendations = client.get("/api/students/recommendations")
    assert recommendations.status_code == 200
    assert len(recommendations.json()) == 1
    match = recommendations.json()[0]
    assert match["name"] == "Benoît"
    assert match["recommendation"]["reasons"]
    assert "score" not in match["recommendation"]
    assert "probabilité" not in match["recommendation"]["explanation"].lower()


def test_connection_request_response_deduplication_and_private_data(client):
    me = register(client, "connect-me@example.edu", "Demandeur")
    with TestClient(app) as other:
        them = register(other, "connect-other@example.edu", "Destinataire")
        response = client.post("/api/connections", json={"user_id": them["user"]["id"]}, headers={"X-CSRF-Token": me["csrf_token"]})
        assert response.status_code == 201
        assert response.json()["status"] == "pending"
        duplicate = client.post("/api/connections", json={"user_id": them["user"]["id"]}, headers={"X-CSRF-Token": me["csrf_token"]})
        assert duplicate.status_code == 409
        assert other.get("/api/connections").json()["received"][0]["name"] == "Demandeur"
        assert "email" not in other.get("/api/connections").json()["received"][0]
        peer_id = me["user"]["id"]
        accepted = other.post(f"/api/connections/{peer_id}/respond?accept=true", headers={"X-CSRF-Token": them["csrf_token"]})
        assert accepted.status_code == 200
        assert client.get("/api/connections").json()["accepted"][0]["name"] == "Destinataire"


def test_invitations_are_member_manager_only_and_accept_persists(client):
    owner = register(client, "invite-owner@example.edu", "Responsable")
    group = client.post("/api/groups", json={"name": "Invitation équipe", "visibility": "private"}, headers={"X-CSRF-Token": owner["csrf_token"]}).json()
    with TestClient(app) as invitee:
        student = register(invitee, "invitee@example.edu", "Invité")
        response = client.post(f"/api/groups/{group['id']}/invitations", json={"user_id": student["user"]["id"]}, headers={"X-CSRF-Token": owner["csrf_token"]})
        assert response.status_code == 200
        assert client.post(f"/api/groups/{group['id']}/invitations", json={"user_id": student["user"]["id"]}, headers={"X-CSRF-Token": owner["csrf_token"]}).status_code == 409
        invitation = invitee.get("/api/group-invitations").json()
        assert len(invitation) == 1
        accepted = invitee.post(f"/api/group-invitations/{invitation[0]['id']}/respond?accept=true", headers={"X-CSRF-Token": student["csrf_token"]})
        assert accepted.status_code == 200
        detail = invitee.get(f"/api/groups/{group['id']}")
        assert detail.status_code == 200 and detail.json()["joined"] is True
