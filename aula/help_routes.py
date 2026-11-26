from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aula import repo
from aula.auth_routes import _require_csrf, current_auth
from aula.db import many, one, session
from aula.util import now

router = APIRouter(prefix="/api/help/requests", tags=["aide entre étudiants"])
HELP_LEVELS = ("L1", "L2", "L3", "M1", "M2", "Doctorat", "Autre")


class HelpRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group_id: int = Field(gt=0)
    target_levels: list[Literal["L1", "L2", "L3", "M1", "M2", "Doctorat", "Autre"]] = Field(
        default_factory=list, max_length=len(HELP_LEVELS),
    )
    target_level: Literal["L1", "L2", "L3", "M1", "M2", "Doctorat", "Autre"] | None = None
    title: str = Field(min_length=4, max_length=120)
    description: str = Field(min_length=10, max_length=2000)

    @field_validator("target_levels")
    @classmethod
    def unique_levels(cls, value):
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def require_target_levels(self):
        if not self.target_levels and self.target_level:
            self.target_levels = [self.target_level]
        if not self.target_levels:
            raise ValueError("Choisissez au moins un niveau.")
        return self

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        value = value.strip()
        if len(value) < 4:
            raise ValueError("Le titre doit contenir au moins quatre caractères.")
        return value

    @field_validator("description")
    @classmethod
    def clean_description(cls, value):
        value = value.strip()
        if len(value) < 10:
            raise ValueError("La description doit contenir au moins dix caractères.")
        return value


class HelpResponsePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=2, max_length=2000)

    @field_validator("body")
    @classmethod
    def clean_body(cls, value):
        value = value.strip()
        if len(value) < 2:
            raise ValueError("La réponse ne peut pas être vide.")
        return value


def _student(context):
    if context["user"]["role"] != "student":
        raise HTTPException(403, "Cette action est réservée aux étudiants.")
    return context["user"]


def _request_row(conn, request_id):
    return one(
        conn,
        """SELECT h.*, g.name AS group_name, u.name AS author_name
           FROM help_requests h
           JOIN groupes g ON g.id=h.group_id
           JOIN users u ON u.id=h.author_id
           WHERE h.id=?""",
        (request_id,),
    )


def _request_levels(conn, item):
    rows = many(
        conn,
        """SELECT level FROM help_request_levels WHERE request_id=?
           ORDER BY CASE level
             WHEN 'L1' THEN 1 WHEN 'L2' THEN 2 WHEN 'L3' THEN 3
             WHEN 'M1' THEN 4 WHEN 'M2' THEN 5 WHEN 'Doctorat' THEN 6 ELSE 7
           END""",
        (item["id"],),
    )
    return [row["level"] for row in rows] or [item["target_level"]]


def _is_group_member(conn, group_id, user_id):
    return bool(one(
        conn,
        "SELECT 1 AS yes FROM group_members WHERE group_id=? AND user_id=?",
        (group_id, user_id),
    ))


def _require_visible(conn, item, user):
    member = _is_group_member(conn, item["group_id"], user["id"])
    eligible = user.get("level", "") in _request_levels(conn, item)
    if item["author_id"] != user["id"] and not member and not (eligible and item["status"] == "open"):
        raise HTTPException(404, "Demande d’aide introuvable.")
    return member, eligible


def _request_view(conn, item, user):
    member, eligible = _require_visible(conn, item, user)
    target_levels = _request_levels(conn, item)
    responses = many(
        conn,
        """SELECT r.id, r.author_id, r.body, r.created_at, u.name AS author_name
           FROM help_responses r JOIN users u ON u.id=r.author_id
           WHERE r.request_id=? ORDER BY r.created_at, r.id""",
        (item["id"],),
    )
    return {
        "id": item["id"],
        "group_id": item["group_id"],
        "group_name": item["group_name"],
        "author_id": item["author_id"],
        "author_name": item["author_name"],
        "mine": item["author_id"] == user["id"],
        "target_level": item["target_level"],
        "target_levels": target_levels,
        "title": item["title"],
        "description": item["description"],
        "status": item["status"],
        "created_at": item["created_at"],
        "can_respond": eligible and item["status"] == "open" and item["author_id"] != user["id"],
        "responses": [{**response, "mine": response["author_id"] == user["id"]} for response in responses],
    }


@router.get("")
def list_help_requests(context: dict = Depends(current_auth)):
    user = _student(context)
    with session() as conn:
        rows = many(
            conn,
            """SELECT h.*, g.name AS group_name, u.name AS author_name
               FROM help_requests h
               JOIN groupes g ON g.id=h.group_id
               JOIN users u ON u.id=h.author_id
               WHERE h.author_id=?
                  OR EXISTS (SELECT 1 FROM group_members gm WHERE gm.group_id=h.group_id AND gm.user_id=?)
                  OR (h.status='open' AND EXISTS (
                       SELECT 1 FROM help_request_levels hrl
                       WHERE hrl.request_id=h.id AND hrl.level=?
                     )
                      AND NOT EXISTS (SELECT 1 FROM group_members gm WHERE gm.group_id=h.group_id AND gm.user_id=?))
               ORDER BY h.created_at DESC, h.id DESC LIMIT 80""",
            (user["id"], user["id"], user.get("level", ""), user["id"]),
        )
        return [_request_view(conn, row, user) for row in rows]


