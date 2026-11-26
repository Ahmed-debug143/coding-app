PASSWORD = "motdepasse-tres-solide-2026"


def register(client, email):
    response = client.post("/api/auth/register", json={
        "email": email,
        "name": email.split("@")[0],
        "password": PASSWORD,
    })
    assert response.status_code == 201
    return response.json()


def test_publication_create_comment_reaction_report_and_delete(client):
    account = register(client, "publication@example.edu")
    created = client.post(
        "/api/publications",
        headers={"X-CSRF-Token": account["csrf_token"]},
        json={"body": "Une opportunité de projet utile aux étudiants", "link_url": "https://example.edu/projet"},
    )
    assert created.status_code == 201
    publication = created.json()

    feed = client.get("/api/publications")
    assert feed.status_code == 200
    assert any(item["id"] == publication["id"] for item in feed.json())

    comment = client.post(
        f"/api/publications/{publication['id']}/comments",
        headers={"X-CSRF-Token": account["csrf_token"]},
        json={"body": "Je suis intéressé"},
    )
    assert comment.status_code == 201

    reaction = client.post(
        f"/api/publications/{publication['id']}/reactions",
        headers={"X-CSRF-Token": account["csrf_token"]},
        json={"emoji": "👍"},
    )
    assert reaction.status_code == 200
    assert reaction.json()["added"] is True

    report = client.post(
        f"/api/publications/{publication['id']}/report",
        headers={"X-CSRF-Token": account["csrf_token"]},
        json={"reason": "Cette publication semble trompeuse."},
    )
    assert report.status_code == 201

    deleted = client.delete(
        f"/api/publications/{publication['id']}",
        headers={"X-CSRF-Token": account["csrf_token"]},
    )
    assert deleted.status_code == 200
