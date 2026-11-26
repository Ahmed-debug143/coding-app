from pathlib import Path

from fastapi.testclient import TestClient

from aula import db, repo
from aula.auth_routes import SESSION_COOKIE
from main import app


def create_student(client, email="profile@example.edu", name="Étudiant Test"):
    response = client.post(
        "/api/auth/register",
        json={"name": name, "email": email, "password": "UnePhraseDePasse2026!"},
    )
    assert response.status_code == 201
    return response.json()


def csrf(client):
    return client.get("/api/auth/me").json()["csrf_token"]


def test_profile_routes_require_authentication(client):
    assert client.get("/api/profile/me").status_code == 401
    assert client.put("/api/profile/me", json={"bio": "Privé"}).status_code == 401
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/profiles/1").status_code == 401


def test_new_profile_is_real_and_incomplete_fields_are_optional(client):
    create_student(client)
    response = client.get("/api/profile/me")
    assert response.status_code == 200
    profile = response.json()
    assert profile["name"] == "Étudiant Test"
    assert profile["skills"] == []
    assert profile["project_types"] == []
    assert profile["collaboration_preferences"] == []
    assert profile["completion"]["percent"] == 8
    assert "Établissement" in profile["completion"]["missing"]


def test_profile_update_persists_and_normalizes_lists(client):
    create_student(client)
    response = client.put(
        "/api/profile/me",
        headers={"X-CSRF-Token": csrf(client)},
        json={
            "name": "  Amina Étudiante  ",
            "school": "Université Exemple",
            "faculty": "Sciences",
            "filiere": "Informatique",
            "level": "L3",
            "bio": "J'aime les projets utiles.",
            "skills": ["Python", " Python ", "Design"],
            "interests": ["IA", "Environnement"],
            "focus_goal": "Créer un projet de recherche.",
            "project_types": ["Recherche", "Hackathon"],
            "availability": "Soirs en semaine",
            "collaboration_preferences": ["hybrid", "structured"],
        },
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Amina Étudiante"
    assert response.json()["skills"] == ["Python", "Design"]
    assert response.json()["collaboration_preferences"] == ["hybrid", "structured"]
    assert response.json()["completion"]["percent"] > 8

    refreshed = client.get("/api/profile/me").json()
    assert refreshed["school"] == "Université Exemple"
    assert refreshed["project_types"] == ["Recherche", "Hackathon"]
    assert refreshed["focus_goal"] == "Créer un projet de recherche."


def test_profile_update_requires_csrf_and_rejects_invalid_or_unowned_fields(client):
    create_student(client)
    no_csrf = client.put("/api/profile/me", json={"bio": "Essai"})
    invalid_value = client.put(
        "/api/profile/me",
        headers={"X-CSRF-Token": csrf(client)},
        json={"name": " ", "skills": ["x" * 41], "collaboration_preferences": ["superuser"]},
    )
    forged_id = client.put(
        "/api/profile/me",
        headers={"X-CSRF-Token": csrf(client)},
        json={"user_id": 999, "name": "Autre compte"},
    )
    null_update = client.put(
        "/api/profile/me",
        headers={"X-CSRF-Token": csrf(client)},
        json={"bio": None},
    )
    assert no_csrf.status_code == 403
    assert invalid_value.status_code == 422
    assert forged_id.status_code == 422
    assert null_update.status_code == 422


def test_public_profile_is_whitelisted_and_account_data_isolated(client):
    own = create_student(client, email="first@example.edu", name="Premier Étudiant")
    first_cookie = client.cookies.get(SESSION_COOKIE)
    with TestClient(app) as second_client:
        second = create_student(second_client, email="second@example.edu", name="Deuxième Étudiant")
        second_cookie = second_client.cookies.get(SESSION_COOKIE)
        second_user_id = second["user"]["id"]
        assert second_client.get("/api/profile/me").json()["name"] == "Deuxième Étudiant"
    with TestClient(app) as first_client:
        first_client.cookies.set(SESSION_COOKIE, first_cookie)
        public_profile = first_client.get(f"/api/profiles/{second_user_id}")
        own_profile = first_client.get("/api/profile/me").json()
        attempted_update = first_client.put(
            "/api/profile/me",
            headers={"X-CSRF-Token": csrf(first_client)},
            json={"name": "Nouveau nom du premier"},
        )

    assert own["user"]["id"] != second_user_id
    assert public_profile.status_code == 200
    assert public_profile.json()["name"] == "Deuxième Étudiant"
    assert "email" not in public_profile.json()
    assert "availability" not in public_profile.json()
    assert own_profile["name"] == "Premier Étudiant"
    assert attempted_update.status_code == 200
    assert attempted_update.json()["name"] == "Nouveau nom du premier"
    with TestClient(app) as second_client:
        second_client.cookies.set(SESSION_COOKIE, second_cookie)
        assert second_client.get("/api/profile/me").json()["name"] == "Deuxième Étudiant"


def test_dashboard_uses_only_real_user_data(client):
    account = create_student(client)
    with db.session() as conn:
        user = repo.user_by_id(conn, account["user"]["id"])
        group = repo.create_group(conn, user, {"name": "Projet réel", "project_name": "Analyse campus"})
        task_id = repo.create_task(
            conn,
            group_id=group["id"],
            title="Préparer le questionnaire",
            description="",
            status="todo",
            priority="normal",
            due_at="2099-05-20T12:00:00",
            created_by=user["id"],
        )
        repo.set_assignees(conn, task_id, [user["id"]])

    response = client.get("/api/dashboard")
    assert response.status_code == 200
    dashboard = response.json()
    assert [row["name"] for row in dashboard["groups"]] == ["Projet réel"]
    assert [row["title"] for row in dashboard["all_tasks"]] == ["Préparer le questionnaire"]
    assert dashboard["deadlines"][0]["title"] == "Préparer le questionnaire"
    assert dashboard["user"]["email"] == "profile@example.edu"
    assert "connections" not in dashboard
    assert "invitations" not in dashboard


def test_avatar_upload_validates_type_and_stores_photo_for_owner(client):
    create_student(client)
    bad = client.post(
        "/api/profile/me/avatar",
        headers={"X-CSRF-Token": csrf(client)},
        files={"file": ("avatar.txt", b"not an image", "text/plain")},
    )
    assert bad.status_code == 422

    uploaded = client.post(
        "/api/profile/me/avatar",
        headers={"X-CSRF-Token": csrf(client)},
        files={"file": ("avatar.png", b"\x89PNG\r\n\x1a\nsmall-test-image", "image/png")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["avatar_url"]
    image = client.get(uploaded.json()["avatar_url"])
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"


def test_profile_migration_adds_columns_without_losing_legacy_user(tmp_path, isolated_data_dir, monkeypatch):
    from aula import auth

    legacy_migrations = tmp_path / "migrations-legacy"
    legacy_migrations.mkdir()
    migration_source = Path(db.MIGRATIONS) / "001_init.sql"
    (legacy_migrations / "001_init.sql").write_text(migration_source.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(db, "MIGRATIONS", legacy_migrations)
    db.init_db()
    with db.session() as conn:
        user_cursor = conn.execute(
            "INSERT INTO users(email, password_hash, name, created_at) VALUES (?, ?, ?, ?)",
            ("legacy@example.edu", "scrypt$legacy", "Ancien compte", "2026-01-01T00:00:00"),
        )
        group_cursor = conn.execute(
            "INSERT INTO groupes(name, owner_id, created_at) VALUES (?, ?, ?)",
            ("Ancien groupe", user_cursor.lastrowid, "2026-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO tasks(group_id, title, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (group_cursor.lastrowid, "Ancienne tâche", user_cursor.lastrowid, "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )

    monkeypatch.setattr(db, "MIGRATIONS", Path(__file__).resolve().parents[1] / "aula" / "migrations")
    db.init_db()
    with db.session() as conn:
        legacy = db.one(conn, "SELECT email, name, faculty, project_types, collab_prefs FROM users WHERE email = ?", ("legacy@example.edu",))
        applied = db.many(conn, "SELECT version FROM schema_migrations ORDER BY version")
    assert legacy == {"email": "legacy@example.edu", "name": "Ancien compte", "faculty": "", "project_types": "[]", "collab_prefs": "[]"}
    assert [row["version"] for row in applied] == [
        "001_init.sql", "002_help.sql", "002_student_profile.sql", "003_collaboration_discovery.sql",
        "004_task_management.sql", "005_publications.sql", "006_admin_audit.sql", "007_calendar_reminders.sql",
        "008_help_multiple_levels.sql"
    ]
    with db.session() as conn:
        columns = {row["name"] for row in db.many(conn, "PRAGMA table_info(groupes)")}
    assert {"preferred_level", "recruitment_open"} <= columns
    with db.session() as conn:
        task_columns = {row["name"] for row in db.many(conn, "PRAGMA table_info(tasks)")}
        preserved_task = db.one(conn, "SELECT title, starts_at, estimate_hours FROM tasks")
        history_table = db.one(conn, "SELECT name FROM sqlite_master WHERE type='table' AND name='task_history'")
    assert {"starts_at", "estimate_hours"} <= task_columns
    assert preserved_task == {"title": "Ancienne tâche", "starts_at": None, "estimate_hours": None}
    assert history_table == {"name": "task_history"}
