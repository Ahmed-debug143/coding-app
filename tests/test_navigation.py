def test_group_deep_link_is_protected_and_serves_the_app_shell(client):
    anonymous = client.get("/app/groupes/42?onglet=discussion", follow_redirects=False)
    assert anonymous.status_code == 303
    assert anonymous.headers["location"] == "/?next=%2Fapp%2Fgroupes%2F42%3Fonglet%3Ddiscussion"

    account = client.post(
        "/api/auth/register",
        json={"email": "deep-link@example.edu", "name": "Étudiante", "password": "motdepasse-tres-solide-2026"},
    )
    assert account.status_code == 201
    page = client.get("/app/groupes/42?onglet=discussion")
    assert page.status_code == 200
    assert 'id="groupDetail"' in page.text

