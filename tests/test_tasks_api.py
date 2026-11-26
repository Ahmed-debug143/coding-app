from fastapi.testclient import TestClient

from main import app


def register(client, email, name):
    response = client.post("/api/auth/register", json={"email": email, "name": name, "password": "motdepasse-tres-solide-2026"})
    assert response.status_code == 201, response.text
    return client.get("/api/auth/me").json()


def create_group(client, csrf, name="Équipe tâche"):
    response = client.post("/api/groups", json={"name": name, "visibility": "public"}, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 201, response.text
    return response.json()


def create_task(client, csrf, group_id, **changes):
    body = {"title": "Préparer le prototype", "description": "Construire et relire", "priority": "high", "starts_at": "2027-03-01", "due_at": "2027-03-12", "estimate_hours": 6.5}
    body.update(changes)
    return client.post(f"/api/groups/{group_id}/tasks", json=body, headers={"X-CSRF-Token": csrf})


def test_task_routes_require_authentication(client):
    assert client.get("/api/tasks/mine").status_code == 401
    assert client.get("/api/groups/1/tasks").status_code == 401
    assert client.post("/api/groups/1/tasks", json={"title": "Test"}).status_code == 401


def test_task_create_update_assign_status_comment_progress_and_delete(client):
    owner = register(client, "task-owner@example.edu", "Créateur")
    group = create_group(client, owner["csrf_token"])
    with TestClient(app) as member:
        student = register(member, "task-member@example.edu", "Responsable")
        student_id = student["user"]["id"]
        assert member.post(f"/api/groups/{group['id']}/join", headers={"X-CSRF-Token": student["csrf_token"]}).status_code == 200
        created = create_task(client, owner["csrf_token"], group["id"], assignee_ids=[student_id])
        assert created.status_code == 201, created.text
        task = created.json()
        task_id = task["id"]
        assert task["starts_at"] == "2027-03-01T00:00:00"
        assert task["due_at"] == "2027-03-12T23:59:59"
        assert task["assignees"][0]["name"] == "Responsable"
        assert task["history"][0]["action"] == "created"
        edited = client.put(f"/api/tasks/{task_id}", json={"title": "Prototype validé", "due_at": None, "estimate_hours": 8}, headers={"X-CSRF-Token": owner["csrf_token"]})
        assert edited.status_code == 200, edited.text
        assert edited.json()["due_at"] is None and edited.json()["estimate_hours"] == 8
        assigned = client.post(f"/api/tasks/{task_id}/assign", json={"user_ids": []}, headers={"X-CSRF-Token": owner["csrf_token"]})
        assert assigned.status_code == 200 and assigned.json()["assignees"] == []
        assert member.post(f"/api/tasks/{task_id}/status", json={"status": "doing"}, headers={"X-CSRF-Token": student["csrf_token"]}).status_code == 403
        assigned = client.post(f"/api/tasks/{task_id}/assign", json={"user_ids": [student_id, student_id]}, headers={"X-CSRF-Token": owner["csrf_token"]})
        assert assigned.status_code == 200 and len(assigned.json()["assignees"]) == 1
        comment = member.post(f"/api/tasks/{task_id}/comments", json={"body": "Je prends cette partie."}, headers={"X-CSRF-Token": student["csrf_token"]})
        assert comment.status_code == 201
        status = member.post(f"/api/tasks/{task_id}/status", json={"status": "doing"}, headers={"X-CSRF-Token": student["csrf_token"]})
        assert status.status_code == 200 and status.json()["status"] == "doing"
        assert len(status.json()["comments"]) == 1
        listed = client.get(f"/api/groups/{group['id']}/tasks?status=doing&priority=high&q=Prototype")
        assert listed.status_code == 200 and len(listed.json()["tasks"]) == 1
        assert listed.json()["progress"] == {"total": 1, "done": 0, "todo": 0, "doing": 1, "review": 0, "pct": 0}
        mine = member.get("/api/tasks/mine")
        assert [item["id"] for item in mine.json()] == [task_id]
        assert client.delete(f"/api/tasks/{task_id}", headers={"X-CSRF-Token": owner["csrf_token"]}).json() == {"deleted": True, "id": task_id}
        assert client.get(f"/api/tasks/{task_id}").status_code == 404


def test_task_access_and_assignment_cannot_cross_group_or_trust_group_id(client):
    owner = register(client, "task-owner2@example.edu", "Propriétaire")
    group_one = create_group(client, owner["csrf_token"], "Première équipe")
    task = create_task(client, owner["csrf_token"], group_one["id"]).json()
    with TestClient(app) as outsider:
        student = register(outsider, "task-outsider@example.edu", "Externe")
        group_two = create_group(outsider, student["csrf_token"], "Autre équipe")
        outsider.post(f"/api/groups/{group_two['id']}/join", headers={"X-CSRF-Token": student["csrf_token"]})
        assert outsider.get(f"/api/tasks/{task['id']}").status_code == 403
        assert outsider.put(f"/api/tasks/{task['id']}", json={"title": "Accès externe"}, headers={"X-CSRF-Token": student["csrf_token"]}).status_code == 403
        assert outsider.post(f"/api/tasks/{task['id']}/status", json={"status": "done"}, headers={"X-CSRF-Token": student["csrf_token"]}).status_code == 403
        assert client.put(f"/api/tasks/{task['id']}", json={"group_id": group_two["id"]}, headers={"X-CSRF-Token": owner["csrf_token"]}).status_code == 422
        rejected = outsider.post(f"/api/groups/{group_two['id']}/tasks", json={"title": "Mauvaise affectation", "assignee_ids": [owner["user"]["id"]]}, headers={"X-CSRF-Token": student["csrf_token"]})
        assert rejected.status_code == 422


def test_task_create_requires_csrf_and_update_permission(client):
    owner = register(client, "task-owner3@example.edu", "Créateur")
    group = create_group(client, owner["csrf_token"])
    task = create_task(client, owner["csrf_token"], group["id"]).json()
    assert client.put(f"/api/tasks/{task['id']}", json={"title": "Sans jeton"}).status_code == 403
    with TestClient(app) as member:
        student = register(member, "task-member3@example.edu", "Membre")
        member.post(f"/api/groups/{group['id']}/join", headers={"X-CSRF-Token": student["csrf_token"]})
        assert member.put(f"/api/tasks/{task['id']}", json={"title": "Non autorisé"}, headers={"X-CSRF-Token": student["csrf_token"]}).status_code == 403
        assert member.delete(f"/api/tasks/{task['id']}", headers={"X-CSRF-Token": student["csrf_token"]}).status_code == 403


def test_late_task_filters_and_dashboard_use_persisted_data(client):
    owner = register(client, "task-late@example.edu", "Étudiant")
    group = create_group(client, owner["csrf_token"])
    late = create_task(client, owner["csrf_token"], group["id"], title="Échéance dépassée", priority="urgent", due_at="2020-01-02", assignee_ids=[owner["user"]["id"]])
    assert late.status_code == 201
    late_id = late.json()["id"]
    assert late.json()["overdue"] is True
    filtered = client.get(f"/api/groups/{group['id']}/tasks?late=true&priority=urgent&sort=created_desc")
    assert [item["id"] for item in filtered.json()["tasks"]] == [late_id]
    dashboard = client.get("/api/dashboard").json()
    assert [item["id"] for item in dashboard["late"]] == [late_id]
    assert [item["id"] for item in dashboard["urgent_tasks"]] == [late_id]
