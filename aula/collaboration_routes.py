from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from aula import repo
from aula.access import Denied, group_or_404, membership, require_manager
from aula.auth_routes import _require_csrf, current_auth
from aula.db import many, one, session
from aula.matching import rank
from aula.serialize import present_user
from aula.util import dumps, loads, now
from aula.hub import hub

router = APIRouter(prefix="/api", tags=["groupes collaboratifs"])


class GroupPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=2000)
    filiere: str = Field(default="", max_length=80)
    subject: str = Field(default="", max_length=80)
    project_name: str = Field(default="", max_length=120)
    objective: str = Field(default="", max_length=2000)
    max_members: int = Field(default=8, ge=2, le=40)
    skills_wanted: list[str] = Field(default_factory=list, max_length=16)
    visibility: str = "public"
    preferred_level: str = Field(default="", max_length=40)
    deadline: str | None = Field(default=None, max_length=40)
    recruitment_open: bool = True

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Le nom doit contenir au moins deux caractères.")
        return value

    @field_validator("description", "filiere", "subject", "project_name", "objective", "preferred_level")
    @classmethod
    def trim(cls, value):
        return value.strip()

    @field_validator("visibility")
    @classmethod
    def check_visibility(cls, value):
        if value not in {"public", "private"}:
            raise ValueError("Visibilité invalide.")
        return value

    @field_validator("skills_wanted")
    @classmethod
    def clean_skills(cls, values):
        if any(not item.strip() or len(item.strip()) > 40 for item in values):
            raise ValueError("Chaque compétence doit contenir de 1 à 40 caractères.")
        return list(dict.fromkeys(item.strip() for item in values))


class JoinPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(default="", max_length=500)


class RolePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str


class InvitePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: int = Field(gt=0)


def _student(ctx):
    if ctx["user"]["role"] != "student":
        raise HTTPException(403, "Cette action est réservée aux étudiants.")
    return ctx["user"]


def _group_view(conn, group, viewer):
    data = dict(group)
    data["skills_wanted"] = loads(data.get("skills_wanted"), [])
    data["recruitment_open"] = bool(data.get("recruitment_open", 1))
    data["member_count"] = repo.count_members(conn, data["id"])
    member = repo.members_of(conn, data["id"])
    current = next((item for item in member if item["id"] == viewer["id"]), None)
    data["joined"] = bool(current)
    data["member_role"] = current.get("member_role") if current else None
    data["unread_count"] = repo.scope_unread(conn, viewer["id"], f"g:{data['id']}", group_id=data["id"]) if current else 0
    data["members"] = [
        {"id": item["id"], "name": item["name"], "avatar_url": f"/api/profiles/{item['id']}/avatar" if item.get("avatar_file") else None,
         "initials": item["initials"], "school": item["school"], "filiere": item["filiere"], "level": item["level"],
         "skills": item["skills"], "role": item["member_role"], "joined_at": item["joined_at"]}
        for item in map(present_user, member)
    ]
    data["activity"] = repo.list_activity(conn, data["id"], 8)
    if current and current["member_role"] in ("owner", "admin"):
        data["join_requests"] = [
            {"id": row["id"], "user_id": row["user_id"], "name": row["name"], "message": row["message"],
             "created_at": row["created_at"], "skills": loads(row.get("skills"), []),
             "filiere": row.get("filiere", ""), "level": row.get("level", "")}
            for row in repo.join_requests_for(conn, data["id"])
        ]
        data["invitations"] = [
            {"id": item["id"], "invitee_id": item["invitee_id"], "name": item["name"], "status": item["status"], "created_at": item["created_at"]}
            for item in repo.group_invitations(conn, data["id"])
        ]
    else:
        data["join_requests"] = []
        data["invitations"] = []
    return data


def _denied(call):
    try:
        return call()
    except Denied as exc:
        raise HTTPException(exc.status, exc.message) from None


@router.get("/groups")
def discover_groups(q: str = "", filiere: str = "", subject: str = "", level: str = "", skill: str = "", recruiting: bool | None = None, mine: bool = False, context: dict = Depends(current_auth)):
    user = _student(context)
    with session() as conn:
        filters = {"q": q, "filiere": filiere, "subject": subject, "preferred_level": level, "skill": skill, "mine": mine, "recruiting": recruiting}
        groups = repo.list_groups(conn, user["id"], filters)
        return [_group_view(conn, group, user) for group in groups]


