from starlette.websockets import WebSocketDisconnect
from aula import auth, db


PASSWORD = "motdepasse-tres-solide-2026"


def register(client, email, name):
    response = client.post("/api/auth/register", json={"email": email, "name": name, "password": PASSWORD})
    assert response.status_code == 201
    return {"user": response.json()["user"], "csrf": response.json()["csrf_token"], "cookie": client.cookies.get("campusia_session")}


def create_group(client, csrf, name="Discussion équipe"):
    response = client.post("/api/groups", json={"name": name, "visibility": "public"}, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 201
    return response.json()


def switch_user(client, identity):
    client.cookies.set("campusia_session", identity["cookie"])


def test_group_messages_permissions_reactions_reads_and_task_conversion(client):
    owner = register(client, "chat-owner@example.edu", "Responsable")
    group = create_group(client, owner["csrf"])
    member = register(client, "chat-member@example.edu", "Équipière")
    switch_user(client, member)
    assert client.post(f"/api/groups/{group['id']}/join", headers={"X-CSRF-Token": member["csrf"]}).status_code == 200
    sent = client.post(f"/api/groups/{group['id']}/messages", json={"body": "Préparer la présentation"}, headers={"X-CSRF-Token": member["csrf"]})
    assert sent.status_code == 201, sent.text
    message = sent.json()
    assert message["body"] == "Préparer la présentation"
    switch_user(client, owner)
    group_list = client.get("/api/groups").json()
    assert next(item for item in group_list if item["id"] == group["id"])["unread_count"] == 1
    assert client.get("/api/dashboard").json()["notifications"][0]["kind"] == "message"
    switch_user(client, member)
    edited = client.put(f"/api/messages/{message['id']}", json={"body": "Préparer la présentation finale"}, headers={"X-CSRF-Token": member["csrf"]})
    assert edited.status_code == 200 and edited.json()["edited"]
    reacted = client.post(f"/api/messages/{message['id']}/reactions", json={"emoji": "✅"}, headers={"X-CSRF-Token": member["csrf"]})
    assert reacted.status_code == 200
    assert reacted.json()["message"]["reactions"][0]["mine"] is True
    read = client.post(f"/api/groups/{group['id']}/messages/read", json={"last_message_id": message["id"]}, headers={"X-CSRF-Token": member["csrf"]})
    assert read.status_code == 200 and read.json()["unread"] == 0
    converted = client.post(f"/api/messages/{message['id']}/convert-to-task", json={"priority": "high", "assignee_ids": [member["user"]["id"]]}, headers={"X-CSRF-Token": member["csrf"]})
    assert converted.status_code == 201, converted.text
    assert converted.json()["source_message_id"] == message["id"]
    duplicate = client.post(f"/api/messages/{message['id']}/convert-to-task", json={}, headers={"X-CSRF-Token": member["csrf"]})
    assert duplicate.status_code == 409
    assert client.get(f"/api/groups/{group['id']}/messages?q=finale").json()["messages"][0]["id"] == message["id"]


def test_group_files_are_validated_private_and_scoped(client):
    owner = register(client, "file-owner@example.edu", "Propriétaire")
    group = create_group(client, owner["csrf"], "Fichiers privés")
    uploaded = client.post(
        f"/api/groups/{group['id']}/files", files={"file": ("brief.pdf", b"%PDF-1.4\ncontenu", "application/pdf")},
        headers={"X-CSRF-Token": owner["csrf"]},
    )
    assert uploaded.status_code == 201, uploaded.text
    item = uploaded.json()
    assert "stored" not in str(item).lower()
    assert client.get(item["url"]).status_code == 200
    bad = client.post(f"/api/groups/{group['id']}/files", files={"file": ("fake.pdf", b"<html>nope</html>", "application/pdf")}, headers={"X-CSRF-Token": owner["csrf"]})
    assert bad.status_code == 422
    large = client.post(f"/api/groups/{group['id']}/files", files={"file": ("large.txt", b"x" * (8 * 1024 * 1024 + 1), "text/plain")}, headers={"X-CSRF-Token": owner["csrf"]})
    assert large.status_code == 422
    outsider = register(client, "file-outsider@example.edu", "Externe")
    denied = client.get(f"/api/groups/{group['id']}/files")
    assert denied.status_code == 403
    assert client.get(item["url"]).status_code == 404
    assert client.delete(item["url"], headers={"X-CSRF-Token": outsider["csrf"]}).status_code == 404


def test_chat_csrf_reply_scope_and_websocket_membership(client):
    owner = register(client, "ws-owner@example.edu", "Créateur")
    group = create_group(client, owner["csrf"], "Canal temps réel")
    denied = client.post(f"/api/groups/{group['id']}/messages", json={"body": "sans csrf"})
    assert denied.status_code == 403
    outsider = register(client, "ws-outsider@example.edu", "Visiteur")
    switch_user(client, owner)
    with client.websocket_connect(f"/ws/groups/{group['id']}", headers={"Origin": "http://testserver"}) as socket:
        first = socket.receive_json()
        assert first["type"] == "presence_snapshot"
        assert owner["user"]["id"] in first["user_ids"]
        sent = client.post(f"/api/groups/{group['id']}/messages", json={"body": "Événement temps réel"}, headers={"X-CSRF-Token": owner["csrf"]})
        assert sent.status_code == 201
        event = socket.receive_json()
        while event["type"] == "presence":
            event = socket.receive_json()
        assert event["type"] == "message_created" and event["message"]["body"] == "Événement temps réel"
    try:
        with client.websocket_connect(f"/ws/groups/{group['id']}", headers={"Origin": "http://testserver"}):
            pass
    except WebSocketDisconnect:
        pass
    switch_user(client, outsider)
    assert client.get(f"/api/groups/{group['id']}/messages").status_code == 403


def test_message_reaches_another_member_websocket_session_without_polling(client):
    owner = register(client, "live-owner@example.edu", "Responsable live")
    group = create_group(client, owner["csrf"], "Temps réel multi-session")
    member = register(client, "live-member@example.edu", "Membre live")
    switch_user(client, member)
    assert client.post(f"/api/groups/{group['id']}/join", headers={"X-CSRF-Token": member["csrf"]}).status_code == 200
    switch_user(client, owner)
    origin = {"Origin": "http://testserver"}
    with client.websocket_connect(f"/ws/groups/{group['id']}", headers=origin) as owner_socket:
        assert owner_socket.receive_json()["type"] == "presence_snapshot"
        member_headers = {**origin, "Cookie": f"campusia_session={member['cookie']}"}
        with client.websocket_connect(f"/ws/groups/{group['id']}", headers=member_headers) as member_socket:
            assert member_socket.receive_json()["type"] == "presence_snapshot"
            response = client.post(
                f"/api/groups/{group['id']}/messages",
                json={"body": "Message visible en temps réel"},
                headers={"X-CSRF-Token": owner["csrf"]},
            )
            assert response.status_code == 201
            owner_events = [owner_socket.receive_json() for _ in range(3)]
            member_events = [member_socket.receive_json() for _ in range(2)]
            assert any(event.get("type") == "message_created" and event["message"]["body"] == "Message visible en temps réel" for event in owner_events), owner_events
            assert any(event.get("type") == "message_created" and event["message"]["body"] == "Message visible en temps réel" for event in member_events), member_events


def test_message_edit_and_delete_are_author_or_moderator_only(client):
    owner = register(client, "moderate-owner@example.edu", "Modérateur")
    group = create_group(client, owner["csrf"], "Modération")
    message = client.post(f"/api/groups/{group['id']}/messages", json={"body": "Message initial"}, headers={"X-CSRF-Token": owner["csrf"]}).json()
    member = register(client, "moderate-member@example.edu", "Membre")
    client.post(f"/api/groups/{group['id']}/join", headers={"X-CSRF-Token": member["csrf"]})
    assert client.put(f"/api/messages/{message['id']}", json={"body": "édition étrangère"}, headers={"X-CSRF-Token": member["csrf"]}).status_code == 403
    assert client.delete(f"/api/messages/{message['id']}", headers={"X-CSRF-Token": member["csrf"]}).status_code == 403
    switch_user(client, owner)
    deleted = client.delete(f"/api/messages/{message['id']}", headers={"X-CSRF-Token": owner["csrf"]})
    assert deleted.status_code == 200 and deleted.json()["deleted"]
    stored = client.get(f"/api/groups/{group['id']}/messages").json()["messages"]
    assert stored[0]["deleted"] is True


def test_suspension_closes_existing_group_websocket(client):
    member = register(client, "suspended-socket-member@example.edu", "Membre suspendu")
    owner = register(client, "suspended-socket-owner@example.edu", "Propriétaire")
    switch_user(client, owner)
    group = create_group(client, owner["csrf"], "Groupe suspendu")
    switch_user(client, member)
    assert client.post(
        f"/api/groups/{group['id']}/join",
        headers={"X-CSRF-Token": member["csrf"]},
    ).status_code == 200

    member_cookie = member["cookie"]
    client.cookies.clear()
    with db.session() as conn:
        admin = auth.create_user(
            conn,
            email="socket-admin@example.edu",
            password=PASSWORD,
            name="Administrateur socket",
            role="admin",
            verified=1,
        )
    login = client.post("/api/auth/login", json={
        "email": "socket-admin@example.edu",
        "password": PASSWORD,
    })
    assert login.status_code == 200
    admin_csrf = login.json()["csrf_token"]
    admin_cookie = client.cookies.get("campusia_session")

    switch_user(client, member)
    origin = {"Origin": "http://testserver"}
    headers = {**origin, "Cookie": f"campusia_session={member_cookie}"}
    with client.websocket_connect(f"/ws/groups/{group['id']}", headers=headers) as socket:
        snapshot = socket.receive_json()
        assert snapshot["type"] == "presence_snapshot"

        switch_user(client, {"cookie": admin_cookie, "csrf": admin_csrf})
        suspended = client.post(
            f"/api/admin/users/{member['user']['id']}/suspension",
            headers={"X-CSRF-Token": admin_csrf},
            json={"suspended": True},
        )
        assert suspended.status_code == 200

        try:
            while True:
                event = socket.receive_json()
                if event["type"] not in {"presence", "heartbeat"}:
                    raise AssertionError(
                        f"The suspended user's WebSocket remained open: {event}"
                    )
        except WebSocketDisconnect as exc:
            assert exc.code == 1008
