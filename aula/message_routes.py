import asyncio
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from aula import auth, repo, storage
from aula.access import Denied, can_dm, membership, require_writer
from aula.auth_routes import SESSION_COOKIE, _require_csrf, current_auth
from aula.config import CORS_ORIGINS
from aula.db import many, one, session
from aula.hub import hub
from aula.serialize import pack_messages
from aula.task_routes import _date_value
from aula.util import ALLOWED_EMOJI, dm_pair, dumps, mentioned_ids, now

router = APIRouter(tags=["chat et fichiers de groupe"])


def _student(context):
    if context["user"]["role"] != "student":
        raise HTTPException(403, "Cette action est réservée aux étudiants.")
    return context["user"]


def _member(conn, group_id, user):
    try:
        return require_writer(conn, group_id, user)
    except Denied as exc:
        raise HTTPException(exc.status, exc.message) from None


def _load_message(conn, message_id, user):
    message = repo.get_message(conn, message_id)
    if not message or message.get("group_id") is None:
        raise HTTPException(404, "Message introuvable.")
    group, member = _member(conn, message["group_id"], user)
    return message, group, member


def _safe_file(file_row):
    return {
        "id": file_row["id"], "name": file_row["original_name"], "mime": file_row["mime"],
        "size": file_row["size"], "created_at": file_row["created_at"],
        "uploader_id": file_row["uploader_id"], "uploader_name": file_row.get("uploader_name"),
        "url": f"/api/group-files/{file_row['id']}",
    }


def _publish_group(group_id, event):
    with session() as conn:
        recipients = repo.member_ids(conn, group_id)
    hub.publish(recipients, {**event, "group_id": group_id})


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(default="", max_length=4000)
    reply_to: int | None = Field(default=None, gt=0)
    file_id: int | None = Field(default=None, gt=0)

    @field_validator("body")
    @classmethod
    def trim_body(cls, value):
        return value.strip()


class MessageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=4000)

    @field_validator("body")
    @classmethod
    def trim_body(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Le message ne peut pas être vide.")
        return value


class ReactionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    emoji: str


class ReadPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    last_message_id: int = Field(default=0, ge=0)


class ConvertTaskPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=140)
    description: str = Field(default="", max_length=4000)
    priority: str = "normal"
    due_at: str | None = Field(default=None, max_length=40)
    assignee_ids: list[int] = Field(default_factory=list, max_length=40)

    @field_validator("title", "description")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if value is not None else None


@router.get("/api/groups/{group_id}/messages")
def list_group_messages(
    group_id: int,
    before: int | None = Query(default=None, gt=0),
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=40, ge=1, le=100),
    context: dict = Depends(current_auth),
):
    user = _student(context)
    with session() as conn:
        _member(conn, group_id, user)
        rows, has_more = repo.list_messages(conn, group_id=group_id, before=before, query=q, limit=limit)
        cursor = repo.last_read(conn, user["id"], f"g:{group_id}")
        messages = pack_messages(conn, rows, user["id"])
        return {
            "messages": messages,
            "has_more": has_more,
            "next_before": messages[0]["id"] if messages else None,
            "last_read_id": cursor,
            "unread": repo.scope_unread(conn, user["id"], f"g:{group_id}", group_id=group_id),
        }