@router.post("/groups", status_code=201)
def create_group(payload: GroupPayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context); _require_csrf(request, context)
    data = payload.model_dump()
    if len(data["name"]) < 2:
        raise HTTPException(422, "Le nom doit contenir au moins deux caractères.")
    with session() as conn:
        group = repo.create_group(conn, user, data)
        conn.execute("UPDATE groupes SET preferred_level = ?, recruitment_open = ? WHERE id = ?", (data["preferred_level"], int(data["recruitment_open"]), group["id"]))
        group = repo.get_group(conn, group["id"])
        return _group_view(conn, group, user)


@router.get("/groups/{group_id}")
def get_group(group_id: int, context: dict = Depends(current_auth)):
    user = _student(context)
    with session() as conn:
        group, _ = _denied(lambda: group_or_404(conn, group_id, user))
        return _group_view(conn, group, user)


@router.put("/groups/{group_id}")
def edit_group(group_id: int, payload: GroupPayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context); _require_csrf(request, context)
    with session() as conn:
        group, member = _denied(lambda: require_manager(conn, group_id, user))
        data = payload.model_dump()
        repo.update_group(conn, group_id, data)
        conn.execute("UPDATE groupes SET preferred_level = ?, recruitment_open = ? WHERE id = ?", (data["preferred_level"], int(data["recruitment_open"]), group_id))
        return _group_view(conn, repo.get_group(conn, group_id), user)


@router.post("/groups/{group_id}/join")
def join_group(group_id: int, request: Request, context: dict = Depends(current_auth)):
    user = _student(context); _require_csrf(request, context)
    with session() as conn:
        group, _ = _denied(lambda: group_or_404(conn, group_id, user))
        if group["visibility"] != "public": raise HTTPException(404, "Groupe introuvable.")
        if not group.get("recruitment_open", 1): raise HTTPException(409, "Le recrutement de ce groupe est fermé.")
        if membership(conn, group_id, user["id"]): raise HTTPException(409, "Vous êtes déjà membre de ce groupe.")
        if repo.count_members(conn, group_id) >= group["max_members"]: raise HTTPException(409, "Ce groupe a atteint sa capacité maximale.")
        pending = one(conn, "SELECT id FROM join_requests WHERE group_id=? AND user_id=? AND status='pending'", (group_id, user["id"]))
        if pending: raise HTTPException(409, "Votre demande est déjà en attente.")
        repo.add_member(conn, group_id, user["id"])
        conn.execute("UPDATE join_requests SET status='accepted' WHERE group_id=? AND user_id=? AND status='pending'", (group_id, user["id"]))
        repo.log_activity(conn, group_id=group_id, actor_id=user["id"], kind="member_joined", summary=f"{user['name']} a rejoint le groupe", href=f"/app/groupes/{group_id}")
        return _group_view(conn, repo.get_group(conn, group_id), user)


@router.post("/groups/{group_id}/requests")
def request_to_join(group_id: int, payload: JoinPayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context); _require_csrf(request, context)
    with session() as conn:
        group, _ = _denied(lambda: group_or_404(conn, group_id, user))
        if group["visibility"] != "public": raise HTTPException(404, "Groupe introuvable.")
        if not group.get("recruitment_open", 1): raise HTTPException(409, "Le recrutement de ce groupe est fermé.")
        if repo.count_members(conn, group_id) >= group["max_members"]: raise HTTPException(409, "Ce groupe a atteint sa capacité maximale.")
        try: request_id = repo.upsert_join_request(conn, group_id, user["id"], payload.message.strip())
        except ValueError as exc: raise HTTPException(409, str(exc)) from None
        return {"id": request_id, "status": "pending"}


@router.post("/groups/{group_id}/requests/{request_id}/respond")
def respond_join_request(group_id: int, request_id: int, accept: bool, request: Request, context: dict = Depends(current_auth)):
    user = _student(context); _require_csrf(request, context)
    with session() as conn:
        group, _ = _denied(lambda: require_manager(conn, group_id, user))
        join_req = repo.get_join_request(conn, request_id)
        if not join_req or join_req["group_id"] != group_id or join_req["status"] != "pending": raise HTTPException(404, "Demande introuvable.")
        if accept and (repo.count_members(conn, group_id) >= group["max_members"] or not group.get("recruitment_open", 1)):
            raise HTTPException(409, "Le groupe ne peut plus accueillir de membre.")
        repo.set_join_status(conn, request_id, "accepted" if accept else "declined")
        if accept: repo.add_member(conn, group_id, join_req["user_id"])
        return {"status": "accepted" if accept else "declined"}


