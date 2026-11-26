from pathlib import Path


def test_existing_home_and_static_assets(client):
    home = client.get("/")
    assert home.status_code == 200
    assert 'lang="fr"' in home.text
    assert 'id="profileForm"' in home.text
    assert 'id="dashboardCompletion"' in home.text
    assert 'id="groupCreateForm"' in home.text
    assert 'id="groupSearchForm"' in home.text
    assert 'id="peopleSearchForm"' in home.text
    assert 'data-people-mode="recommendations"' in home.text
    assert "Ahmed Martin" not in home.text
    assert "Data Science appliquée à l’éducation" not in home.text
    assert "68%" not in home.text

    script = client.get("/static/app.js")
    stylesheet = client.get("/static/styles.css")
    assert script.status_code == 200
    assert stylesheet.status_code == 200


def test_health_uses_only_the_isolated_database(client, isolated_data_dir):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "users": 0}
    assert (isolated_data_dir / "aula.db").is_file()
    assert (isolated_data_dir / "uploads").is_dir()


def test_static_mount_is_independent_of_current_working_directory():
    from main import app

    static_mount = next(route for route in app.routes if getattr(route, "name", None) == "static")
    assert Path(static_mount.app.directory).is_absolute()


def test_dashboard_resource_guard_matches_removed_resource_section(client):
    script = client.get("/static/app.js")
    assert script.status_code == 200
    assert "const resourcesList = document.querySelector('#resourcesList')" in script.text
    assert "if (resourcesList)" in script.text
