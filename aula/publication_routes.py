from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from aula.auth_routes import _require_csrf, current_auth
from aula.db import many, one, session
from aula.util import ALLOWED_EMOJI, now

router = APIRouter(prefix="/api/publications", tags=["vie étudiante"])


class PublicationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=3, max_length=4000)
    link_url: str | None = Field(default=None, max_length=500)

    @field_validator("body")
    @classmethod
    def clean_body(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("La publication doit contenir au moins trois caractères.")
        return value

    @field_validator("link_url")
    @classmethod
    def clean_link(cls, value):
        if not value:
            return None
        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Le lien doit commencer par http:// ou https://.")
        return value.strip()


class CommentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=2000)
    parent_id: int | None = Field(default=None, gt=0)

    @field_validator("body")
    @classmethod
    def clean_body(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Le commentaire ne peut pas être vide.")
        return value


class ReactionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    emoji: str


class ReportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=8, max_length=1000)


def _student(context):
    if context["user"]["role"] != "student":
        raise HTTPException(403, "Cette action est réservée aux étudiants.")
    return context["user"]


def _publication_view(conn, row, viewer_id):
    if not row:
        return None
    data = dict(row)
    data["mine"] = row["author_id"] == viewer_id
    data["reactions"] = many(
        conn,
        """SELECT emoji, COUNT(*) AS count,
                  MAX(CASE WHEN user_id=? THEN 1 ELSE 0 END) AS mine
           FROM publication_reactions WHERE publication_id=?
           GROUP BY emoji ORDER BY count DESC""",
        (viewer_id, row["id"]),
    )
    data["comments"] = many(
        conn,
        """SELECT c.*, u.name AS author_name
           FROM publication_comments c JOIN users u ON u.id=c.author_id
           WHERE c.publication_id=? AND c.deleted_at IS NULL
           ORDER BY c.created_at, c.id""",
        (row["id"],),
    )
    return data


@router.get("")
def list_publications(context: dict = Depends(current_auth)):
    user = _student(context)
    with session() as conn:
        rows = many(
            conn,
            """SELECT p.*, u.name AS author_name, u.avatar_file
               FROM publications p JOIN users u ON u.id=p.author_id
               WHERE p.status='published' AND p.deleted_at IS NULL
               ORDER BY p.created_at DESC, p.id DESC LIMIT 80""",
        )
        return [_publication_view(conn, row, user["id"]) for row in rows]


@router.post("", status_code=201)
def create_publication(payload: PublicationPayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        cur = conn.execute(
            """INSERT INTO publications(author_id, body, link_url, status, created_at)
               VALUES (?, ?, ?, 'published', ?)""",
            (user["id"], payload.body, payload.link_url, now()),
        )
        row = one(
            conn,
            """SELECT p.*, u.name AS author_name, u.avatar_file
               FROM publications p JOIN users u ON u.id=p.author_id WHERE p.id=?""",
            (cur.lastrowid,),
        )
        return _publication_view(conn, row, user["id"])


@router.put("/{publication_id}")
def update_publication(publication_id: int, payload: PublicationPayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        row = one(conn, "SELECT * FROM publications WHERE id=?", (publication_id,))
        if not row or row["deleted_at"]:
            raise HTTPException(404, "Publication introuvable.")
        if row["author_id"] != user["id"]:
            raise HTTPException(403, "Vous ne pouvez modifier que vos propres publications.")
        conn.execute(
            "UPDATE publications SET body=?, link_url=?, edited_at=? WHERE id=?",
            (payload.body, payload.link_url, now(), publication_id),
        )
        return _publication_view(
            conn,
            one(conn, "SELECT p.*, u.name AS author_name, u.avatar_file FROM publications p JOIN users u ON u.id=p.author_id WHERE p.id=?", (publication_id,),),
            user["id"],
        )


@router.delete("/{publication_id}")
def delete_publication(publication_id: int, request: Request, context: dict = Depends(current_auth)):
    user = context["user"]
    _require_csrf(request, context)
    if user["role"] not in {"student", "admin"}:
        raise HTTPException(403, "Compte non autorisé.")
    with session() as conn:
        row = one(conn, "SELECT * FROM publications WHERE id=?", (publication_id,))
        if not row:
            raise HTTPException(404, "Publication introuvable.")
        if row["author_id"] != user["id"] and user["role"] != "admin":
            raise HTTPException(403, "Vous ne pouvez supprimer que vos publications.")
        conn.execute("UPDATE publications SET deleted_at=? WHERE id=?", (now(), publication_id))
    return {"deleted": True, "id": publication_id}


@router.post("/{publication_id}/comments", status_code=201)
def add_comment(publication_id: int, payload: CommentPayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        publication = one(conn, "SELECT id FROM publications WHERE id=? AND deleted_at IS NULL", (publication_id,))
        if not publication:
            raise HTTPException(404, "Publication introuvable.")
        if payload.parent_id:
            parent = one(
                conn,
                "SELECT id FROM publication_comments WHERE id=? AND publication_id=? AND deleted_at IS NULL",
                (payload.parent_id, publication_id),
            )
            if not parent:
                raise HTTPException(404, "Commentaire parent introuvable.")
        cur = conn.execute(
            "INSERT INTO publication_comments(publication_id, author_id, body, parent_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (publication_id, user["id"], payload.body, payload.parent_id, now()),
        )
        return {"id": cur.lastrowid, "publication_id": publication_id, "body": payload.body}


@router.post("/{publication_id}/reactions")
def toggle_reaction(publication_id: int, payload: ReactionPayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    if payload.emoji not in ALLOWED_EMOJI:
        raise HTTPException(422, "Réaction non prise en charge.")
    with session() as conn:
        publication = one(conn, "SELECT id FROM publications WHERE id=? AND deleted_at IS NULL", (publication_id,))
        if not publication:
            raise HTTPException(404, "Publication introuvable.")
        existing = one(
            conn,
            "SELECT 1 AS ok FROM publication_reactions WHERE publication_id=? AND user_id=? AND emoji=?",
            (publication_id, user["id"], payload.emoji),
        )
        if existing:
            conn.execute(
                "DELETE FROM publication_reactions WHERE publication_id=? AND user_id=? AND emoji=?",
                (publication_id, user["id"], payload.emoji),
            )
            return {"added": False}
        conn.execute(
            "INSERT INTO publication_reactions(publication_id, user_id, emoji) VALUES (?, ?, ?)",
            (publication_id, user["id"], payload.emoji),
        )
        return {"added": True}


@router.post("/{publication_id}/report", status_code=201)
def report_publication(publication_id: int, payload: ReportPayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        publication = one(conn, "SELECT id FROM publications WHERE id=? AND deleted_at IS NULL", (publication_id,))
        if not publication:
            raise HTTPException(404, "Publication introuvable.")
        conn.execute(
            "INSERT INTO publication_reports(reporter_id, publication_id, reason, created_at) VALUES (?, ?, ?, ?)",
            (user["id"], publication_id, payload.reason, now()),
        )
        conn.execute(
            "UPDATE publications SET status='reported' WHERE id=?",
            (publication_id,),
        )
    return {"reported": True}