@router.post("/groups/{group_id}/invitations")
def invite_student(group_id: int, payload: InvitePayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context); _require_csrf(request, context)
    with session() as conn:
        group, _ = _denied(lambda: require_manager(conn, group_id, user))
        target = repo.user_by_id(conn, payload.user_id)
        if not target or target["role"] != "student" or target["suspended"] or not target["discoverable"]: raise HTTPException(404, "Étudiant introuvable.")
        if repo.count_members(conn, group_id) >= group["max_members"]: raise HTTPException(409, "Le groupe a atteint sa capacité maximale.")
        try: invitation_id = repo.invite(conn, group_id, user["id"], payload.user_id)
        except ValueError as exc: raise HTTPException(409, str(exc)) from None
        return {"id": invitation_id, "status": "pending"}


@router.get("/group-invitations")
def my_invitations(context: dict = Depends(current_auth)):
    user = _student(context)
    with session() as conn: return repo.pending_invitations(conn, user["id"])


@router.post("/group-invitations/{invitation_id}/respond")
def respond_invitation(invitation_id: int, accept: bool, request: Request, context: dict = Depends(current_auth)):
    user = _student(context); _require_csrf(request, context)
    with session() as conn:
        invitation = repo.get_invitation(conn, invitation_id)
        if not invitation or invitation["invitee_id"] != user["id"] or invitation["status"] != "pending": raise HTTPException(404, "Invitation introuvable.")
        group = repo.get_group(conn, invitation["group_id"])
        if accept and (repo.count_members(conn, group["id"]) >= group["max_members"] or not group.get("recruitment_open", 1)):
            raise HTTPException(409, "Ce groupe ne peut plus accueillir de membre.")
        repo.set_invitation_status(conn, invitation_id, "accepted" if accept else "declined")
        if accept: repo.add_member(conn, group["id"], user["id"])
        return {"status": "accepted" if accept else "declined"}


@router.delete("/groups/{group_id}/membership")
def leave_group(group_id: int, request: Request, context: dict = Depends(current_auth)):
    user = _student(context); _require_csrf(request, context)
    with session() as conn:
        group, member = _denied(lambda: group_or_404(conn, group_id, user))
        if not member: raise HTTPException(404, "Vous n'êtes pas membre de ce groupe.")
        if member["role"] == "owner": raise HTTPException(409, "Transférez la propriété avant de quitter le groupe.")
        repo.remove_member(conn, group_id, user["id"])
        return {"status": "left"}


