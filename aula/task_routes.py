from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aula import repo
from aula.access import Denied, require_writer
from aula.auth_routes import _require_csrf, current_auth
from aula.db import one, session
from aula.util import initials, now

router = APIRouter(prefix="/api", tags=["tâches"])


def _student(context):
    if context["user"]["role"] != "student":
        raise HTTPException(403, "Cette action est réservée aux étudiants.")
    return context["user"]


def _writer(conn, group_id, user):
    try:
        return require_writer(conn, group_id, user)
    except Denied as exc:
        raise HTTPException(exc.status, exc.message) from None


def _date_value(value, *, end_of_day=False):
    if value is None or value == "":
        return None
    try:
        if len(value) == 10:
            date.fromisoformat(value)
            return value + ("T23:59:59" if end_of_day else "T00:00:00")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        raise ValueError("Utilisez une date ISO valide.") from None


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=140)
    description: str = Field(default="", max_length=4000)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    starts_at: str | None = Field(default=None, max_length=40)
    due_at: str | None = Field(default=None, max_length=40)
    estimate_hours: float | None = Field(default=None, ge=0, le=1000)
    assignee_ids: list[int] = Field(default_factory=list, max_length=40)

    @field_validator("title", "description")
    @classmethod
    def trim_text(cls, value):
        return value.strip()

    @field_validator("starts_at", "due_at")
    @classmethod
    def validate_dates(cls, value):
        if value is not None:
            _date_value(value)
        return value


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=2, max_length=140)
    description: str | None = Field(default=None, max_length=4000)
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    starts_at: str | None = Field(default=None, max_length=40)
    due_at: str | None = Field(default=None, max_length=40)
    estimate_hours: float | None = Field(default=None, ge=0, le=1000)

    @model_validator(mode="before")
    @classmethod
    def reject_null_text_fields(cls, values):
        if isinstance(values, dict) and any(values.get(key) is None for key in ("title", "description", "priority") if key in values):
            raise ValueError("Le titre, la description et la priorité ne peuvent pas être null.")
        return values

    @field_validator("title", "description")
    @classmethod
    def trim_text(cls, value):
        if value is None: return None
        return value.strip()

    @field_validator("starts_at", "due_at")
    @classmethod
    def validate_dates(cls, value):
        if value is not None:
            _date_value(value)
        return value


class StatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["todo", "doing", "review", "done"]


class AssigneeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_ids: list[int] = Field(max_length=40)


class TaskComment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def trim_body(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Le commentaire ne peut pas être vide.")
        return value


def _task_view(conn, task, *, detailed=False):
    data = {key: task.get(key) for key in (
        "id", "group_id", "group_name", "title", "description", "status", "priority", "starts_at", "due_at",
        "estimate_hours", "created_by", "created_at", "updated_at", "source_message_id",
    ) if key in task}
    data["assignees"] = [
        {"id": item["id"], "name": item["name"], "initials": initials(item["name"]),
         "avatar_url": f"/api/profiles/{item['id']}/avatar" if item.get("avatar_file") else None}
        for item in repo.assignees_map(conn, [task["id"]]).get(task["id"], [])
    ]
    data["overdue"] = bool(task.get("due_at") and task["due_at"] < now() and task["status"] != "done")
    if detailed:
        data["comments"] = repo.task_comments(conn, task["id"])
        data["history"] = repo.task_history(conn, task["id"])
    return data


def _with_permissions(view, conn, task, user, member):
    manager_or_creator = _can_manage(task, member, user)
    assigned = user["id"] in repo.task_assignee_ids(conn, task["id"])
    view["can_edit"] = manager_or_creator
    view["can_delete"] = manager_or_creator
    view["can_change_status"] = bool(manager_or_creator or assigned)
    return view


def _load_task(conn, task_id, user):
    task = repo.get_task(conn, task_id)
    if not task:
        raise HTTPException(404, "Tâche introuvable.")
    group, member = _writer(conn, task["group_id"], user)
    return task, group, member


def _can_manage(task, member, user):
    return bool(member and (member["role"] in {"owner", "admin"} or task["created_by"] == user["id"]))


@router.get("/groups/{group_id}/tasks")
def list_group_tasks(group_id: int, status: str | None = None, priority: str | None = None, assignee: int | None = None, q: str = "", late: bool = False, sort: str = "due_asc", context: dict = Depends(current_auth)):
    user = _student(context)
    if status is not None and status not in {"todo", "doing", "review", "done"}: raise HTTPException(422, "Statut invalide.")
    if priority is not None and priority not in {"low", "normal", "high", "urgent"}: raise HTTPException(422, "Priorité invalide.")
    if sort not in {"due_asc", "due_desc", "created_asc", "created_desc"}: raise HTTPException(422, "Tri invalide.")
    with session() as conn:
        _, member = _writer(conn, group_id, user)
        filters = {"status": status, "priority": priority, "assignee": assignee, "q": q, "late": late, "sort": sort}
        items = repo.list_tasks(conn, group_id, filters)
        return {"tasks": [_with_permissions(_task_view(conn, item), conn, item, user, member) for item in items], "progress": repo.progress(conn, group_id)}


@router.post("/groups/{group_id}/tasks", status_code=201)
def create_group_task(group_id: int, payload: TaskCreate, request: Request, context: dict = Depends(current_auth)):
    user = _student(context); _require_csrf(request, context)
    if len(payload.title.strip()) < 2: raise HTTPException(422, "Le titre doit contenir au moins deux caractères.")
    with session() as conn:
        _, member = _writer(conn, group_id, user)
        member_ids = set(repo.member_ids(conn, group_id))
        assignees = list(dict.fromkeys(payload.assignee_ids))
        if any(user_id not in member_ids for user_id in assignees): raise HTTPException(422, "Chaque responsable doit être membre du groupe.")
        task_id = repo.create_task(
            conn, group_id=group_id, title=payload.title.strip(), description=payload.description.strip(), status="todo",
            priority=payload.priority, starts_at=_date_value(payload.starts_at), due_at=_date_value(payload.due_at, end_of_day=True),
            estimate_hours=payload.estimate_hours, created_by=user["id"],
        )
        repo.set_assignees(conn, task_id, assignees)
        repo.add_task_history(conn, task_id, user["id"], "created", "Tâche créée")
        task = repo.get_task(conn, task_id)
        return _with_permissions(_task_view(conn, task, detailed=True), conn, task, user, member)


@router.get("/tasks/mine")
def list_my_tasks(context: dict = Depends(current_auth)):
    user = _student(context)
    with session() as conn:
        tasks = repo.my_tasks(conn, user["id"])
        return [_task_view(conn, task) for task in tasks]


@router.get("/tasks/{task_id}")
def get_task(task_id: int, context: dict = Depends(current_auth)):
    user = _student(context)
    with session() as conn:
        task, _, member = _load_task(conn, task_id, user)
        task["group_name"] = one(conn, "SELECT name FROM groupes WHERE id = ?", (task["group_id"],))["name"]
        return _with_permissions(_task_view(conn, task, detailed=True), conn, task, user, member)


@router.put("/tasks/{task_id}")
def edit_task(task_id: int, payload: TaskUpdate, request: Request, context: dict = Depends(current_auth)):
    user = _student(context); _require_csrf(request, context)
    fields = payload.model_dump(exclude_unset=True)
    if "title" in fields and len(fields["title"]) < 2: raise HTTPException(422, "Le titre doit contenir au moins deux caractères.")
    for name in ("starts_at", "due_at"):
        if name in fields: fields[name] = _date_value(fields[name], end_of_day=name == "due_at")
    with session() as conn:
        task, _, member = _load_task(conn, task_id, user)
        if not _can_manage(task, member, user): raise HTTPException(403, "Seul un responsable ou le créateur peut modifier les détails de cette tâche.")
        changed = {key: value for key, value in fields.items() if task.get(key) != value}
        if changed:
            repo.update_task(conn, task_id, changed)
            repo.add_task_history(conn, task_id, user["id"], "updated", ", ".join(sorted(changed)))
        updated = repo.get_task(conn, task_id)
        updated["group_name"] = one(conn, "SELECT name FROM groupes WHERE id = ?", (updated["group_id"],))["name"]
        return _with_permissions(_task_view(conn, updated, detailed=True), conn, updated, user, member)


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, request: Request, context: dict = Depends(current_auth)):
    user = _student(context); _require_csrf(request, context)
    with session() as conn:
        task, _, member = _load_task(conn, task_id, user)
        if not _can_manage(task, member, user): raise HTTPException(403, "Seul un responsable ou le créateur peut supprimer cette tâche.")
        repo.delete_task(conn, task_id)
        return {"deleted": True, "id": task_id}


