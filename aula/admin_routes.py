from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from aula import repo
from aula.auth_routes import _require_csrf, current_auth
from aula.db import session
from aula.util import now
from aula.hub import hub

router = APIRouter(prefix="/api/admin", tags=["administration"])


class SuspensionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suspended: bool


class ReportResolutionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern="^(resolved|dismissed)$")
    note: str = Field(default="", max_length=500)


def _admin(context):
    if context["user"]["role"] != "admin":
        raise HTTPException(403, "Cette action est réservée aux administrateurs.")
    return context["user"]


@router.get("/stats")
def admin_stats(context: dict = Depends(current_auth)):
    _admin(context)
    with session() as conn:
        return repo.admin_stats(conn)


@router.get("/users")
def admin_users(q: str = "", context: dict = Depends(current_auth)):
    _admin(context)
    with session() as conn:
        return repo.admin_users(conn, q)


@router.post("/users/{user_id}/suspension")
def suspend_user(user_id: int, payload: SuspensionPayload, request: Request, context: dict = Depends(current_auth)):
    admin = _admin(context)
    _require_csrf(request, context)
    with session() as conn:
        target = repo.user_by_id(conn, user_id)
        if not target:
            raise HTTPException(404, "Utilisateur introuvable.")
        if target["role"] == "admin" and payload.suspended:
            raise HTTPException(409, "Un autre administrateur ne peut pas être suspendu depuis cette interface.")
        repo.set_suspended(conn, user_id, payload.suspended)
        repo.log_admin_action(
            conn, admin["id"], "suspend" if payload.suspended else "reactivate",
            "user", user_id, f"Compte {payload.suspended and 'suspendu' or 'réactivé'}",
        )
    if payload.suspended:
        hub.publish([user_id], {"type": "force_disconnect", "reason": "account_suspended"})
    return {"id": user_id, "suspended": payload.suspended}


@router.get("/reports")
def admin_reports(status: str = "pending", context: dict = Depends(current_auth)):
    _admin(context)
    if status not in {"pending", "resolved", "dismissed"}:
        raise HTTPException(422, "Statut de signalement invalide.")
    with session() as conn:
        return repo.list_reports(conn, status)


@router.post("/reports/{report_id}/resolve")
def resolve_report(report_id: int, payload: ReportResolutionPayload, request: Request, context: dict = Depends(current_auth)):
    admin = _admin(context)
    _require_csrf(request, context)
    with session() as conn:
        reports = repo.list_reports(conn, "pending")
        report = next((item for item in reports if item["id"] == report_id), None)
        if not report:
            raise HTTPException(404, "Signalement introuvable ou déjà traité.")
        repo.resolve_report(conn, report_id, payload.status, payload.note, admin["id"])
        repo.log_admin_action(conn, admin["id"], "resolve_report", "report", report_id, payload.status)
        if payload.status == "resolved" and report["target_type"] == "resource":
            repo.set_resource_status(conn, report["target_id"], "rejected")
        if payload.status == "dismissed" and report["target_type"] == "resource":
            repo.set_resource_status(conn, report["target_id"], "published")
    return {"id": report_id, "status": payload.status}


@router.get("/publication-reports")
def publication_reports(context: dict = Depends(current_auth)):
    _admin(context)
    with session() as conn:
        from aula.db import many
        return many(
            conn,
            """SELECT r.*, u.name AS reporter_name, p.body AS publication_body
               FROM publication_reports r
               JOIN users u ON u.id=r.reporter_id
               JOIN publications p ON p.id=r.publication_id
               WHERE r.status='pending' ORDER BY r.created_at DESC""",
        )


@router.post("/publication-reports/{report_id}/resolve")
def resolve_publication_report(report_id: int, payload: ReportResolutionPayload, request: Request, context: dict = Depends(current_auth)):
    admin = _admin(context)
    _require_csrf(request, context)
    with session() as conn:
        from aula.db import one
        report = one(
            conn,
            "SELECT * FROM publication_reports WHERE id=? AND status='pending'",
            (report_id,),
        )
        if not report:
            raise HTTPException(404, "Signalement introuvable ou déjà traité.")
        conn.execute(
            """UPDATE publication_reports
               SET status=?, admin_note=?, resolved_at=?, resolver_id=? WHERE id=?""",
            (payload.status, payload.note[:500], now(), admin["id"], report_id),
        )
        if payload.status == "resolved":
            conn.execute("UPDATE publications SET status='rejected' WHERE id=?", (report["publication_id"],))
        else:
            conn.execute("UPDATE publications SET status='published' WHERE id=?", (report["publication_id"],))
        repo.log_admin_action(conn, admin["id"], "resolve_publication_report", "publication_report", report_id, payload.status)
    return {"id": report_id, "status": payload.status}


@router.get("/audit")
def admin_audit(context: dict = Depends(current_auth)):
    _admin(context)
    with session() as conn:
        return repo.list_admin_audit(conn)