@router.delete("/groups/{group_id}")
def delete_group(group_id: int, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        group, member = _denied(lambda: require_manager(conn, group_id, user))
        if member["role"] != "owner":
            raise HTTPException(403, "Seul le propriétaire peut supprimer le groupe.")
        repo.delete_group(conn, group_id)
    return {"deleted": True, "id": group_id}


@router.put("/groups/{group_id}/members/{member_id}/role")
def change_member_role(group_id: int, member_id: int, payload: RolePayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context); _require_csrf(request, context)
    if payload.role not in {"admin", "member"}: raise HTTPException(422, "Rôle invalide.")
    with session() as conn:
        group, manager = _denied(lambda: require_manager(conn, group_id, user))
        if manager["role"] != "owner" and user["role"] != "admin": raise HTTPException(403, "Seul le propriétaire peut gérer les rôles.")
        target = membership(conn, group_id, member_id)
        if not target or target["role"] == "owner": raise HTTPException(404, "Membre introuvable.")
        repo.set_member_role(conn, group_id, member_id, payload.role)
        return {"user_id": member_id, "role": payload.role}


@router.post("/groups/{group_id}/owner")
def transfer_group_owner(group_id: int, payload: InvitePayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context); _require_csrf(request, context)
    with session() as conn:
        _, current = _denied(lambda: require_manager(conn, group_id, user))
        if current["role"] != "owner": raise HTTPException(403, "Seul le propriétaire actuel peut transférer le groupe.")
        target = membership(conn, group_id, payload.user_id)
        if not target or payload.user_id == user["id"]: raise HTTPException(404, "Le futur propriétaire doit déjà être membre du groupe.")
        conn.execute("UPDATE group_members SET role='admin' WHERE group_id=? AND user_id=?", (group_id, user["id"]))
        conn.execute("UPDATE group_members SET role='owner' WHERE group_id=? AND user_id=?", (group_id, payload.user_id))
        conn.execute("UPDATE groupes SET owner_id=? WHERE id=?", (payload.user_id, group_id))
        return {"owner_id": payload.user_id}


@router.delete("/groups/{group_id}/members/{member_id}")
def remove_group_member(group_id: int, member_id: int, request: Request, context: dict = Depends(current_auth)):
    user = _student(context); _require_csrf(request, context)
    with session() as conn:
        _, manager = _denied(lambda: require_manager(conn, group_id, user))
        target = membership(conn, group_id, member_id)
        if not target or target["role"] == "owner": raise HTTPException(404, "Membre introuvable.")
        if manager["role"] != "owner" and manager["role"] != "admin": raise HTTPException(403, "Action réservée aux responsables.")
        repo.remove_member(conn, group_id, member_id)
        hub.publish([member_id], {"type": "force_disconnect", "reason": "removed_from_group", "group_id": group_id})
        return {"status": "removed"}


def _student_card(user, viewer_id, connection=None):
    profile = present_user(user)
    return {
        "id": profile["id"], "name": profile["name"], "initials": profile["initials"],
        "avatar_url": f"/api/profiles/{profile['id']}/avatar" if profile.get("avatar_file") else None,
        "school": profile.get("school", ""), "faculty": profile.get("faculty", ""),
        "filiere": profile.get("filiere", ""), "level": profile.get("level", ""),
        "bio": profile.get("bio", ""), "skills": profile.get("skills", []),
        "interests": profile.get("interests", []), "project_types": profile.get("project_types", []),
        "focus_goal": profile.get("focus_goal", ""), "connection_status": connection,
        "is_self": profile["id"] == viewer_id,
    }


def _connection_info(conn, a, b):
    row = repo.find_connection(conn, a, b)
    if not row or row["status"] == "blocked":
        return None
    if row["status"] == "pending":
        return "pending_received" if row["addressee_id"] == a else "pending_sent"
    return row["status"]


@router.get("/students")
def discover_students(q: str = "", filiere: str = "", school: str = "", faculty: str = "", level: str = "", skill: str = "", interest: str = "", project_type: str = "", context: dict = Depends(current_auth)):
    user = _student(context)
    filters = {"q": q, "filiere": filiere, "school": school, "faculty": faculty, "level": level, "skill": skill, "interest": interest, "project_type": project_type}
    with session() as conn:
        users = repo.search_students(conn, user["id"], filters)
        return [{**_student_card(person, user["id"], _connection_info(conn, user["id"], person["id"])), "recommendation": None} for person in users]


@router.get("/students/recommendations")
def student_recommendations(context: dict = Depends(current_auth)):
    user = _student(context)
    with session() as conn:
        me = repo.user_by_id(conn, user["id"])
        others = repo.search_students(conn, user["id"], {})
        ranked = rank(me, others, limit=20)
        result = []
        for item in ranked:
            person = item["user"]
            card = _student_card(person, user["id"], _connection_info(conn, user["id"], person["id"]))
            card["recommendation"] = {"reasons": item["reasons"], "explanation": item["sentence"]}
            result.append(card)
        return result


class ConnectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: int = Field(gt=0)


@router.post("/connections", status_code=201)
def send_connection(payload: ConnectionPayload, request: Request, context: dict = Depends(current_auth)):
    user = _student(context); _require_csrf(request, context)
    with session() as conn:
        try: status = repo.request_connection(conn, user["id"], payload.user_id)
        except ValueError as exc: raise HTTPException(409, str(exc)) from None
        return {"user_id": payload.user_id, "status": status}


@router.get("/connections")
def list_my_connections(context: dict = Depends(current_auth)):
    user = _student(context)
    with session() as conn:
        rows = many(conn, "SELECT * FROM connections WHERE requester_id=? OR addressee_id=? ORDER BY updated_at DESC", (user["id"], user["id"]))
        result = {"received": [], "sent": [], "accepted": []}
        for row in rows:
            if row["status"] not in {"pending", "accepted"}: continue
            peer_id = row["addressee_id"] if row["requester_id"] == user["id"] else row["requester_id"]
            peer = repo.user_by_id(conn, peer_id)
            if not peer or peer["suspended"] or peer["role"] != "student": continue
            item = {**_student_card(peer, user["id"], row["status"]), "created_at": row["created_at"], "updated_at": row["updated_at"]}
            bucket = "accepted" if row["status"] == "accepted" else ("sent" if row["requester_id"] == user["id"] else "received")
            result[bucket].append(item)
        return result


@router.post("/connections/{other_id}/respond")
def respond_connection(other_id: int, accept: bool, request: Request, context: dict = Depends(current_auth)):
    user = _student(context); _require_csrf(request, context)
    with session() as conn:
        try: repo.respond_connection(conn, user["id"], other_id, accept)
        except ValueError as exc: raise HTTPException(404, str(exc)) from None
        return {"user_id": other_id, "status": "accepted" if accept else "declined"}


@router.delete("/connections/{other_id}")
def remove_connection(other_id: int, request: Request, context: dict = Depends(current_auth)):
    user = _student(context)
    _require_csrf(request, context)
    with session() as conn:
        try:
            repo.remove_connection(conn, user["id"], other_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
    return {"removed": True, "user_id": other_id}
