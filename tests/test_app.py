from pathlib import Path


def test_existing_home_and_static_assets(client):
    home = client.get("/")
    assert home.status_code == 200
    assert 'lang="fr"' in home.text
    assert '<title>MED_ETUD — Tableau de bord</title>' in home.text
    assert 'MED_ETUD' in home.text
    assert 'Campusia' not in home.text
    assert 'id="welcomeScreen"' in home.text
    assert 'id="enterApplication"' in home.text
    assert 'id="welcomeName"' in home.text
    assert '/static/med-etud-students.png' in home.text
    assert 'id="profileForm"' in home.text
    assert 'id="dashboardCompletion"' in home.text
    assert 'id="dashboardCompletionRing"' in home.text
    assert 'class="grid dashboard-grid"' in home.text
    assert 'id="groupCreateForm"' in home.text
    assert 'id="groupSearchForm"' in home.text
    assert 'data-view="assistant"' not in home.text
    assert '<h2>Apprendre à utiliser la plateforme</h2>' in home.text
    assert 'id="siteGuideTabs"' in home.text
    assert 'id="siteGuideContent"' in home.text
    assert 'data-view="settings">⚙ &nbsp; Paramètres' in home.text
    assert 'data-view="profile"' not in home.text
    assert 'id="settingsMenu"' in home.text
    assert 'data-settings-tab="profile"' in home.text
    assert 'data-settings-guide>Apprendre à utiliser la plateforme' in home.text
    assert 'id="profile" class="settings-panel" data-settings-panel="profile"' in home.text
    assert 'data-theme-mode="dark"' in home.text
    assert 'data-theme-accent="violet"' in home.text
    assert 'id="assistantForm"' not in home.text
    assert 'data-view="help">? &nbsp; Aide' in home.text
    assert 'id="helpRequestForm"' in home.text
    assert 'data-view="publications">◈ &nbsp; Publications et vie étudiante' in home.text
    assert 'id="publicationTabs"' in home.text
    assert 'id="publicationBrowsePane"' in home.text
    assert 'id="publicationComposePane"' in home.text
    assert 'id="calendarReminderPreset"' in home.text
    assert 'value="2">2 jours avant' in home.text
    assert 'value="3">3 jours avant' in home.text
    assert 'id="peopleSearchForm"' in home.text
    assert 'data-people-mode="recommendations"' in home.text
    assert "Ahmed Martin" not in home.text
    assert "Data Science appliquée à l’éducation" not in home.text
    assert "68%" not in home.text

    script = client.get("/static/app.js")
    stylesheet = client.get("/static/styles.css")
    theme = client.get("/static/med-etud-theme.css")
    assert script.status_code == 200
    assert stylesheet.status_code == 200
    assert theme.status_code == 200
    image = client.get("/static/med-etud-students.png")
    assert image.status_code == 200


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
