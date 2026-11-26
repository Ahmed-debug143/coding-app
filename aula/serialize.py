from aula import repo
from aula.util import initials, loads


def present_user(row: dict | None):
    if not row:
        return None
    data = dict(row)
    for secret in ("password_hash", "csrf", "expires_at"):
        data.pop(secret, None)
    data["skills"] = loads(data.get("skills"), [])
    data["interests"] = loads(data.get("interests"), [])
    data["project_types"] = loads(data.get("project_types"), [])
    data["collab_prefs"] = loads(data.get("collab_prefs"), [])
    data["prefs"] = loads(data.get("notif_prefs"), {})
    if not isinstance(data["prefs"], dict):
        data["prefs"] = {}
    data["initials"] = initials(data.get("name") or "")
    return data


def _file(conn, file_id, cache):
    if not file_id:
        return None
    if file_id not in cache:
        row = repo.get_file(conn, file_id)
        cache[file_id] = None if not row else {
            "id": row["id"],
            "name": row["original_name"],
            "mime": row["mime"],
            "size": row["size"],
            "url": f"/api/group-files/{row['id']}" if row.get("group_id") else None,
        }
    return cache[file_id]


def _author(conn, user_id, cache):
    if user_id not in cache:
        row = repo.user_by_id(conn, user_id)
        cache[user_id] = {
            "id": user_id,
            "name": row["name"] if row else "Compte retiré",
            "initials": initials(row["name"]) if row else "?",
            "is_demo": bool(row["is_demo"]) if row else False,
            "avatar": bool(row and row["avatar_file"]),
        }
    return cache[user_id]


def pack_messages(conn, rows: list[dict], viewer_id: int) -> list[dict]:
    if not rows:
        return []
    ids = [row["id"] for row in rows]
    reactions = repo.reactions_for(conn, ids, viewer_id)
    task_map = repo.message_task_map(conn, ids)
    authors: dict = {}
    files: dict = {}
    parents: dict = {}
    packed = []
    for row in rows:
        parent = None
        if row.get("reply_to"):
            if row["reply_to"] not in parents:
                parents[row["reply_to"]] = repo.get_message(conn, row["reply_to"])
            source = parents[row["reply_to"]]
            if source:
                parent = {
                    "id": source["id"],
                    "author": _author(conn, source["user_id"], authors)["name"],
                    "excerpt": "Message supprimé" if source["deleted_at"] else (source["body"] or "Fichier")[:140],
                }
        packed.append({
            "id": row["id"],
            "author": _author(conn, row["user_id"], authors),
            "body": "" if row["deleted_at"] else row["body"],
            "deleted": bool(row["deleted_at"]),
            "reply": parent,
            "file": _file(conn, row.get("file_id"), files),
            "reactions": reactions.get(row["id"], []),
            "pinned": bool(row["pinned"]),
            "task_id": task_map.get(row["id"]),
            "created_at": row["created_at"],
            "edited": bool(row["edited_at"]),
            "mine": row["user_id"] == viewer_id,
            "group_id": row.get("group_id"),
        })
    return packed