@router.post("", status_code=201)
def create_help_request(payload: HelpRequestPayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        if not _is_group_member(conn, payload.group_id, user["id"]):
            raise HTTPException(404, "Groupe introuvable.")
        cur = conn.execute(
            """INSERT INTO help_requests(group_id, author_id, target_level, title, description, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (payload.group_id, user["id"], payload.target_levels[0], payload.title, payload.description, now()),
        )
        conn.executemany(
            "INSERT INTO help_request_levels(request_id, level) VALUES (?, ?)",
            [(cur.lastrowid, level) for level in payload.target_levels],
        )
        item = _request_row(conn, cur.lastrowid)
        recipients = many(
            conn,
            """SELECT DISTINCT u.id FROM users u
               JOIN help_request_levels hrl ON hrl.level=u.level AND hrl.request_id=?
               WHERE u.role='student' AND u.suspended=0 AND u.id<>?""",
            (cur.lastrowid, user["id"]),
        )
        for recipient in recipients:
            repo.notify(
                conn,
                user_id=recipient["id"],
                kind="help_request",
                title="Un groupe demande de l’aide",
                body=f"{item['group_name']} cherche des étudiants de niveau {' / '.join(payload.target_levels)} : {payload.title}",
                dedupe_key=f"help:{item['id']}:{recipient['id']}",
                actor_id=user["id"],
            )
        result = _request_view(conn, item, user)
        result["notified_count"] = len(recipients)
        return result


@router.post("/{request_id}/responses", status_code=201)
def respond_to_help_request(request_id: int, payload: HelpResponsePayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        item = _request_row(conn, request_id)
        if not item:
            raise HTTPException(404, "Demande d’aide introuvable.")
        _, eligible = _require_visible(conn, item, user)
        if not eligible or item["author_id"] == user["id"]:
            raise HTTPException(403, "Seuls les étudiants extérieurs du niveau demandé peuvent répondre.")
        if item["status"] != "open":
            raise HTTPException(409, "Cette demande est clôturée.")
        cur = conn.execute(
            "INSERT INTO help_responses(request_id, author_id, body, created_at) VALUES (?, ?, ?, ?)",
            (request_id, user["id"], payload.body, now()),
        )
        group_members = many(
            conn,
            "SELECT user_id FROM group_members WHERE group_id=? AND user_id<>?",
            (item["group_id"], user["id"]),
        )
        for member in group_members:
            repo.notify(
                conn,
                user_id=member["user_id"],
                kind="help_response",
                title="Votre demande d’aide a reçu une réponse",
                body=f"{user['name']} propose son aide pour « {item['title']} ».",
                dedupe_key=f"help-response:{cur.lastrowid}:{member['user_id']}",
                actor_id=user["id"],
                href="/app/aide",
            )
        return {"id": cur.lastrowid, "request_id": request_id, "body": payload.body}


@router.post("/{request_id}/close")
def close_help_request(request_id: int, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        item = _request_row(conn, request_id)
        if not item:
            raise HTTPException(404, "Demande d’aide introuvable.")
        if item["author_id"] != user["id"]:
            raise HTTPException(403, "Seul l’auteur peut clôturer cette demande.")
        conn.execute(
            "UPDATE help_requests SET status='closed', closed_at=? WHERE id=? AND status='open'",
            (now(), request_id),
        )
        return {"closed": True, "id": request_id}


@router.delete("/{request_id}")
def delete_help_request(request_id: int, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        item = _request_row(conn, request_id)
        if not item:
            raise HTTPException(404, "Demande d’aide introuvable.")
        if item["author_id"] != user["id"]:
            raise HTTPException(403, "Seul l’auteur peut supprimer cette demande.")
        responses = many(conn, "SELECT id FROM help_responses WHERE request_id=?", (request_id,))
        if item["status"] == "open" and not responses:
            raise HTTPException(409, "La demande ne peut être supprimée qu’après une réponse ou sa clôture.")
        conn.execute("DELETE FROM notifications WHERE dedupe_key LIKE ?", (f"help:{request_id}:%",))
        for response in responses:
            conn.execute(
                "DELETE FROM notifications WHERE dedupe_key=? OR dedupe_key LIKE ?",
                (f"help-response:{response['id']}", f"help-response:{response['id']}:%"),
            )
        conn.execute("DELETE FROM help_requests WHERE id=?", (request_id,))
        return {"deleted": True, "id": request_id}