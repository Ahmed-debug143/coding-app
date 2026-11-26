import pytest

from aula.config import EXPOSE_RESET_LINKS


def test_reset_links_are_disabled_by_default():
    assert EXPOSE_RESET_LINKS is False


def test_cors_is_not_enabled_without_explicit_origins(client):
    from main import app

    assert not any(middleware.cls.__name__ == "CORSMiddleware" for middleware in app.user_middleware)


def test_explicit_cors_origins_are_normalized_and_wildcard_rejected():
    from aula.config import parse_cors_origins

    assert parse_cors_origins(" https://campusia.example/ , http://localhost:3000 ") == [
        "https://campusia.example",
        "http://localhost:3000",
    ]
    with pytest.raises(ValueError, match="origines explicites"):
        parse_cors_origins("*")


def test_reset_base_url_parser_rejects_non_origin_urls():
    from aula.config import parse_reset_base_url

    assert parse_reset_base_url(" https://campusia.example/ ") == "https://campusia.example"
    with pytest.raises(ValueError):
        parse_reset_base_url("https://user:secret@campusia.example")
    with pytest.raises(ValueError):
        parse_reset_base_url("https://campusia.example/reset?step=1")
    with pytest.raises(ValueError):
        parse_reset_base_url("/relative")


def test_password_hash_verification_uses_scrypt():
    from aula.auth import hash_password, verify_password

    stored = hash_password("un-mot-de-passe-solide")
    assert stored.startswith("scrypt$")
    assert verify_password("un-mot-de-passe-solide", stored)
    assert not verify_password("un-autre-mot-de-passe", stored)


def test_partner_matching_returns_explainable_reasons():
    from aula.matching import explain

    score, reasons = explain(
        {"filiere": "Informatique", "school": "Campus A", "level": "L3", "skills": ["Python"], "interests": ["IA"]},
        {"filiere": "Informatique", "school": "Campus A", "level": "L3", "skills": ["Python", "Design"], "interests": ["IA"]},
    )
    assert score > 0
    assert reasons


def test_reset_base_url_is_canonical_and_never_uses_host_header(client, monkeypatch):
    import aula.auth_routes as auth_routes

    monkeypatch.setattr(auth_routes, "RESET_BASE_URL", "https://campusia.example")
    monkeypatch.setattr(auth_routes, "EXPOSE_RESET_LINKS", False)
    sent = {}

    def capture(recipient, link):
        sent["recipient"] = recipient
        sent["link"] = link

    monkeypatch.setattr(auth_routes, "_send_reset_email", capture)
    registered = client.post("/api/auth/register", json={
        "email": "reset-security@example.edu",
        "name": "Sécurité",
        "password": "motdepasse-tres-solide-2026",
    })
    assert registered.status_code == 201

    response = client.post(
        "/api/auth/forgot-password",
        json={"email": "reset-security@example.edu"},
        headers={"Host": "attacker.invalid"},
    )
    assert response.status_code == 200
    assert "reset_link" not in response.json()
    assert sent["recipient"] == "reset-security@example.edu"
    assert sent["link"].startswith("https://campusia.example/?reset=")
    assert "attacker.invalid" not in sent["link"]


def test_reset_links_are_not_generated_when_canonical_base_is_absent(client, monkeypatch):
    import aula.auth_routes as auth_routes

    monkeypatch.setattr(auth_routes, "RESET_BASE_URL", "")
    monkeypatch.setattr(auth_routes, "_send_reset_email", lambda *_args: (_ for _ in ()).throw(AssertionError("SMTP must not be called")))
    client.post("/api/auth/register", json={
        "email": "reset-no-base@example.edu",
        "name": "Sécurité",
        "password": "motdepasse-tres-solide-2026",
    })
    response = client.post(
        "/api/auth/forgot-password",
        json={"email": "reset-no-base@example.edu"},
        headers={"Host": "attacker.invalid"},
    )
    assert response.status_code == 200
    assert response.json() == {"sent": True}
