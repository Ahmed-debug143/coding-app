from fastapi.testclient import TestClient

from main import app


def register(client, email, name):
    response = client.post("/api/auth/register", json={
        "email": email, "name": name, "password": "motdepasse-tres-solide-2026"
    })
    assert response.status_code == 201
    return client.get("/api/auth/me").json()["csrf_token"]


def payload(**changes):
    data = {
        "name": "Équipe environnement", "description": "Projet étudiant", "filiere": "Informatique",
        "subject": "Écologie", "project_name": "Campus vert", "objective": "Mesurer les déchets",
        "max_members": 4, "skills_wanted": ["Python", "Analyse"], "visibility": "public",
        "preferred_level": "L3", "deadline": "2027-05-01", "recruitment_open": True,
    }
    data.update(changes)
    return data


def test_group_creation_discovery_and_details(client):
    csrf = register(client, "group-owner@example.edu", "Créatrice")
    response = client.post("/api/groups", json=payload(), headers={"X-CSRF-Token": csrf})
    assert response.status_code == 201, response.text
    group = response.json()
    assert group["member_count"] == 1
    assert group["member_role"] == "owner"
    assert group["skills_wanted"] == ["Python", "Analyse"]
    assert group["recruitment_open"] is True
    assert client.get("/api/groups?subject=Écologie&level=L3&skill=Python").json()[0]["id"] == group["id"]
    assert client.get(f"/api/groups/{group['id']}").status_code == 200


def test_group_can_be_created_with_only_its_name(client):
    csrf = register(client, "simple-group@example.edu", "Étudiant")
    response = client.post(
        "/api/groups",
        json={"name": "Groupe de révision"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "Groupe de révision"
    assert response.json()["max_members"] == 8


def test_group_join_access_duplicate_and_leave(client):
    owner_csrf = register(client, "owner2@example.edu", "Propriétaire")
    group = client.post("/api/groups", json=payload(), headers={"X-CSRF-Token": owner_csrf}).json()
    with TestClient(app) as member:
        csrf = register(member, "member2@example.edu", "Membre")
        joined = member.post(f"/api/groups/{group['id']}/join", headers={"X-CSRF-Token": csrf})
        assert joined.status_code == 200
        assert joined.json()["member_role"] == "member"
        assert member.post(f"/api/groups/{group['id']}/join", headers={"X-CSRF-Token": csrf}).status_code == 409
        assert member.delete(f"/api/groups/{group['id']}/membership", headers={"X-CSRF-Token": csrf}).status_code == 200
        assert member.delete(f"/api/groups/{group['id']}/membership", headers={"X-CSRF-Token": csrf}).status_code == 404


def test_private_group_and_manager_permissions(client):
    owner_csrf = register(client, "owner3@example.edu", "Propriétaire")
    group = client.post("/api/groups", json=payload(visibility="private"), headers={"X-CSRF-Token": owner_csrf}).json()
    with TestClient(app) as outsider:
        csrf = register(outsider, "outsider@example.edu", "Externe")
        assert outsider.get(f"/api/groups/{group['id']}").status_code == 404
        assert outsider.post(f"/api/groups/{group['id']}/join", headers={"X-CSRF-Token": csrf}).status_code == 404
        assert outsider.put(f"/api/groups/{group['id']}", json=payload(name="Piraté"), headers={"X-CSRF-Token": csrf}).status_code == 404


def test_join_request_acceptance_role_control_and_capacity(client):
    owner_csrf = register(client, "owner4@example.edu", "Propriétaire")
    group = client.post("/api/groups", json=payload(max_members=2), headers={"X-CSRF-Token": owner_csrf}).json()
    with TestClient(app) as requester:
        csrf = register(requester, "requester@example.edu", "Demandeur")
        request = requester.post(f"/api/groups/{group['id']}/requests", json={"message": "Je peux contribuer."}, headers={"X-CSRF-Token": csrf})
        assert request.status_code == 200
        assert requester.post(f"/api/groups/{group['id']}/requests", json={}, headers={"X-CSRF-Token": csrf}).status_code == 409
        request_id = request.json()["id"]
        assert requester.post(f"/api/groups/{group['id']}/requests/{request_id}/respond?accept=true", headers={"X-CSRF-Token": csrf}).status_code == 403
        response = client.post(f"/api/groups/{group['id']}/requests/{request_id}/respond?accept=true", headers={"X-CSRF-Token": owner_csrf})
        assert response.status_code == 200
        assert requester.get(f"/api/groups/{group['id']}").json()["joined"] is True
        assert client.put(f"/api/groups/{group['id']}/members/{requester.get('/api/auth/me').json()['user']['id']}/role", json={"role": "owner"}, headers={"X-CSRF-Token": owner_csrf}).status_code == 422
        assert client.put(f"/api/groups/{group['id']}/members/{requester.get('/api/auth/me').json()['user']['id']}/role", json={"role": "admin"}, headers={"X-CSRF-Token": owner_csrf}).status_code == 200


def test_group_mutations_require_csrf_and_closed_recruitment(client):
    csrf = register(client, "owner5@example.edu", "Créateur")
    group = client.post("/api/groups", json=payload(recruitment_open=False), headers={"X-CSRF-Token": csrf}).json()
    with TestClient(app) as outsider:
        member_csrf = register(outsider, "closed@example.edu", "Étudiant")
        assert outsider.post(f"/api/groups/{group['id']}/join", headers={"X-CSRF-Token": member_csrf}).status_code == 409
    assert client.put(f"/api/groups/{group['id']}", json=payload(), headers={}).status_code == 403


def test_owner_transfer_enables_owner_departure_and_admins_manage_settings(client):
    owner_csrf = register(client, "owner-transfer@example.edu", "Créateur")
    group = client.post("/api/groups", json=payload(), headers={"X-CSRF-Token": owner_csrf}).json()
    with TestClient(app) as member:
        member_csrf = register(member, "member-transfer@example.edu", "Futur propriétaire")
        member_id = member.get("/api/auth/me").json()["user"]["id"]
        member.post(f"/api/groups/{group['id']}/join", headers={"X-CSRF-Token": member_csrf})
        assert client.delete(f"/api/groups/{group['id']}/membership", headers={"X-CSRF-Token": owner_csrf}).status_code == 409
        transfer = client.post(f"/api/groups/{group['id']}/owner", json={"user_id": member_id}, headers={"X-CSRF-Token": owner_csrf})
        assert transfer.status_code == 200
        assert client.delete(f"/api/groups/{group['id']}/membership", headers={"X-CSRF-Token": owner_csrf}).status_code == 200
        updated = payload(name="Groupe administré")
        assert member.put(f"/api/groups/{group['id']}", json=updated, headers={"X-CSRF-Token": member_csrf}).status_code == 200
