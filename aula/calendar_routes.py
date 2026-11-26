from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from aula import repo
from aula.access import Denied, membership, require_manager
from aula.auth_routes import _require_csrf, current_auth
from aula.db import session

router = APIRouter(prefix="/api", tags=["calendrier"])


class EventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=140)
    kind: Literal["reunion", "travail", "echeance", "autre"] = "reunion"
    description: str = Field(default="", max_length=1000)
    starts_at: str
    ends_at: str | None = None
    group_id: int | None = Field(default=None, gt=0)

    @field_validator("title", "description")
    @classmethod
    def trim(cls, value):
        return value.strip()

    @field_validator("starts_at", "ends_at")
    @classmethod
    def validate_iso(cls, value):
        if value is None:
            return None
        try:
            if len(value) == 10:
                date.fromisoformat(value)
            else:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            raise ValueError("Utilisez une date ISO valide.") from None
        return value


def _student(context):
    if context["user"]["role"] != "student":
        raise HTTPException(403, "Cette action est réservée aux étudiants.")
    return context["user"]


@router.get("/calendar")
def list_calendar(start: str, end: str, context: dict = Depends(current_auth)):
    user = _student(context)
    try:
        datetime.fromisoformat(start.replace("Z", "+00:00"))
        datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, "Période ISO invalide.") from None
    with session() as conn:
        return {
            "events": repo.events_between(conn, user["id"], start, end),
            "deadlines": repo.deadlines_between(conn, user["id"], start, end),
        }


@router.post("/calendar/events", status_code=201)
def create_event(payload: EventPayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    if payload.ends_at and payload.ends_at < payload.starts_at:
        raise HTTPException(422, "La fin doit suivre le début.")
    with session() as conn:
        if payload.group_id:
            try:
                require_manager(conn, payload.group_id, user)
            except Denied as exc:
                raise HTTPException(exc.status, exc.message) from None
        event_id = repo.create_event(conn, payload.model_dump() | {"created_by": user["id"]})
        return repo.get_event(conn, event_id)


@router.put("/calendar/events/{event_id}")
def update_event(event_id: int, payload: EventPayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    if payload.ends_at and payload.ends_at < payload.starts_at:
        raise HTTPException(422, "La fin doit suivre le début.")
    with session() as conn:
        event = repo.get_event(conn, event_id)
        if not event:
            raise HTTPException(404, "Événement introuvable.")
        if event["created_by"] != user["id"]:
            if not event["group_id"]:
                raise HTTPException(403, "Vous ne pouvez modifier que vos propres événements.")
            try:
                require_manager(conn, event["group_id"], user)
            except Denied as exc:
                raise HTTPException(exc.status, exc.message) from None
        if payload.group_id:
            try:
                require_manager(conn, payload.group_id, user)
            except Denied as exc:
                raise HTTPException(exc.status, exc.message) from None
        return repo.update_event(conn, event_id, payload.model_dump())


@router.delete("/calendar/events/{event_id}")
def delete_event(event_id: int, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        event = repo.get_event(conn, event_id)
        if not event:
            raise HTTPException(404, "Événement introuvable.")
        if event["created_by"] != user["id"]:
            if not event["group_id"]:
                raise HTTPException(403, "Vous ne pouvez supprimer que vos propres événements.")
            try:
                require_manager(conn, event["group_id"], user)
            except Denied as exc:
                raise HTTPException(exc.status, exc.message) from None
        repo.delete_event(conn, event_id)
    return {"deleted": True, "id": event_id}
