from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from aula import assistant, repo
from aula.access import Denied, require_writer
from aula.auth_routes import _require_csrf, current_auth
from aula.db import session
from aula.matching import rank
from aula.serialize import pack_messages

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class AssistantPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["summary", "tasks", "organize", "study", "partners"]
    group_id: int | None = Field(default=None, gt=0)
    question: str = Field(default="", max_length=2000)


@router.post("/answer")
def answer(payload: AssistantPayload, request: Request, context: dict = Depends(current_auth)):
    user = context["user"]
    if user["role"] != "student":
        raise HTTPException(403, "Cette action est réservée aux étudiants.")
    _require_csrf(request, context)
    if payload.action in {"summary", "tasks", "organize"} and payload.group_id is None:
        raise HTTPException(422, "Choisissez un groupe pour cette action.")
    data = {}
    with session() as conn:
        if payload.group_id:
            try:
                group, _ = require_writer(conn, payload.group_id, user)
            except Denied as exc:
                raise HTTPException(exc.status, exc.message) from None
            rows, _ = repo.list_messages(
                conn, group_id=payload.group_id, limit=100,
            )
            messages = pack_messages(conn, rows, user["id"])
            tasks = repo.list_tasks(conn, payload.group_id, {})
            data = {
                "messages": messages,
                "titles": [task["title"] for task in tasks],
                "group": group,
                "progress": repo.progress(conn, payload.group_id),
                "workload": repo.workload(conn, payload.group_id),
                "tasks": tasks,
            }
        if payload.action == "study":
            data["question"] = payload.question
        if payload.action == "partners":
            me = repo.user_by_id(conn, user["id"])
            people = repo.search_students(conn, user["id"], {})
            suggestions = rank(me, people, limit=5)
            data["partner_result"] = {
                "mode": "local",
                "title": "Profils recommandés",
                "intro": "Ces suggestions s’appuient sur les informations de profil renseignées, pas sur une garantie de compatibilité.",
                "sections": [{
                    "heading": "Étudiants suggérés",
                    "items": [
                        f"{item['user']['name']} — {item['sentence']}" for item in suggestions
                    ] or ["Aucun profil ne correspond encore aux critères renseignés. Complétez vos compétences, intérêts et objectifs pour obtenir des suggestions."],
                }],
                "proposals": [],
            }
    return assistant.answer(payload.action, data)

