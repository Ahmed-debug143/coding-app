from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from aula import repo, storage
from aula.access import membership
from aula.auth_routes import _require_csrf, current_auth
from aula.db import one, session

router = APIRouter(prefix="/api", tags=["bibliothèque"])


class ResourcePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=140)
    kind: Literal["Cours", "TD", "TP", "Résumé", "Fiche de révision", "Ancien examen", "Corrigé", "Document", "Lien", "Vidéo", "Tutoriel"]
    description: str = Field(default="", max_length=4000)
    subject: str = Field(default="", max_length=80)
    filiere: str = Field(default="", max_length=80)
    level: str = Field(default="", max_length=40)
    tags: list[str] = Field(default_factory=list, max_length=16)
    link_url: str | None = Field(default=None, max_length=500)
    group_id: int | None = Field(default=None, gt=0)

    @field_validator("title", "description", "subject", "filiere", "level")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if value is not None else None

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, values):
        if any(not item.strip() or len(item.strip()) > 40 for item in values):
            raise ValueError("Chaque mot-clé doit contenir entre 1 et 40 caractères.")
        return list(dict.fromkeys(item.strip() for item in values))

    @field_validator("link_url")
    @classmethod
    def validate_link(cls, value):
        if value is None or not value.strip():
            return None
        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Le lien doit commencer par http:// ou https://.")
        return value.strip()


class ReportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=8, max_length=1000)


class FavoritePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_type: Literal["resource", "group", "message"]
    target_id: int = Field(gt=0)


def _student(context):
    if context["user"]["role"] != "student":
        raise HTTPException(403, "Cette action est réservée aux étudiants.")
    return context["user"]


def _check_group_scope(conn, user, group_id):
    if group_id is not None and not membership(conn, group_id, user["id"]):
        raise HTTPException(403, "La ressource doit être liée à un groupe auquel vous appartenez.")


@router.get("/resources")
def list_resources(
    q: str = "",
    kind: str = "",
    subject: str = "",
    filiere: str = "",
    level: str = "",
    context: dict = Depends(current_auth),
):
    user = _student(context)
    with session() as conn:
        return repo.list_resources(conn, {
            "q": q, "kind": kind, "subject": subject, "filiere": filiere, "level": level,
            "viewer_id": user["id"], "admin": user["role"] == "admin",
        })