@router.post("/tasks/{task_id}/status")
def update_task_status(task_id: int, payload: StatusUpdate, request: Request, context: dict = Depends(current_auth)):
    user = _student(context); _require_csrf(request, context)
    with session() as conn:
        task, _, member = _load_task(conn, task_id, user)
        assigned = user["id"] in repo.task_assignee_ids(conn, task_id)
        if not assigned and not _can_manage(task, member, user): raise HTTPException(403, "Seuls les responsables et personnes affectées peuvent changer le statut.")
        if task["status"] != payload.status:
            repo.update_task(conn, task_id, {"status": payload.status})
            repo.add_task_history(conn, task_id, user["id"], "status", f"{task['status']} → {payload.status}")
        updated = repo.get_task(conn, task_id)
        return _with_permissions(_task_view(conn, updated, detailed=True), conn, updated, user, member)


@router.post("/tasks/{task_id}/assign")
def assign_task(task_id: int, payload: AssigneeUpdate, request: Request, context: dict = Depends(current_auth)):
    user = _student(context); _require_csrf(request, context)
    with session() as conn:
        task, _, member = _load_task(conn, task_id, user)
        if not _can_manage(task, member, user): raise HTTPException(403, "Seul un responsable ou le créateur peut gérer les affectations.")
        assignees = list(dict.fromkeys(payload.user_ids))
        members = set(repo.member_ids(conn, task["group_id"]))
        if any(user_id not in members for user_id in assignees): raise HTTPException(422, "Chaque responsable doit être membre du groupe.")
        old = set(repo.task_assignee_ids(conn, task_id))
        if old != set(assignees):
            repo.set_assignees(conn, task_id, assignees)
            repo.add_task_history(conn, task_id, user["id"], "assignment", "Affectations mises à jour")
        updated = repo.get_task(conn, task_id)
        return _with_permissions(_task_view(conn, updated, detailed=True), conn, updated, user, member)


@router.post("/tasks/{task_id}/comments", status_code=201)
def add_task_comment(task_id: int, payload: TaskComment, request: Request, context: dict = Depends(current_auth)):
    user = _student(context); _require_csrf(request, context)
    with session() as conn:
        task, _, _ = _load_task(conn, task_id, user)
        comment_id = repo.add_comment(conn, task_id, user["id"], payload.body)
        repo.add_task_history(conn, task_id, user["id"], "comment", "Commentaire ajouté")
        return {"id": comment_id, "task_id": task_id, "body": payload.body, "author_id": user["id"], "author_name": user["name"]}
