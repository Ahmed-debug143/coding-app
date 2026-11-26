from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aula import repo, storage
from aula.access import is_blocked
from aula.auth_routes import _require_csrf, current_auth
from aula.db import one, session
from aula.serialize import present_user

router = APIRouter(tags=["profils et tableau de bord"])

COLLAB_PREFERENCES = {
    "remote", "in_person", "hybrid", "structured", "flexible", "weekly", "async",
}


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=80)
    bio: str | None = Field(default=None, max_length=500)
    school: str | None = Field(default=None, max_length=120)
    faculty: str | None = Field(default=None, max_length=120)
    filiere: str | None = Field(default=None, max_length=80)
    level: str | None = Field(default=None, max_length=40)
    skills: list[str] | None = None
    interests: list[str] | None = None
    focus_goal: str | None = Field(default=None, max_length=220)
    project_types: list[str] | None = None
    availability: str | None = Field(default=None, max_length=200)
    collaboration_preferences: list[str] | None = None
    discoverable: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_null_updates(cls, value):
        if isinstance(value, dict) and any(item is None for item in value.values()):
            raise ValueError("Utilisez une valeur vide pour effacer un champ, pas null.")
        return value

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Le nom doit contenir au moins 2 caractères.")
        return value

    @field_validator("bio", "school", "faculty", "filiere", "level", "focus_goal", "availability")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("skills", "interests", "project_types")
    @classmethod
    def clean_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if len(value) > 16:
            raise ValueError("La liste ne peut pas dépasser 16 éléments.")
        result = []
        seen = set()
        for item in value:
            clean = item.strip()
            if not clean or len(clean) > 40:
                raise ValueError("Chaque élément doit contenir entre 1 et 40 caractères.")
            key = clean.casefold()
            if key not in seen:
                result.append(clean)
                seen.add(key)
        return result

    @field_validator("collaboration_preferences")
    @classmethod
    def validate_collaboration_preferences(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if len(value) > len(COLLAB_PREFERENCES) or any(item not in COLLAB_PREFERENCES for item in value):
            raise ValueError("Une préférence de collaboration n'est pas reconnue.")
        return list(dict.fromkeys(value))


def profile_completion(user: dict) -> dict:
    checks = [
        ("Nom", bool(user.get("name"))),
        ("Établissement", bool(user.get("school"))),
        ("Faculté", bool(user.get("faculty"))),
        ("Filière", bool(user.get("filiere"))),
        ("Niveau", bool(user.get("level"))),
        ("Biographie", bool(user.get("bio"))),
        ("Compétences", bool(user.get("skills"))),
        ("Centres d'intérêt", bool(user.get("interests"))),
        ("Objectif académique", bool(user.get("focus_goal"))),
        ("Projets recherchés", bool(user.get("project_types"))),
        ("Disponibilités", bool(user.get("availability"))),
        ("Préférences de collaboration", bool(user.get("collab_prefs") or user.get("collaboration_preferences"))),
        ("Photo", bool(user.get("avatar_file"))),
    ]
    completed = sum(1 for _, is_complete in checks if is_complete)
    total = len(checks)
    return {
        "percent": round(completed * 100 / total),
        "completed": completed,
        "total": total,
        "missing": [label for label, is_complete in checks if not is_complete],
    }


def _require_student(context: dict) -> dict:
    if context["user"]["role"] != "student":
        raise HTTPException(status_code=403, detail="Cette action est réservée aux étudiants.")
    return context["user"]


def _profile_response(user: dict) -> dict:
    profile = present_user(user)
    profile["collaboration_preferences"] = profile.pop("collab_prefs", [])
    profile["avatar_url"] = f"/api/profiles/{user['id']}/avatar" if user.get("avatar_file") else None
    profile["completion"] = profile_completion(profile)
    return profile


@router.get("/api/profile/me")
def get_my_profile(context: dict = Depends(current_auth)):
    _require_student(context)
    return _profile_response(context["user"])


@router.put("/api/profile/me")
def update_my_profile(
    payload: ProfileUpdate,
    request: Request,
    context: dict = Depends(current_auth),
):
    user = _require_student(context)
    _require_csrf(request, context)
    fields = payload.model_dump(exclude_unset=True)
    if "collaboration_preferences" in fields:
        fields["collab_prefs"] = fields.pop("collaboration_preferences")
    with session() as conn:
        updated = repo.update_profile(conn, user["id"], fields)
    return _profile_response(updated)


@router.post("/api/profile/me/avatar")
def upload_my_avatar(
    request: Request,
    file: UploadFile = File(...),
    context: dict = Depends(current_auth),
):
    user = _require_student(context)
    _require_csrf(request, context)
    try:
        with session() as conn:
            file_row = storage.save_upload(conn, file, user["id"], avatar=True)
            updated = repo.update_profile(conn, user["id"], {"avatar_file": file_row["stored_name"]})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    finally:
        file.file.close()
    return _profile_response(updated)


@router.get("/api/profiles/{user_id}")
def get_public_profile(user_id: int, context: dict = Depends(current_auth)):
    _require_student(context)
    with session() as conn:
        user = repo.user_by_id(conn, user_id)
    if not user or user["suspended"] or user["role"] != "student":
        raise HTTPException(status_code=404, detail="Profil étudiant introuvable.")
    with session() as conn:
        if is_blocked(conn, context["user"]["id"], user_id):
            raise HTTPException(status_code=404, detail="Profil étudiant introuvable.")
    profile = _profile_response(user)
    allowed = (
        "id", "name", "avatar_url", "school", "faculty", "filiere", "level", "bio",
        "skills", "interests", "project_types", "initials", "completion",
    )
    return {key: profile[key] for key in allowed}


@router.get("/api/profiles/{user_id}/avatar")
def get_profile_avatar(user_id: int, context: dict = Depends(current_auth)):
    _require_student(context)
    with session() as conn:
        if is_blocked(conn, context["user"]["id"], user_id):
            raise HTTPException(404, "Photo de profil introuvable.")
        row = one(
            conn,
            """SELECT f.* FROM users u JOIN files f ON f.stored_name = u.avatar_file
               WHERE u.id = ? AND u.role = 'student' AND u.suspended = 0""",
            (user_id,),
        )
    if not row:
        raise HTTPException(status_code=404, detail="Photo de profil introuvable.")
    path: Path = storage.safe_stored_path(row["stored_name"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Photo de profil introuvable.")
    return FileResponse(path, media_type=row["mime"], headers={
        "Cache-Control": "private, max-age=300",
        "X-Content-Type-Options": "nosniff",
    })


@router.get("/api/dashboard")
def get_dashboard(context: dict = Depends(current_auth)):
    user = _require_student(context)
    with session() as conn:
        fresh_user = repo.user_by_id(conn, user["id"])
        data = repo.dashboard(conn, fresh_user)
        all_tasks = repo.my_tasks(conn, user["id"])
        notifications = repo.list_notifications(conn, user["id"], limit=5)
        unread_notifications = repo.unread_count(conn, user["id"])
    profile = _profile_response(fresh_user)
    return {
        "user": profile,
        "profile_completion": profile["completion"],
        "groups": data["groups"],
        "tasks": data["tasks"],
        "all_tasks": all_tasks,
        "late": data["late"],
        "urgent_tasks": data["urgent"],
        "events": data["events"],
        "deadlines": data["deadlines"],
        "activity": data["activity"],
        "resources": data["resources"],
        "unread_messages": data["unread_messages"],
        "notifications": notifications,
        "unread_notifications": unread_notifications,
    }


@router.get("/api/notifications")
def get_notifications(context: dict = Depends(current_auth)):
    user = _require_student(context)
    with session() as conn:
        repo.sweep_deadlines(conn, repo.user_by_id(conn, user["id"]))
        notifications = repo.list_notifications(conn, user["id"], limit=100)
        unread = repo.unread_count(conn, user["id"])
    return {"notifications": notifications, "unread": unread}


@router.post("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id: int, request: Request, context: dict = Depends(current_auth)):
    user = _require_student(context)
    _require_csrf(request, context)
    with session() as conn:
        repo.mark_notification(conn, user["id"], notification_id)
        unread = repo.unread_count(conn, user["id"])
    return {"read": True, "unread": unread}


@router.post("/api/notifications/read-all")
def mark_notifications_read(request: Request, context: dict = Depends(current_auth)):
    user = _require_student(context)
    _require_csrf(request, context)
    with session() as conn:
        repo.mark_all_notifications(conn, user["id"])
    return {"read": True, "unread": 0}


@router.delete("/api/notifications/{notification_id}")
def delete_notification(notification_id: int, request: Request, context: dict = Depends(current_auth)):
    user = _require_student(context)
    _require_csrf(request, context)
    with session() as conn:
        deleted = repo.delete_notification(conn, user["id"], notification_id)
        unread = repo.unread_count(conn, user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Notification introuvable.")
    return {"deleted": True, "unread": unread}