@router.post("/api/groups/{group_id}/messages", status_code=201)
def send_group_message(group_id: int, payload: MessageCreate, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    if not payload.body and not payload.file_id:
        raise HTTPException(422, "Écrivez un message ou joignez un fichier.")
    with session() as conn:
        _member(conn, group_id, user)
        if payload.reply_to:
            parent = repo.get_message(conn, payload.reply_to)
            if not parent or parent.get("group_id") != group_id:
                raise HTTPException(404, "Message de réponse introuvable dans ce groupe.")
        if payload.file_id:
            file_row = repo.get_file(conn, payload.file_id)
            if not file_row or file_row.get("group_id") != group_id:
                raise HTTPException(404, "Fichier introuvable dans ce groupe.")
        message_id = repo.create_message(
            conn, user_id=user["id"], body=payload.body, group_id=group_id,
            reply_to=payload.reply_to, file_id=payload.file_id,
        )
        row = repo.get_message(conn, message_id)
        packed = pack_messages(conn, [row], user["id"])[0]
        members = repo.members_of(conn, group_id)
        mentions = set(mentioned_ids(payload.body, members))
        reply = repo.get_message(conn, payload.reply_to) if payload.reply_to else None
        for member in members:
            recipient_id = member["id"]
            if recipient_id == user["id"]:
                continue
            if recipient_id in mentions:
                kind, title = "mention", "Vous avez été mentionné dans une discussion"
            elif reply and reply["user_id"] == recipient_id:
                kind, title = "reply", "Un membre a répondu à votre message"
            else:
                kind, title = "message", "Nouveau message dans votre groupe"
            repo.notify(
                conn, user_id=recipient_id, actor_id=user["id"], kind=kind, title=title,
                body=f"{user['name']} · {(payload.body or 'A partagé un fichier')[:240]}",
                href=f"/app/groupes/{group_id}?onglet=discussion",
                dedupe_key=f"group-message:{message_id}:{recipient_id}",
            )
    _publish_group(group_id, {"type": "message_created", "message": packed})
    return packed


@router.put("/api/messages/{message_id}")
def edit_group_message(message_id: int, payload: MessageUpdate, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        message, group, member = _load_message(conn, message_id, user)
        if message["deleted_at"]:
            raise HTTPException(409, "Un message supprimé ne peut pas être modifié.")
        if message["user_id"] != user["id"]:
            raise HTTPException(403, "Vous ne pouvez modifier que vos propres messages.")
        repo.update_message_body(conn, message_id, payload.body)
        packed = pack_messages(conn, [repo.get_message(conn, message_id)], user["id"])[0]
    _publish_group(group["id"], {"type": "message_updated", "message": packed})
    return packed


@router.delete("/api/messages/{message_id}")
def delete_group_message(message_id: int, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        message, group, member = _load_message(conn, message_id, user)
        if message["deleted_at"]:
            return {"deleted": True, "id": message_id}
        if message["user_id"] != user["id"] and member["role"] not in {"owner", "admin"}:
            raise HTTPException(403, "Vous ne pouvez supprimer que vos propres messages.")
        repo.soft_delete_message(conn, message_id)
        packed = pack_messages(conn, [repo.get_message(conn, message_id)], user["id"])[0]
    _publish_group(group["id"], {"type": "message_deleted", "message": packed})
    return {"deleted": True, "id": message_id}


@router.post("/api/messages/{message_id}/reactions")
def toggle_message_reaction(message_id: int, payload: ReactionPayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    if payload.emoji not in ALLOWED_EMOJI:
        raise HTTPException(422, "Réaction non prise en charge.")
    with session() as conn:
        message, group, _ = _load_message(conn, message_id, user)
        if message["deleted_at"]:
            raise HTTPException(409, "Un message supprimé ne peut pas recevoir de réaction.")
        added = repo.toggle_reaction(conn, message_id, user["id"], payload.emoji)
        packed = pack_messages(conn, [repo.get_message(conn, message_id)], user["id"])[0]
    _publish_group(group["id"], {"type": "message_reaction", "message": packed})
    return {"added": added, "message": packed}


@router.post("/api/groups/{group_id}/messages/read")
def mark_group_messages_read(group_id: int, payload: ReadPayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        _member(conn, group_id, user)
        latest = one(conn, "SELECT COALESCE(MAX(id), 0) AS id FROM messages WHERE group_id = ?", (group_id,))["id"]
        if payload.last_message_id > latest:
            raise HTTPException(422, "Le curseur de lecture dépasse les messages du groupe.")
        repo.mark_read(conn, user["id"], f"g:{group_id}", payload.last_message_id)
        unread = repo.scope_unread(conn, user["id"], f"g:{group_id}", group_id=group_id)
    _publish_group(group_id, {"type": "messages_read", "user_id": user["id"], "last_message_id": payload.last_message_id})
    return {"last_read_id": payload.last_message_id, "unread": unread}


def _file_kind(mime: str) -> str:
    if mime.startswith("image/"):
        return "image"
    if mime == "application/zip":
        return "archive"
    return "document"


@router.get("/api/groups/{group_id}/files")
def list_group_files(group_id: int, q: str = Query(default="", max_length=160), kind: str | None = None, context: dict = Depends(current_auth)):
    user = _student(context)
    if kind not in (None, "image", "document", "archive"):
        raise HTTPException(422, "Type de fichier invalide.")
    with session() as conn:
        _member(conn, group_id, user)
        rows = repo.group_files(conn, group_id)
        if q.strip():
            needle = q.strip().casefold()
            rows = [row for row in rows if needle in row["original_name"].casefold() or needle in row["uploader_name"].casefold()]
        if kind:
            rows = [row for row in rows if _file_kind(row["mime"]) == kind]
        return [_safe_file(row) | {"kind": _file_kind(row["mime"])} for row in rows[:100]]


@router.post("/api/groups/{group_id}/files", status_code=201)
def upload_group_file(group_id: int, request: Request, file: UploadFile = File(...), context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    try:
        with session() as conn:
            _member(conn, group_id, user)
            row = storage.save_upload(conn, file, user["id"], group_id)
            row["uploader_name"] = user["name"]
            result = _safe_file(row) | {"kind": _file_kind(row["mime"])}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    finally:
        file.file.close()
    _publish_group(group_id, {"type": "file_uploaded", "file": result})
    return result


@router.get("/api/group-files/{file_id}")
def download_group_file(file_id: int, context: dict = Depends(current_auth)):
    user = _student(context)
    with session() as conn:
        row = repo.get_file(conn, file_id)
        if not row or not row.get("group_id"):
            raise HTTPException(404, "Fichier introuvable.")
        try:
            _member(conn, row["group_id"], user)
        except HTTPException:
            raise HTTPException(404, "Fichier introuvable.") from None
        path = storage.safe_stored_path(row["stored_name"])
    if not path.is_file():
        raise HTTPException(404, "Fichier introuvable.")
    return FileResponse(
        path, media_type="application/octet-stream", filename=Path(row["original_name"]).name,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/api/group-files/{file_id}")
def delete_group_file(file_id: int, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        row = repo.get_file(conn, file_id)
        if not row or not row.get("group_id"):
            raise HTTPException(404, "Fichier introuvable.")
        try:
            group, member = _member(conn, row["group_id"], user)
        except HTTPException:
            raise HTTPException(404, "Fichier introuvable.") from None
        if row["uploader_id"] != user["id"] and member["role"] not in {"owner", "admin"}:
            raise HTTPException(403, "Seul l’auteur du fichier ou un responsable peut le supprimer.")
        path = storage.safe_stored_path(row["stored_name"])
        conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
    path.unlink(missing_ok=True)
    _publish_group(group["id"], {"type": "file_deleted", "file_id": file_id})
    return {"deleted": True, "id": file_id}


@router.post("/api/messages/{message_id}/convert-to-task", status_code=201)
def convert_message_to_task(message_id: int, payload: ConvertTaskPayload, request: Request, context: dict = Depends(current_auth)):
    from aula import task_routes

    user = _student(context)
    _require_csrf(request, context)
    if payload.priority not in {"low", "normal", "high", "urgent"}:
        raise HTTPException(422, "Priorité invalide.")
    try:
        due_at = _date_value(payload.due_at, end_of_day=True)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    with session() as conn:
        conn.execute("BEGIN IMMEDIATE")
        message, group, _ = _load_message(conn, message_id, user)
        if message["deleted_at"] or not message["body"].strip():
            raise HTTPException(422, "Ce message ne contient pas de texte convertible.")
        existing = repo.task_by_message(conn, message_id)
        if existing:
            raise HTTPException(409, detail={"message": "Ce message a déjà été converti en tâche.", "task_id": existing["id"]})
        title = (payload.title or message["body"].splitlines()[0]).strip()[:140]
        if len(title) < 2:
            raise HTTPException(422, "Le titre doit contenir au moins deux caractères.")
        assignees = list(dict.fromkeys(payload.assignee_ids))
        if any(not membership(conn, group["id"], assignee_id) for assignee_id in assignees):
            raise HTTPException(422, "Chaque responsable doit être membre du groupe.")
        description = payload.description.strip() or message["body"].strip()
        task_id = repo.create_task(
            conn, group_id=group["id"], title=title, description=description, status="todo", priority=payload.priority,
            due_at=due_at, created_by=user["id"], source_message_id=message_id,
        )
        repo.set_assignees(conn, task_id, assignees)
        repo.add_task_history(conn, task_id, user["id"], "created", f"Tâche créée depuis le message #{message_id}")
        task = repo.get_task(conn, task_id)
        task["group_name"] = group["name"]
        result = task_routes._task_view(conn, task, detailed=True)
    _publish_group(group["id"], {"type": "task_created_from_message", "message_id": message_id, "task_id": task_id})
    return result


@router.get("/api/dm/conversations")
def list_dm_conversations(context: dict = Depends(current_auth)):
    user = _student(context)
    with session() as conn:
        return repo.conversations(conn, user["id"])


@router.get("/api/dm/{other_id}/messages")
def list_dm_messages(
    other_id: int,
    before: int | None = Query(default=None, gt=0),
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=40, ge=1, le=100),
    context: dict = Depends(current_auth),
):
    user = _student(context)
    with session() as conn:
        if not can_dm(conn, user["id"], other_id):
            raise HTTPException(403, "Cette conversation n'est pas autorisée.")
        low, high = dm_pair(user["id"], other_id)
        rows, has_more = repo.list_messages(
            conn, dm_low=low, dm_high=high, before=before, query=q, limit=limit,
        )
        scope = f"d:{low}:{high}"
        return {
            "messages": pack_messages(conn, rows, user["id"]),
            "has_more": has_more,
            "next_before": rows[0]["id"] if rows else None,
            "last_read_id": repo.last_read(conn, user["id"], scope),
            "unread": repo.scope_unread(conn, user["id"], scope, dm_low=low, dm_high=high),
        }


@router.post("/api/dm/{other_id}/messages", status_code=201)
def send_dm_message(other_id: int, payload: MessageCreate, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    if not payload.body:
        raise HTTPException(422, "Écrivez un message.")
    with session() as conn:
        if not can_dm(conn, user["id"], other_id):
            raise HTTPException(403, "Cette conversation n'est pas autorisée.")
        low, high = dm_pair(user["id"], other_id)
        if payload.reply_to:
            parent = repo.get_message(conn, payload.reply_to)
            if not parent or parent.get("dm_low") != low or parent.get("dm_high") != high:
                raise HTTPException(404, "Message de réponse introuvable dans cette conversation.")
        message_id = repo.create_message(
            conn, user_id=user["id"], body=payload.body,
            dm_low=low, dm_high=high, reply_to=payload.reply_to,
        )
        row = repo.get_message(conn, message_id)
        packed = pack_messages(conn, [row], user["id"])[0]
        repo.notify(
            conn, user_id=other_id, actor_id=user["id"], kind="dm",
            title="Nouveau message privé",
            body=f"{user['name']} · {payload.body[:240]}",
            href=f"/app/messages/d/{user['id']}",
        )
    hub.publish([other_id], {"type": "dm_created", "message": packed, "with_user_id": user["id"]})
    return packed


@router.post("/api/dm/{other_id}/read")
def mark_dm_read(other_id: int, payload: ReadPayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        if not can_dm(conn, user["id"], other_id):
            raise HTTPException(403, "Cette conversation n'est pas autorisée.")
        low, high = dm_pair(user["id"], other_id)
        latest = one(
            conn,
            "SELECT COALESCE(MAX(id), 0) AS id FROM messages WHERE dm_low=? AND dm_high=?",
            (low, high),
        )["id"]
        if payload.last_message_id > latest:
            raise HTTPException(422, "Le curseur de lecture dépasse les messages.")
        scope = f"d:{low}:{high}"
        repo.mark_read(conn, user["id"], scope, payload.last_message_id)
        unread = repo.scope_unread(conn, user["id"], scope, dm_low=low, dm_high=high)
    return {"last_read_id": payload.last_message_id, "unread": unread}


@router.put("/api/dm/{other_id}/messages/{message_id}")
def edit_dm_message(other_id: int, message_id: int, payload: MessageUpdate, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        if not can_dm(conn, user["id"], other_id):
            raise HTTPException(403, "Cette conversation n'est pas autorisée.")
        low, high = dm_pair(user["id"], other_id)
        message = repo.get_message(conn, message_id)
        if not message or message.get("dm_low") != low or message.get("dm_high") != high:
            raise HTTPException(404, "Message introuvable.")
        if message["deleted_at"]:
            raise HTTPException(409, "Un message supprimé ne peut pas être modifié.")
        if message["user_id"] != user["id"]:
            raise HTTPException(403, "Vous ne pouvez modifier que vos propres messages.")
        repo.update_message_body(conn, message_id, payload.body)
        packed = pack_messages(conn, [repo.get_message(conn, message_id)], user["id"])[0]
    hub.publish([other_id], {"type": "dm_updated", "message": packed, "with_user_id": user["id"]})
    return packed


@router.delete("/api/dm/{other_id}/messages/{message_id}")
def delete_dm_message(other_id: int, message_id: int, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        if not can_dm(conn, user["id"], other_id):
            raise HTTPException(403, "Cette conversation n'est pas autorisée.")
        low, high = dm_pair(user["id"], other_id)
        message = repo.get_message(conn, message_id)
        if not message or message.get("dm_low") != low or message.get("dm_high") != high:
            raise HTTPException(404, "Message introuvable.")
        if message["user_id"] != user["id"]:
            raise HTTPException(403, "Vous ne pouvez supprimer que vos propres messages.")
        repo.soft_delete_message(conn, message_id)
        packed = pack_messages(conn, [repo.get_message(conn, message_id)], user["id"])[0]
    hub.publish([other_id], {"type": "dm_deleted", "message": packed, "with_user_id": user["id"]})
    return {"deleted": True, "id": message_id}


def _origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    if not origin:
        return False
    parsed = urlsplit(origin)
    expected_scheme = "https" if websocket.url.scheme == "wss" else "http"
    expected = f"{expected_scheme}://{websocket.url.netloc}".rstrip("/")
    normalized = origin.rstrip("/")
    return normalized == expected or normalized in CORS_ORIGINS


@router.websocket("/ws/groups/{group_id}")
async def group_websocket(websocket: WebSocket, group_id: int):
    if not _origin_allowed(websocket):
        await websocket.close(code=1008)
        return
    token = websocket.cookies.get(SESSION_COOKIE)
    with session() as conn:
        user = auth.resolve_session(conn, token)
        if not user or user["role"] != "student":
            await websocket.close(code=1008)
            return
        try:
            _, member = require_writer(conn, group_id, user)
        except Denied:
            await websocket.close(code=1008)
            return
        group_members = repo.member_ids(conn, group_id)
    await websocket.accept()
    queue = await hub.register(user["id"])
    online = set(hub.snapshot())
    await websocket.send_json({"type": "presence_snapshot", "group_id": group_id, "user_ids": [item for item in group_members if item in online]})
    hub.publish(group_members, {"type": "presence", "group_id": group_id, "user_id": user["id"], "online": True})
    try:
        while True:
            receive_task = asyncio.create_task(websocket.receive_text())
            event_task = asyncio.create_task(queue.get())
            done, pending = await asyncio.wait((receive_task, event_task), timeout=25, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            if not done:
                with session() as conn:
                    fresh = auth.resolve_session(conn, token)
                    if not fresh:
                        await websocket.close(code=1008)
                        break
                    try:
                        require_writer(conn, group_id, fresh)
                    except Denied:
                        await websocket.close(code=1008)
                        break
                await websocket.send_json({"type": "heartbeat"})
                continue
            if receive_task in done:
                incoming = receive_task.result()
                if incoming == "ping":
                    await websocket.send_text("pong")
            if event_task in done:
                event = event_task.result()
                if event.get("type") == "force_disconnect":
                    affected_group = event.get("group_id")
                    if affected_group is None or affected_group == group_id:
                        await websocket.close(code=1008)
                        break
                with session() as conn:
                    fresh = auth.resolve_session(conn, token)
                    if not fresh:
                        await websocket.close(code=1008)
                        break
                    try:
                        require_writer(conn, group_id, fresh)
                    except Denied:
                        await websocket.close(code=1008)
                        break
                if event.get("group_id") == group_id:
                    await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        hub.unregister(user["id"], queue)
        still_online = user["id"] in hub.snapshot()
        hub.publish(group_members, {"type": "presence", "group_id": group_id, "user_id": user["id"], "online": still_online})
