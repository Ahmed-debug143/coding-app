from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from aula import assistant, repo
from aula.access import Denied, require_writer
from aula.auth_routes import _require_csrf, current_auth
from aula.db import session
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
            data["partner_result"] = {
                "mode": "local",
                "title": "Profils déjà enregistrés",
                "intro": "Utilisez les recommandations Campusia fondées sur les compétences, intérêts et objectifs réellement renseignés.",
                "sections": [],
                "proposals": [],
            }
    return assistant.answer(payload.action, data)