@router.post("/resources", status_code=201)
def create_resource(payload: ResourcePayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    if not payload.link_url:
        raise HTTPException(422, "Ajoutez un lien ou téléversez un fichier.")
    with session() as conn:
        _check_group_scope(conn, user, payload.group_id)
        resource_id = repo.create_resource(conn, payload.model_dump() | {"author_id": user["id"]})
        return repo.get_resource(conn, resource_id)


@router.post("/resources/upload", status_code=201)
def upload_resource(
    request: Request,
    title: str = Form(..., min_length=2, max_length=140),
    kind: str = Form(...),
    description: str = Form(default="", max_length=4000),
    subject: str = Form(default="", max_length=80),
    filiere: str = Form(default="", max_length=80),
    level: str = Form(default="", max_length=40),
    tags: str = Form(default=""),
    group_id: int | None = Form(default=None),
    file: UploadFile = File(...),
    context: dict = Depends(current_auth),
):
    user = _student(context)
    _require_csrf(request, context)
    allowed_kinds = {"Cours", "TD", "TP", "Résumé", "Fiche de révision", "Ancien examen", "Corrigé", "Document", "Lien", "Vidéo", "Tutoriel"}
    if kind not in allowed_kinds:
        raise HTTPException(422, "Type de ressource invalide.")
    tag_list = [item.strip() for item in tags.split(",") if item.strip()]
    try:
        with session() as conn:
            _check_group_scope(conn, user, group_id)
            file_row = storage.save_upload(conn, file, user["id"], group_id)
            resource_id = repo.create_resource(conn, {
                "author_id": user["id"], "group_id": group_id, "title": title,
                "kind": kind, "description": description, "subject": subject,
                "filiere": filiere, "level": level, "tags": tag_list,
                "file_id": file_row["id"], "link_url": None,
            })
            resource = repo.get_resource(conn, resource_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    finally:
        file.file.close()
    return resource


@router.get("/resources/{resource_id}")
def get_resource(resource_id: int, context: dict = Depends(current_auth)):
    user = _student(context)
    with session() as conn:
        resource = repo.get_resource(conn, resource_id)
        if not resource or resource["status"] != "published":
            raise HTTPException(404, "Ressource introuvable.")
        if resource["group_id"] and not membership(conn, resource["group_id"], user["id"]):
            raise HTTPException(404, "Ressource introuvable.")
    return resource


@router.get("/resources/{resource_id}/download")
def download_resource(resource_id: int, context: dict = Depends(current_auth)):
    user = _student(context)
    with session() as conn:
        resource = repo.get_resource(conn, resource_id)
        if not resource or resource["status"] != "published" or not resource["file_id"]:
            raise HTTPException(404, "Fichier introuvable.")
        if resource["group_id"] and not membership(conn, resource["group_id"], user["id"]):
            raise HTTPException(404, "Fichier introuvable.")
        file_row = repo.get_file(conn, resource["file_id"])
        if not file_row:
            raise HTTPException(404, "Fichier introuvable.")
        path = storage.safe_stored_path(file_row["stored_name"])
        repo.increment_download(conn, resource_id)
    if not path.is_file():
        raise HTTPException(404, "Fichier introuvable.")
    return FileResponse(path, media_type=file_row["mime"], filename=Path(file_row["original_name"]).name)


@router.post("/resources/{resource_id}/favorite")
def favorite_resource(resource_id: int, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        resource = repo.get_resource(conn, resource_id)
        if not resource or resource["status"] != "published":
            raise HTTPException(404, "Ressource introuvable.")
        if resource["group_id"] and not membership(conn, resource["group_id"], user["id"]):
            raise HTTPException(404, "Ressource introuvable.")
        added = repo.toggle_favorite(conn, user["id"], "resource", resource_id)
    return {"favorited": added}


@router.post("/resources/{resource_id}/report", status_code=201)
def report_resource(resource_id: int, payload: ReportPayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        resource = repo.get_resource(conn, resource_id)
        if not resource:
            raise HTTPException(404, "Ressource introuvable.")
        if resource["group_id"] and not membership(conn, resource["group_id"], user["id"]):
            raise HTTPException(404, "Ressource introuvable.")
        repo.create_report(
            conn, reporter_id=user["id"], target_type="resource",
            target_id=resource_id, reason=payload.reason,
        )
    return {"reported": True}


@router.delete("/resources/{resource_id}")
def delete_resource(resource_id: int, request: Request, context: dict = Depends(current_auth)):
    user = context["user"]
    if user["role"] not in {"student", "admin"}:
        raise HTTPException(403, "Compte non autorisé.")
    _require_csrf(request, context)
    with session() as conn:
        resource = repo.get_resource(conn, resource_id)
        if not resource:
            raise HTTPException(404, "Ressource introuvable.")
        if resource["author_id"] != user["id"] and user["role"] != "admin":
            raise HTTPException(403, "Seul l'auteur ou un administrateur peut supprimer cette ressource.")
        file_row = repo.get_file(conn, resource["file_id"]) if resource["file_id"] else None
        conn.execute("DELETE FROM resources WHERE id = ?", (resource_id,))
        if file_row:
            referenced = one(
                conn,
                "SELECT 1 AS ok FROM resources WHERE file_id = ? LIMIT 1",
                (file_row["id"],),
            )
            if not referenced:
                conn.execute("DELETE FROM files WHERE id = ?", (file_row["id"],))
    if file_row:
        try:
            storage.safe_stored_path(file_row["stored_name"]).unlink(missing_ok=True)
        except ValueError:
            pass
    return {"deleted": True, "id": resource_id}
