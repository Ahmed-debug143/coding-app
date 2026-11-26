import asyncio
import logging
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aula import repo
from aula.access import Denied, membership, require_manager
from aula.auth_routes import _require_csrf, current_auth
from aula.db import many, session
from aula.util import PARIS, now

router = APIRouter(prefix="/api", tags=["calendrier"])
logger = logging.getLogger(__name__)


class EventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=140)
    kind: Literal["reunion", "travail", "echeance", "autre"] = "reunion"
    description: str = Field(default="", max_length=1000)
    starts_at: str
    ends_at: str | None = None
    group_id: int | None = Field(default=None, gt=0)
    reminder_at: str | None = None

    @field_validator("title", "description")
    @classmethod
    def trim(cls, value):
        return value.strip()

    @field_validator("starts_at", "ends_at", "reminder_at")
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

    @model_validator(mode="after")
    def reminder_precedes_event(self):
        if self.reminder_at:
            reminder = datetime.fromisoformat(self.reminder_at.replace("Z", "+00:00"))
            start = datetime.fromisoformat(self.starts_at.replace("Z", "+00:00"))
            if reminder.tzinfo:
                reminder = reminder.astimezone(PARIS).replace(tzinfo=None)
            if start.tzinfo:
                start = start.astimezone(PARIS).replace(tzinfo=None)
            if reminder > start:
                raise ValueError("Le rappel doit être fixé au plus tard au début de l’événement.")
        return self


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


def dispatch_due_reminders():
    current_time = now()
    with session() as conn:
        due_events = many(
            conn,
            """SELECT id, group_id, created_by, title, starts_at, reminder_at
               FROM events
               WHERE reminder_at IS NOT NULL AND reminder_sent_at IS NULL AND reminder_at<=?
               ORDER BY reminder_at, id""",
            (current_time,),
        )
        for event in due_events:
            recipients = many(
                conn,
                "SELECT user_id AS id FROM group_members WHERE group_id=?",
                (event["group_id"],),
            ) if event["group_id"] else [{"id": event["created_by"]}]
            for recipient in recipients:
                repo.notify(
                    conn,
                    user_id=recipient["id"],
                    kind="event_reminder",
                    title=f"Rappel : {event['title']}",
                    body=f"Événement prévu le {event['starts_at']}.",
                    dedupe_key=f"event-reminder:{event['id']}:{recipient['id']}",
                )
            conn.execute(
                "UPDATE events SET reminder_sent_at=? WHERE id=? AND reminder_sent_at IS NULL",
                (current_time, event["id"]),
            )
        return len(due_events)


async def reminder_worker():
    while True:
        try:
            await asyncio.to_thread(dispatch_due_reminders)
        except Exception:
            logger.exception("Impossible de traiter les rappels du calendrier.")
        await asyncio.sleep(30)
