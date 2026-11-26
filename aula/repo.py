import json

from aula.auth import user_columns
from aula.db import many, one
from aula.util import (
    DEFAULT_PREFS,
    NOTIF_PREF,
    dumps,
    later,
    like,
    loads,
    now,
)

U = user_columns("u")


def user_by_id(conn, user_id: int):
    return one(conn, f"SELECT {user_columns()} FROM users WHERE id = ?", (user_id,))


def user_by_email(conn, email: str):
    return one(conn, f"SELECT {user_columns()} FROM users WHERE email = ?", (email.strip().lower(),))


def update_profile(conn, user_id: int, fields: dict):
    allowed = [
        "name", "bio", "school", "faculty", "filiere", "level", "skills", "interests",
        "project_types", "collab_prefs", "availability", "notif_prefs", "focus_goal", "avatar_file", "email_verified",
        "discoverable",
    ]
    sets, params = [], []
    for key in allowed:
        if key in fields:
            value = fields[key]
            if key in ("skills", "interests", "project_types", "collab_prefs", "notif_prefs") and not isinstance(value, str):
                value = dumps(value)
            sets.append(f"{key} = ?")
            params.append(value)
    if not sets:
        return user_by_id(conn, user_id)
    params.append(user_id)
    conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", params)
    return user_by_id(conn, user_id)


def set_swept(conn, user_id: int):
    conn.execute("UPDATE users SET swept_at = ? WHERE id = ?", (now(), user_id))


def member_ids(conn, group_id: int) -> list[int]:
    return [row["user_id"] for row in many(conn, "SELECT user_id FROM group_members WHERE group_id = ?", (group_id,))]


def peers(conn, user_id: int) -> list[int]:
    rows = many(
        conn,
        """SELECT DISTINCT m2.user_id AS user_id
           FROM group_members m1
           JOIN group_members m2 ON m1.group_id = m2.group_id
           WHERE m1.user_id = ? AND m2.user_id != ?""",
        (user_id, user_id),
    )
    return [row["user_id"] for row in rows]


def log_activity(conn, *, group_id, actor_id, kind, summary, href="", created_at=None):
    conn.execute(
        """INSERT INTO activity(group_id, actor_id, kind, summary, href, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (group_id, actor_id, kind, summary[:240], href, created_at or now()),
    )


def list_activity(conn, group_id: int | None, limit: int = 20):
    if group_id is None:
        return many(
            conn,
            f"""SELECT a.*, u.name AS actor_name FROM activity a
                LEFT JOIN users u ON u.id = a.actor_id
                ORDER BY a.id DESC LIMIT ?""",
            (limit,),
        )
    return many(
        conn,
        f"""SELECT a.*, u.name AS actor_name FROM activity a
            LEFT JOIN users u ON u.id = a.actor_id
            WHERE a.group_id = ? ORDER BY a.id DESC LIMIT ?""",
        (group_id, limit),
    )


def prefs_of(user: dict) -> dict:
    data = loads(user.get("notif_prefs"), {})
    merged = dict(DEFAULT_PREFS)
    if isinstance(data, dict):
        for key in DEFAULT_PREFS:
            if key in data:
                merged[key] = bool(data[key])
    return merged


def notify(conn, *, user_id, kind, title, body="", href="", dedupe_key=None, actor_id=None):
    if actor_id and actor_id == user_id:
        return None
    user = user_by_id(conn, user_id)
    if not user or user["suspended"]:
        return None
    pref = NOTIF_PREF.get(kind)
    if pref and not prefs_of(user).get(pref, True):
        return None
    stamp = now()
    if dedupe_key:
        existing = one(
            conn,
            "SELECT id FROM notifications WHERE user_id = ? AND dedupe_key = ?",
            (user_id, dedupe_key),
        )
        if existing:
            conn.execute(
                """UPDATE notifications
                   SET kind = ?, title = ?, body = ?, href = ?, read_at = NULL, created_at = ?
                   WHERE id = ?""",
                (kind, title[:140], body[:400], href, stamp, existing["id"]),
            )
            return existing["id"]
    cur = conn.execute(
        """INSERT INTO notifications(user_id, kind, title, body, href, dedupe_key, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, kind, title[:140], body[:400], href, dedupe_key, stamp),
    )
    return cur.lastrowid


def unread_count(conn, user_id: int) -> int:
    row = one(
        conn,
        "SELECT COUNT(*) AS c FROM notifications WHERE user_id = ? AND read_at IS NULL",
        (user_id,),
    )
    return row["c"] if row else 0


def list_notifications(conn, user_id: int, limit: int = 40):
    return many(
        conn,
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
        (user_id, limit),
    )


def mark_notification(conn, user_id: int, notif_id: int):
    conn.execute(
        "UPDATE notifications SET read_at = ? WHERE id = ? AND user_id = ? AND read_at IS NULL",
        (now(), notif_id, user_id),
    )


def mark_all_notifications(conn, user_id: int):
    conn.execute(
        "UPDATE notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL",
        (now(), user_id),
    )


def delete_notification(conn, user_id: int, notification_id: int) -> bool:
    cur = conn.execute(
        "DELETE FROM notifications WHERE id = ? AND user_id = ?",
        (notification_id, user_id),
    )
    return cur.rowcount > 0


def sweep_deadlines(conn, user: dict):
    if user.get("swept_at") and user["swept_at"] > later(hours=-6):
        return
    soon = later(hours=24)
    current = now()
    tasks = many(
        conn,
        """SELECT t.*, g.name AS group_name FROM tasks t
           JOIN task_assignees ta ON ta.task_id = t.id
           JOIN groupes g ON g.id = t.group_id
           WHERE ta.user_id = ? AND t.status != 'done' AND t.due_at IS NOT NULL AND t.due_at <= ?""",
        (user["id"], soon),
    )
    for task in tasks:
        overdue = task["due_at"] < current
        notify(
            conn,
            user_id=user["id"],
            kind="overdue" if overdue else "due_soon",
            title="Échéance dépassée" if overdue else "Échéance proche",
            body=f"{task['title']} · {task['group_name']}",
            href=f"/app/groupes/{task['group_id']}?onglet=taches&tache={task['id']}",
            dedupe_key=f"{'overdue' if overdue else 'due'}:{task['id']}:{task['due_at'][:10]}",
        )
    events = many(
        conn,
        """SELECT e.*, g.name AS group_name FROM events e
           LEFT JOIN groupes g ON g.id = e.group_id
           WHERE e.starts_at > ? AND e.starts_at <= ?
             AND (
               e.created_by = ?
               OR e.group_id IN (SELECT group_id FROM group_members WHERE user_id = ?)
             )""",
        (current, soon, user["id"], user["id"]),
    )
    for event in events:
        notify(
            conn,
            user_id=user["id"],
            kind="event",
            title="Événement à venir",
            body=event["title"],
            href="/app/calendrier",
            dedupe_key=f"event:{event['id']}:{event['starts_at'][:10]}",
        )
    set_swept(conn, user["id"])


def find_connection(conn, a: int, b: int):
    return one(
        conn,
        """SELECT * FROM connections
           WHERE (requester_id = ? AND addressee_id = ?)
              OR (requester_id = ? AND addressee_id = ?)""",
        (a, b, b, a),
    )


def list_connections(conn, user_id: int, status: str | None = None):
    sql = f"""SELECT c.*, {U}
              FROM connections c
              JOIN users u ON u.id = CASE WHEN c.requester_id = ? THEN c.addressee_id ELSE c.requester_id END
              WHERE (c.requester_id = ? OR c.addressee_id = ?)"""
    params: list = [user_id, user_id, user_id]
    if status:
        sql += " AND c.status = ?"
        params.append(status)
    sql += " ORDER BY c.updated_at DESC"
    return many(conn, sql, params)


def request_connection(conn, requester_id: int, addressee_id: int):
    if requester_id == addressee_id:
        raise ValueError("Vous ne pouvez pas vous connecter à vous-même.")
    other = user_by_id(conn, addressee_id)
    if not other or other["suspended"] or other["role"] != "student":
        raise ValueError("Étudiant introuvable.")
    row = find_connection(conn, requester_id, addressee_id)
    stamp = now()
    if row and row["status"] == "blocked":
        raise ValueError("Cette mise en relation n'est pas disponible.")
    if row and row["status"] == "accepted":
        raise ValueError("Vous êtes déjà en lien.")
    if row and row["status"] == "pending":
        if row["requester_id"] == addressee_id:
            conn.execute(
                "UPDATE connections SET status = 'accepted', updated_at = ? WHERE id = ?",
                (stamp, row["id"]),
            )
            return "accepted"
        raise ValueError("Une demande est déjà en attente.")
    if row:
        conn.execute(
            """UPDATE connections
               SET requester_id = ?, addressee_id = ?, status = 'pending', blocked_by = NULL, updated_at = ?
               WHERE id = ?""",
            (requester_id, addressee_id, stamp, row["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO connections(requester_id, addressee_id, status, created_at, updated_at)
               VALUES (?, ?, 'pending', ?, ?)""",
            (requester_id, addressee_id, stamp, stamp),
        )
    return "pending"


def respond_connection(conn, user_id: int, other_id: int, accept: bool):
    row = find_connection(conn, user_id, other_id)
    if not row or row["status"] != "pending" or row["addressee_id"] != user_id:
        raise ValueError("Aucune demande à traiter.")
    conn.execute(
        "UPDATE connections SET status = ?, updated_at = ? WHERE id = ?",
        ("accepted" if accept else "declined", now(), row["id"]),
    )


def remove_connection(conn, user_id: int, other_id: int):
    row = find_connection(conn, user_id, other_id)
    if not row:
        return
    if row["status"] == "blocked" and row.get("blocked_by") not in (None, user_id):
        raise ValueError("Vous ne pouvez pas retirer ce blocage.")
    conn.execute("DELETE FROM connections WHERE id = ?", (row["id"],))


def block_user(conn, user_id: int, other_id: int):
    if user_id == other_id:
        raise ValueError("Action impossible.")
    row = find_connection(conn, user_id, other_id)
    stamp = now()
    if row:
        conn.execute(
            "UPDATE connections SET status = 'blocked', blocked_by = ?, updated_at = ? WHERE id = ?",
            (user_id, stamp, row["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO connections(requester_id, addressee_id, status, blocked_by, created_at, updated_at)
               VALUES (?, ?, 'blocked', ?, ?, ?)""",
            (user_id, other_id, user_id, stamp, stamp),
        )


def create_report(conn, *, reporter_id, target_type, target_id, reason):
    reason = (reason or "").strip()
    if len(reason) < 8:
        raise ValueError("Décrivez le signalement en quelques mots.")
    if target_type not in {"user", "group", "resource", "message"}:
        raise ValueError("Cible invalide.")
    conn.execute(
        """INSERT INTO reports(reporter_id, target_type, target_id, reason, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (reporter_id, target_type, target_id, reason[:1000], now()),
    )
    if target_type == "resource":
        conn.execute(
            "UPDATE resources SET status = 'reported' WHERE id = ? AND status = 'published'",
            (target_id,),
        )


def create_group(conn, owner: dict, data: dict, *, is_demo=0, created_at=None):
    stamp = created_at or now()
    cur = conn.execute(
        """INSERT INTO groupes (
            name, description, filiere, subject, project_name, objective, max_members,
            skills_wanted, visibility, deadline, color, owner_id, is_demo, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["name"].strip()[:80],
            data.get("description", "")[:2000],
            data.get("filiere", "")[:80],
            data.get("subject", "")[:80],
            data.get("project_name", "")[:120],
            data.get("objective", "")[:2000],
            max(2, min(int(data.get("max_members") or 8), 40)),
            dumps(data.get("skills_wanted") or []),
            data.get("visibility") if data.get("visibility") in ("public", "private") else "public",
            data.get("deadline") or None,
            data.get("color") or "#185744",
            owner["id"],
            1 if is_demo else 0,
            stamp,
        ),
    )
    group_id = cur.lastrowid
    conn.execute(
        "INSERT INTO group_members(group_id, user_id, role, joined_at) VALUES (?, ?, 'owner', ?)",
        (group_id, owner["id"], stamp),
    )
    return one(conn, "SELECT * FROM groupes WHERE id = ?", (group_id,))


def update_group(conn, group_id: int, data: dict):
    conn.execute(
        """UPDATE groupes SET name=?, description=?, filiere=?, subject=?, project_name=?,
           objective=?, max_members=?, skills_wanted=?, visibility=?, deadline=?, color=?
           WHERE id=?""",
        (
            data["name"].strip()[:80],
            data.get("description", "")[:2000],
            data.get("filiere", "")[:80],
            data.get("subject", "")[:80],
            data.get("project_name", "")[:120],
            data.get("objective", "")[:2000],
            max(2, min(int(data.get("max_members") or 8), 40)),
            dumps(data.get("skills_wanted") or []),
            "private" if data.get("visibility") == "private" else "public",
            data.get("deadline") or None,
            data.get("color") or "#185744",
            group_id,
        ),
    )
    return one(conn, "SELECT * FROM groupes WHERE id = ?", (group_id,))


def delete_group(conn, group_id: int):
    conn.execute("DELETE FROM groupes WHERE id = ?", (group_id,))


def get_group(conn, group_id: int):
    return one(conn, "SELECT * FROM groupes WHERE id = ?", (group_id,))


def list_groups(conn, user_id: int, filters: dict | None = None):
    filters = filters or {}
    sql = """SELECT g.*,
             (SELECT COUNT(*) FROM group_members gm WHERE gm.group_id = g.id) AS member_count,
             EXISTS(SELECT 1 FROM group_members gm WHERE gm.group_id = g.id AND gm.user_id = ?) AS joined
             FROM groupes g
             WHERE (g.visibility = 'public' OR EXISTS(
               SELECT 1 FROM group_members gm WHERE gm.group_id = g.id AND gm.user_id = ?))"""
    params: list = [user_id, user_id]
    if filters.get("q"):
        sql += " AND (g.name LIKE ? ESCAPE '\\' OR g.project_name LIKE ? ESCAPE '\\' OR g.description LIKE ? ESCAPE '\\' OR g.subject LIKE ? ESCAPE '\\')"
        token = like(filters["q"].strip())
        params.extend([token, token, token, token])
    if filters.get("filiere"):
        sql += " AND g.filiere LIKE ? ESCAPE '\\'"
        params.append(like(filters["filiere"].strip()))
    if filters.get("subject"):
        sql += " AND g.subject LIKE ? ESCAPE '\\'"
        params.append(like(filters["subject"].strip()))
    if filters.get("preferred_level"):
        sql += " AND g.preferred_level = ?"
        params.append(filters["preferred_level"].strip())
    if filters.get("skill"):
        sql += " AND lower(g.skills_wanted) LIKE ? ESCAPE '\\'"
        params.append(like(filters["skill"].strip().lower()))
    if filters.get("recruiting") is True:
        sql += " AND g.recruitment_open = 1"
    elif filters.get("recruiting") is False:
        sql += " AND g.recruitment_open = 0"
    if filters.get("mine"):
        sql += " AND EXISTS(SELECT 1 FROM group_members gm WHERE gm.group_id = g.id AND gm.user_id = ?)"
        params.append(user_id)
    sql += " ORDER BY joined DESC, g.created_at DESC LIMIT 60"
    return many(conn, sql, params)


def my_groups(conn, user_id: int):
    return many(
        conn,
        """SELECT g.*, gm.role AS member_role,
                  (SELECT COUNT(*) FROM group_members x WHERE x.group_id = g.id) AS member_count
           FROM group_members gm JOIN groupes g ON g.id = gm.group_id
           WHERE gm.user_id = ? ORDER BY g.name""",
        (user_id,),
    )


def members_of(conn, group_id: int):
    return many(
        conn,
        f"""SELECT {U}, gm.role AS member_role, gm.joined_at
            FROM group_members gm JOIN users u ON u.id = gm.user_id
            WHERE gm.group_id = ?
            ORDER BY CASE gm.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END, u.name""",
        (group_id,),
    )


def count_members(conn, group_id: int) -> int:
    return one(conn, "SELECT COUNT(*) AS c FROM group_members WHERE group_id = ?", (group_id,))["c"]


def add_member(conn, group_id: int, user_id: int, role: str = "member", joined_at=None):
    conn.execute(
        """INSERT INTO group_members(group_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)
           ON CONFLICT(group_id, user_id) DO UPDATE SET role = excluded.role""",
        (group_id, user_id, role, joined_at or now()),
    )


def set_member_role(conn, group_id: int, user_id: int, role: str):
    conn.execute(
        "UPDATE group_members SET role = ? WHERE group_id = ? AND user_id = ?",
        (role, group_id, user_id),
    )


def remove_member(conn, group_id: int, user_id: int):
    conn.execute("DELETE FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user_id))


def invite(conn, group_id: int, inviter_id: int, invitee_id: int):
    if one(conn, "SELECT 1 AS ok FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, invitee_id)):
        raise ValueError("Cette personne fait déjà partie du groupe.")
    stamp = now()
    existing = one(
        conn,
        "SELECT * FROM invitations WHERE group_id = ? AND invitee_id = ?",
        (group_id, invitee_id),
    )
    if existing:
        if existing["status"] == "pending":
            raise ValueError("Une invitation est déjà en attente pour cette personne.")
        conn.execute(
            "UPDATE invitations SET status = 'pending', inviter_id = ?, created_at = ? WHERE id = ?",
            (inviter_id, stamp, existing["id"]),
        )
        return existing["id"]
    cur = conn.execute(
        """INSERT INTO invitations(group_id, inviter_id, invitee_id, status, created_at)
           VALUES (?, ?, ?, 'pending', ?)""",
        (group_id, inviter_id, invitee_id, stamp),
    )
    return cur.lastrowid


def pending_invitations(conn, user_id: int):
    return many(
        conn,
        """SELECT i.*, g.name AS group_name, g.project_name, u.name AS inviter_name
           FROM invitations i
           JOIN groupes g ON g.id = i.group_id
           JOIN users u ON u.id = i.inviter_id
           WHERE i.invitee_id = ? AND i.status = 'pending'
           ORDER BY i.created_at DESC""",
        (user_id,),
    )


def group_invitations(conn, group_id: int):
    return many(
        conn,
        f"""SELECT i.*, {U}
            FROM invitations i JOIN users u ON u.id = i.invitee_id
            WHERE i.group_id = ? AND i.status = 'pending' ORDER BY i.created_at DESC""",
        (group_id,),
    )


def get_invitation(conn, invitation_id: int):
    return one(conn, "SELECT * FROM invitations WHERE id = ?", (invitation_id,))


def set_invitation_status(conn, invitation_id: int, status: str):
    conn.execute("UPDATE invitations SET status = ? WHERE id = ?", (status, invitation_id))


def upsert_join_request(conn, group_id: int, user_id: int, message: str):
    if one(conn, "SELECT 1 AS ok FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user_id)):
        raise ValueError("Vous faites déjà partie de ce groupe.")
    stamp = now()
    existing = one(conn, "SELECT * FROM join_requests WHERE group_id = ? AND user_id = ?", (group_id, user_id))
    if existing and existing["status"] == "pending":
        raise ValueError("Votre demande est déjà en attente.")
    if existing:
        conn.execute(
            "UPDATE join_requests SET status = 'pending', message = ?, created_at = ? WHERE id = ?",
            (message[:500], stamp, existing["id"]),
        )
        return existing["id"]
    cur = conn.execute(
        """INSERT INTO join_requests(group_id, user_id, message, status, created_at)
           VALUES (?, ?, ?, 'pending', ?)""",
        (group_id, user_id, message[:500], stamp),
    )
    return cur.lastrowid


def join_requests_for(conn, group_id: int):
    return many(
        conn,
        f"""SELECT r.*, {U}
            FROM join_requests r JOIN users u ON u.id = r.user_id
            WHERE r.group_id = ? AND r.status = 'pending' ORDER BY r.created_at""",
        (group_id,),
    )


def get_join_request(conn, request_id: int):
    return one(conn, "SELECT * FROM join_requests WHERE id = ?", (request_id,))


def set_join_status(conn, request_id: int, status: str):
    conn.execute("UPDATE join_requests SET status = ? WHERE id = ?", (status, request_id))


def create_message(conn, *, user_id, body, group_id=None, dm_low=None, dm_high=None, reply_to=None, file_id=None, created_at=None):
    cur = conn.execute(
        """INSERT INTO messages(group_id, dm_low, dm_high, user_id, body, reply_to, file_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (group_id, dm_low, dm_high, user_id, body[:4000], reply_to, file_id, created_at or now()),
    )
    return cur.lastrowid


def get_message(conn, message_id: int):
    return one(conn, "SELECT * FROM messages WHERE id = ?", (message_id,))


def update_message_body(conn, message_id: int, body: str):
    conn.execute(
        "UPDATE messages SET body = ?, edited_at = ? WHERE id = ?",
        (body[:4000], now(), message_id),
    )


def soft_delete_message(conn, message_id: int):
    conn.execute(
        "UPDATE messages SET deleted_at = ?, body = '', pinned = 0 WHERE id = ?",
        (now(), message_id),
    )


def toggle_reaction(conn, message_id: int, user_id: int, emoji: str) -> bool:
    existing = one(
        conn,
        "SELECT 1 AS ok FROM reactions WHERE message_id = ? AND user_id = ? AND emoji = ?",
        (message_id, user_id, emoji),
    )
    if existing:
        conn.execute(
            "DELETE FROM reactions WHERE message_id = ? AND user_id = ? AND emoji = ?",
            (message_id, user_id, emoji),
        )
        return False
    conn.execute(
        "INSERT INTO reactions(message_id, user_id, emoji) VALUES (?, ?, ?)",
        (message_id, user_id, emoji),
    )
    return True


def set_pinned(conn, message_id: int, pinned: bool):
    conn.execute("UPDATE messages SET pinned = ? WHERE id = ?", (1 if pinned else 0, message_id))


def list_messages(conn, *, group_id=None, dm_low=None, dm_high=None, before=None, query="", limit=40):
    where = ["deleted_at IS NULL OR deleted_at IS NOT NULL"]
    params: list = []
    if group_id is not None:
        where = ["group_id = ?"]
        params.append(group_id)
    else:
        where = ["dm_low = ? AND dm_high = ?"]
        params.extend([dm_low, dm_high])
    if before:
        where.append("id < ?")
        params.append(before)
    if query.strip():
        where.append("deleted_at IS NULL AND body LIKE ? ESCAPE '\\'")
        params.append(like(query.strip()))
    params.append(limit + 1)
    rows = many(
        conn,
        f"""SELECT * FROM messages WHERE {' AND '.join(where)}
            ORDER BY id DESC LIMIT ?""",
        params,
    )
    has_more = len(rows) > limit
    rows = list(reversed(rows[:limit]))
    return rows, has_more


def pinned_messages(conn, *, group_id=None, dm_low=None, dm_high=None):
    if group_id is not None:
        return many(
            conn,
            "SELECT * FROM messages WHERE group_id = ? AND pinned = 1 AND deleted_at IS NULL ORDER BY id DESC",
            (group_id,),
        )
    return many(
        conn,
        """SELECT * FROM messages WHERE dm_low = ? AND dm_high = ? AND pinned = 1 AND deleted_at IS NULL
           ORDER BY id DESC""",
        (dm_low, dm_high),
    )


def mark_read(conn, user_id: int, scope: str, message_id: int):
    conn.execute(
        """INSERT INTO reads(user_id, scope, last_read_id) VALUES (?, ?, ?)
           ON CONFLICT(user_id, scope) DO UPDATE SET last_read_id = MAX(last_read_id, excluded.last_read_id)""",
        (user_id, scope, message_id),
    )


def last_read(conn, user_id: int, scope: str) -> int:
    row = one(conn, "SELECT last_read_id FROM reads WHERE user_id = ? AND scope = ?", (user_id, scope))
    return row["last_read_id"] if row else 0


def scope_unread(conn, user_id: int, scope: str, *, group_id=None, dm_low=None, dm_high=None) -> int:
    cursor = last_read(conn, user_id, scope)
    if group_id is not None:
        row = one(
            conn,
            """SELECT COUNT(*) AS c FROM messages
               WHERE group_id = ? AND deleted_at IS NULL AND user_id != ? AND id > ?""",
            (group_id, user_id, cursor),
        )
    else:
        row = one(
            conn,
            """SELECT COUNT(*) AS c FROM messages
               WHERE dm_low = ? AND dm_high = ? AND deleted_at IS NULL AND user_id != ? AND id > ?""",
            (dm_low, dm_high, user_id, cursor),
        )
    return row["c"] if row else 0


def conversations(conn, user_id: int):
    groups = many(
        conn,
        """SELECT g.id, g.name, g.color,
                  (SELECT body FROM messages m WHERE m.group_id = g.id AND m.deleted_at IS NULL ORDER BY m.id DESC LIMIT 1) AS last_body,
                  (SELECT created_at FROM messages m WHERE m.group_id = g.id ORDER BY m.id DESC LIMIT 1) AS last_at,
                  (SELECT id FROM messages m WHERE m.group_id = g.id ORDER BY m.id DESC LIMIT 1) AS last_id
           FROM group_members gm JOIN groupes g ON g.id = gm.group_id
           WHERE gm.user_id = ?""",
        (user_id,),
    )
    items = []
    for group in groups:
        scope = f"g:{group['id']}"
        items.append({
            "kind": "group",
            "id": group["id"],
            "title": group["name"],
            "color": group["color"],
            "last_body": group["last_body"] or "",
            "last_at": group["last_at"] or "",
            "href": f"/app/messages/g/{group['id']}",
            "unread": scope_unread(conn, user_id, scope, group_id=group["id"]),
        })
    dms = many(
        conn,
        f"""SELECT {U},
                  (SELECT body FROM messages m
                    WHERE m.dm_low = CASE WHEN u.id < ? THEN u.id ELSE ? END
                      AND m.dm_high = CASE WHEN u.id < ? THEN ? ELSE u.id END
                      AND m.deleted_at IS NULL
                    ORDER BY m.id DESC LIMIT 1) AS last_body,
                  (SELECT created_at FROM messages m
                    WHERE m.dm_low = CASE WHEN u.id < ? THEN u.id ELSE ? END
                      AND m.dm_high = CASE WHEN u.id < ? THEN ? ELSE u.id END
                    ORDER BY m.id DESC LIMIT 1) AS last_at
           FROM users u
           WHERE EXISTS (
             SELECT 1 FROM messages m
             WHERE ((m.dm_low = u.id AND m.dm_high = ?) OR (m.dm_high = u.id AND m.dm_low = ?))
           )""",
        (user_id, user_id, user_id, user_id, user_id, user_id, user_id, user_id, user_id, user_id),
    )
    for person in dms:
        low, high = sorted((user_id, person["id"]))
        items.append({
            "kind": "dm",
            "id": person["id"],
            "title": person["name"],
            "color": "#1d4e89",
            "last_body": person["last_body"] or "",
            "last_at": person["last_at"] or "",
            "href": f"/app/messages/d/{person['id']}",
            "unread": scope_unread(conn, user_id, f"d:{low}:{high}", dm_low=low, dm_high=high),
            "is_demo": person["is_demo"],
        })
    items.sort(key=lambda item: item["last_at"] or "", reverse=True)
    return items


def create_task(conn, *, group_id, title, description, status, priority, due_at, created_by, source_message_id=None, created_at=None, starts_at=None, estimate_hours=None):
    stamp = created_at or now()
    cur = conn.execute(
        """INSERT INTO tasks(group_id, title, description, status, priority, due_at, created_by, source_message_id, created_at, updated_at, starts_at, estimate_hours)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (group_id, title[:140], description[:4000], status, priority, due_at, created_by, source_message_id, stamp, stamp, starts_at, estimate_hours),
    )
    return cur.lastrowid


def set_assignees(conn, task_id: int, user_ids: list[int]):
    conn.execute("DELETE FROM task_assignees WHERE task_id = ?", (task_id,))
    for user_id in dict.fromkeys(user_ids):
        conn.execute("INSERT INTO task_assignees(task_id, user_id) VALUES (?, ?)", (task_id, user_id))


def get_task(conn, task_id: int):
    return one(conn, "SELECT * FROM tasks WHERE id = ?", (task_id,))


def update_task(conn, task_id: int, fields: dict):
    allowed = ["title", "description", "status", "priority", "due_at", "starts_at", "estimate_hours"]
    sets, params = [], []
    for key in allowed:
        if key in fields:
            sets.append(f"{key} = ?")
            params.append(fields[key])
    sets.append("updated_at = ?")
    params.append(now())
    params.append(task_id)
    conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", params)


def delete_task(conn, task_id: int):
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


def task_assignee_ids(conn, task_id: int) -> list[int]:
    return [row["user_id"] for row in many(conn, "SELECT user_id FROM task_assignees WHERE task_id = ?", (task_id,))]


def assignees_map(conn, task_ids: list[int]):
    if not task_ids:
        return {}
    marks = ",".join("?" for _ in task_ids)
    rows = many(
        conn,
        f"""SELECT ta.task_id, u.id, u.name, u.is_demo, u.avatar_file
            FROM task_assignees ta JOIN users u ON u.id = ta.user_id
            WHERE ta.task_id IN ({marks}) ORDER BY u.name""",
        task_ids,
    )
    grouped: dict[int, list] = {}
    for row in rows:
        grouped.setdefault(row["task_id"], []).append(row)
    return grouped


def list_tasks(conn, group_id: int, filters: dict | None = None):
    filters = filters or {}
    sql = "SELECT * FROM tasks WHERE group_id = ?"
    params: list = [group_id]
    if filters.get("status") in {"todo", "doing", "review", "done"}:
        sql += " AND status = ?"
        params.append(filters["status"])
    if filters.get("q"):
        sql += " AND (title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')"
        token = like(filters["q"].strip())
        params.extend([token, token])
    if filters.get("late"):
        sql += " AND status != 'done' AND due_at IS NOT NULL AND due_at < ?"
        params.append(now())
    if filters.get("assignee"):
        sql += " AND id IN (SELECT task_id FROM task_assignees WHERE user_id = ?)"
        params.append(filters["assignee"])
    if filters.get("priority") in {"low", "normal", "high", "urgent"}:
        sql += " AND priority = ?"
        params.append(filters["priority"])
    sort = filters.get("sort")
    ordering = {
        "due_asc": "COALESCE(due_at, '9999'), id",
        "due_desc": "COALESCE(due_at, '' ) DESC, id DESC",
        "created_asc": "created_at, id",
        "created_desc": "created_at DESC, id DESC",
    }.get(sort, "CASE status WHEN 'doing' THEN 0 WHEN 'review' THEN 1 WHEN 'todo' THEN 2 ELSE 3 END, COALESCE(due_at, '9999'), id")
    sql += " ORDER BY " + ordering
    tasks = many(conn, sql, params)
    grouped = assignees_map(conn, [task["id"] for task in tasks])
    for task in tasks:
        task["assignees"] = grouped.get(task["id"], [])
    return tasks


def my_tasks(conn, user_id: int, *, late=False, open_only=False):
    sql = """SELECT t.*, g.name AS group_name FROM tasks t
             JOIN task_assignees ta ON ta.task_id = t.id
             JOIN groupes g ON g.id = t.group_id
             WHERE ta.user_id = ?
               AND EXISTS (SELECT 1 FROM group_members gm WHERE gm.group_id = t.group_id AND gm.user_id = ?)"""
    params: list = [user_id, user_id]
    if open_only:
        sql += " AND t.status != 'done'"
    if late:
        sql += " AND t.status != 'done' AND t.due_at IS NOT NULL AND t.due_at < ?"
        params.append(now())
    sql += " ORDER BY COALESCE(t.due_at, '9999'), t.id"
    return many(conn, sql, params)


def add_comment(conn, task_id: int, user_id: int, body: str):
    cur = conn.execute(
        "INSERT INTO task_comments(task_id, user_id, body, created_at) VALUES (?, ?, ?, ?)",
        (task_id, user_id, body[:2000], now()),
    )
    return cur.lastrowid


def add_task_history(conn, task_id: int, actor_id: int, action: str, detail: str = ""):
    conn.execute(
        "INSERT INTO task_history(task_id, actor_id, action, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (task_id, actor_id, action, detail[:500], now()),
    )


def task_history(conn, task_id: int, limit: int = 40):
    return many(
        conn,
        """SELECT h.id, h.action, h.detail, h.created_at, u.id AS actor_id, u.name AS actor_name
           FROM task_history h JOIN users u ON u.id = h.actor_id
           WHERE h.task_id = ? ORDER BY h.id DESC LIMIT ?""",
        (task_id, limit),
    )


def task_comments(conn, task_id: int):
    return many(
        conn,
        """SELECT c.id, c.body, c.created_at, u.id AS author_id, u.name AS author_name
           FROM task_comments c JOIN users u ON u.id = c.user_id
           WHERE c.task_id = ? ORDER BY c.id""",
        (task_id,),
    )


def comments_for(conn, task_id: int):
    return many(
        conn,
        f"""SELECT c.*, u.name AS author_name, u.is_demo
            FROM task_comments c JOIN users u ON u.id = c.user_id
            WHERE c.task_id = ? ORDER BY c.id""",
        (task_id,),
    )


def attach_file_to_task(conn, task_id: int, file_id: int):
    conn.execute("INSERT OR IGNORE INTO task_files(task_id, file_id) VALUES (?, ?)", (task_id, file_id))


def task_files(conn, task_id: int):
    return many(
        conn,
        """SELECT f.* FROM task_files tf JOIN files f ON f.id = tf.file_id
           WHERE tf.task_id = ? ORDER BY f.id""",
        (task_id,),
    )


def task_by_message(conn, message_id: int):
    return one(conn, "SELECT id FROM tasks WHERE source_message_id = ? ORDER BY id DESC LIMIT 1", (message_id,))


def progress(conn, group_id: int):
    rows = many(conn, "SELECT status, COUNT(*) AS c FROM tasks WHERE group_id = ? GROUP BY status", (group_id,))
    counts = {row["status"]: row["c"] for row in rows}
    total = sum(counts.values())
    done = counts.get("done", 0)
    return {
        "total": total,
        "done": done,
        "todo": counts.get("todo", 0),
        "doing": counts.get("doing", 0),
        "review": counts.get("review", 0),
        "pct": round(100 * done / total) if total else 0,
    }


def workload(conn, group_id: int):
    return many(
        conn,
        """SELECT u.id, u.name, u.is_demo,
                  SUM(CASE WHEN t.id IS NOT NULL AND t.status != 'done' THEN 1 ELSE 0 END) AS open_tasks,
                  SUM(CASE WHEN t.status = 'done' THEN 1 ELSE 0 END) AS done_tasks
           FROM group_members gm
           JOIN users u ON u.id = gm.user_id
           LEFT JOIN task_assignees ta ON ta.user_id = u.id
           LEFT JOIN tasks t ON t.id = ta.task_id AND t.group_id = gm.group_id
           WHERE gm.group_id = ?
           GROUP BY u.id
           ORDER BY open_tasks DESC, u.name""",
        (group_id,),
    )


def create_resource(conn, data: dict):
    cur = conn.execute(
        """INSERT INTO resources(
            author_id, group_id, title, kind, description, subject, filiere, level, tags,
            link_url, file_id, status, is_demo, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'published', ?, ?)""",
        (
            data["author_id"], data.get("group_id"), data["title"][:140], data["kind"],
            data.get("description", "")[:4000], data.get("subject", "")[:80],
            data.get("filiere", "")[:80], data.get("level", "")[:40],
            dumps(data.get("tags") or []), data.get("link_url"), data.get("file_id"),
            1 if data.get("is_demo") else 0, data.get("created_at") or now(),
        ),
    )
    return cur.lastrowid


def list_resources(conn, filters: dict | None = None):
    filters = filters or {}
    sql = f"""SELECT r.*, u.name AS author_name, u.is_demo AS author_demo
              FROM resources r JOIN users u ON u.id = r.author_id
              WHERE r.status = 'published'"""
    params: list = []
    viewer_id = filters.get("viewer_id")
    if viewer_id and not filters.get("admin"):
        sql += """ AND (
            r.group_id IS NULL
            OR EXISTS (
                SELECT 1 FROM group_members gm
                WHERE gm.group_id = r.group_id AND gm.user_id = ?
            )
        )"""
        params.append(viewer_id)
    if filters.get("include_hidden") and filters.get("admin"):
        sql = f"""SELECT r.*, u.name AS author_name, u.is_demo AS author_demo
                  FROM resources r JOIN users u ON u.id = r.author_id WHERE 1=1"""
    if filters.get("q"):
        sql += " AND (r.title LIKE ? ESCAPE '\\' OR r.description LIKE ? ESCAPE '\\' OR r.tags LIKE ? ESCAPE '\\' OR r.subject LIKE ? ESCAPE '\\')"
        token = like(filters["q"].strip())
        params.extend([token, token, token, token])
    if filters.get("kind"):
        sql += " AND r.kind = ?"
        params.append(filters["kind"])
    if filters.get("filiere"):
        sql += " AND r.filiere LIKE ? ESCAPE '\\'"
        params.append(like(filters["filiere"].strip()))
    if filters.get("level"):
        sql += " AND r.level = ?"
        params.append(filters["level"])
    if filters.get("subject"):
        sql += " AND r.subject LIKE ? ESCAPE '\\'"
        params.append(like(filters["subject"].strip()))
    sql += " ORDER BY r.created_at DESC LIMIT 80"
    rows = many(conn, sql, params)
    for row in rows:
        row["tags"] = loads(row["tags"], [])
    return rows


def get_resource(conn, resource_id: int):
    row = one(
        conn,
        f"""SELECT r.*, u.name AS author_name, u.is_demo AS author_demo, u.filiere AS author_filiere
            FROM resources r JOIN users u ON u.id = r.author_id WHERE r.id = ?""",
        (resource_id,),
    )
    if row:
        row["tags"] = loads(row["tags"], [])
    return row


def set_resource_status(conn, resource_id: int, status: str):
    conn.execute("UPDATE resources SET status = ? WHERE id = ?", (status, resource_id))


def increment_download(conn, resource_id: int):
    conn.execute("UPDATE resources SET downloads = downloads + 1 WHERE id = ?", (resource_id,))


def resources_by_author(conn, user_id: int):
    rows = many(
        conn,
        "SELECT * FROM resources WHERE author_id = ? AND status != 'rejected' ORDER BY created_at DESC",
        (user_id,),
    )
    for row in rows:
        row["tags"] = loads(row["tags"], [])
    return rows


def toggle_favorite(conn, user_id: int, target_type: str, target_id: int) -> bool:
    existing = one(
        conn,
        "SELECT 1 AS ok FROM favorites WHERE user_id = ? AND target_type = ? AND target_id = ?",
        (user_id, target_type, target_id),
    )
    if existing:
        conn.execute(
            "DELETE FROM favorites WHERE user_id = ? AND target_type = ? AND target_id = ?",
            (user_id, target_type, target_id),
        )
        return False
    conn.execute(
        "INSERT INTO favorites(user_id, target_type, target_id, created_at) VALUES (?, ?, ?, ?)",
        (user_id, target_type, target_id, now()),
    )
    return True


def is_favorite(conn, user_id: int, target_type: str, target_id: int) -> bool:
    return bool(one(
        conn,
        "SELECT 1 AS ok FROM favorites WHERE user_id = ? AND target_type = ? AND target_id = ?",
        (user_id, target_type, target_id),
    ))


def list_favorites(conn, user_id: int):
    favs = many(conn, "SELECT * FROM favorites WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    items = []
    for fav in favs:
        title, href = None, None
        if fav["target_type"] == "resource":
            row = get_resource(conn, fav["target_id"])
            if row and row["status"] == "published" and (
                not row["group_id"]
                or one(conn, "SELECT 1 AS ok FROM group_members WHERE group_id=? AND user_id=?", (row["group_id"], user_id))
            ):
                title, href = row["title"], f"/app/bibliotheque/{row['id']}"
        elif fav["target_type"] == "group":
            row = get_group(conn, fav["target_id"])
            if row and (row["visibility"] == "public" or one(conn, "SELECT 1 AS ok FROM group_members WHERE group_id=? AND user_id=?", (row["id"], user_id))):
                title, href = row["name"], f"/app/groupes/{row['id']}"
        elif fav["target_type"] == "message":
            row = get_message(conn, fav["target_id"])
            if row and row["group_id"] and one(conn, "SELECT 1 AS ok FROM group_members WHERE group_id=? AND user_id=?", (row["group_id"], user_id)):
                title, href = (row["body"] or "Message")[:80], f"/app/groupes/{row['group_id']}?onglet=discussion"
        if title:
            items.append({"type": fav["target_type"], "id": fav["target_id"], "title": title, "href": href})
    return items


def create_event(conn, data: dict):
    cur = conn.execute(
        """INSERT INTO events(group_id, title, kind, description, starts_at, ends_at, created_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("group_id"), data["title"][:140], data.get("kind") or "reunion",
            data.get("description", "")[:1000], data["starts_at"], data.get("ends_at"),
            data["created_by"], data.get("created_at") or now(),
        ),
    )
    return cur.lastrowid


def delete_event(conn, event_id: int):
    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))


def update_event(conn, event_id: int, data: dict):
    conn.execute(
        """UPDATE events
           SET title=?, kind=?, description=?, starts_at=?, ends_at=?, group_id=?
           WHERE id=?""",
        (
            data["title"][:140],
            data["kind"],
            data.get("description", "")[:1000],
            data["starts_at"],
            data.get("ends_at"),
            data.get("group_id"),
            event_id,
        ),
    )
    return get_event(conn, event_id)


def get_event(conn, event_id: int):
    return one(conn, "SELECT * FROM events WHERE id = ?", (event_id,))


def events_between(conn, user_id: int, start: str, end: str):
    return many(
        conn,
        """SELECT e.*, g.name AS group_name FROM events e
           LEFT JOIN groupes g ON g.id = e.group_id
           WHERE e.starts_at >= ? AND e.starts_at < ?
             AND (e.group_id IS NULL AND e.created_by = ?
                  OR e.group_id IN (SELECT group_id FROM group_members WHERE user_id = ?))
           ORDER BY e.starts_at""",
        (start, end, user_id, user_id),
    )


def deadlines_between(conn, user_id: int, start: str, end: str):
    return many(
        conn,
        """SELECT t.*, g.name AS group_name FROM tasks t
           JOIN groupes g ON g.id = t.group_id
           WHERE t.due_at IS NOT NULL AND t.due_at >= ? AND t.due_at < ?
             AND t.group_id IN (SELECT group_id FROM group_members WHERE user_id = ?)
           ORDER BY t.due_at""",
        (start, end, user_id),
    )


def upcoming(conn, user_id: int, limit: int = 6):
    current = now()
    events = events_between(conn, user_id, current, "9999-12-31T00:00:00")[:limit]
    tasks = many(
        conn,
        """SELECT t.*, g.name AS group_name FROM tasks t
           JOIN groupes g ON g.id = t.group_id
           WHERE t.due_at IS NOT NULL AND t.due_at >= ? AND t.status != 'done'
             AND t.group_id IN (SELECT group_id FROM group_members WHERE user_id = ?)
           ORDER BY t.due_at LIMIT ?""",
        (current[:10], user_id, limit),
    )
    return events, tasks


def search_students(conn, viewer_id: int, filters: dict):
    sql = f"""SELECT {U} FROM users u
              WHERE u.suspended = 0 AND u.role = 'student' AND u.id != ?
                AND NOT EXISTS (
                  SELECT 1 FROM connections c
                  WHERE c.status = 'blocked'
                    AND ((c.requester_id = ? AND c.addressee_id = u.id)
                      OR (c.addressee_id = ? AND c.requester_id = u.id))
                )"""
    params: list = [viewer_id, viewer_id, viewer_id]
    if filters.get("q"):
        token = like(filters["q"].strip())
        sql += " AND (u.name LIKE ? ESCAPE '\\' OR u.filiere LIKE ? ESCAPE '\\' OR u.school LIKE ? ESCAPE '\\' OR u.skills LIKE ? ESCAPE '\\' OR u.interests LIKE ? ESCAPE '\\' OR u.bio LIKE ? ESCAPE '\\')"
        params.extend([token, token, token, token, token, token])
    if filters.get("filiere"):
        sql += " AND u.filiere LIKE ? ESCAPE '\\'"
        params.append(like(filters["filiere"].strip()))
    if filters.get("level"):
        sql += " AND u.level = ?"
        params.append(filters["level"])
    if filters.get("school"):
        sql += " AND u.school LIKE ? ESCAPE '\\'"
        params.append(like(filters["school"].strip()))
    if filters.get("skill"):
        sql += " AND u.skills LIKE ? ESCAPE '\\'"
        params.append(like(filters["skill"].strip()))
    if filters.get("interest"):
        sql += " AND u.interests LIKE ? ESCAPE '\\'"
        params.append(like(filters["interest"].strip()))
    if filters.get("project_type"):
        sql += " AND lower(u.project_types) LIKE ? ESCAPE '\\'"
        params.append(like(filters["project_type"].strip().lower()))
    if filters.get("faculty"):
        sql += " AND u.faculty LIKE ? ESCAPE '\\'"
        params.append(like(filters["faculty"].strip()))
    sql += " AND u.discoverable = 1"
    if filters.get("availability"):
        sql += " AND u.availability LIKE ? ESCAPE '\\'"
        params.append(like(filters["availability"].strip()))
    if filters.get("project"):
        token = like(filters["project"].strip())
        sql += """ AND EXISTS (
            SELECT 1 FROM group_members gm JOIN groupes g ON g.id = gm.group_id
            WHERE gm.user_id = u.id AND (g.name LIKE ? ESCAPE '\\' OR g.project_name LIKE ? ESCAPE '\\')
              AND (g.visibility = 'public' OR EXISTS(SELECT 1 FROM group_members mine WHERE mine.group_id = g.id AND mine.user_id = ?))
        )"""
        params.extend([token, token, viewer_id])
    sql += " ORDER BY u.name LIMIT 40"
    return many(conn, sql, params)


def visible_groups_for_profile(conn, profile_id: int, viewer_id: int):
    return many(
        conn,
        """SELECT g.id, g.name, g.project_name, g.visibility, g.is_demo
           FROM group_members gm JOIN groupes g ON g.id = gm.group_id
           WHERE gm.user_id = ?
             AND (g.visibility = 'public' OR EXISTS(
               SELECT 1 FROM group_members mine WHERE mine.group_id = g.id AND mine.user_id = ?))
           ORDER BY g.name""",
        (profile_id, viewer_id),
    )


def search_all(conn, user: dict, query: str):
    token = like(query.strip())
    people = search_students(conn, user["id"], {"q": query})[:8]
    groups = list_groups(conn, user["id"], {"q": query})[:8]
    tasks = many(
        conn,
        """SELECT t.id, t.title, t.group_id, g.name AS group_name FROM tasks t
           JOIN groupes g ON g.id = t.group_id
           WHERE t.group_id IN (SELECT group_id FROM group_members WHERE user_id = ?)
             AND (t.title LIKE ? ESCAPE '\\' OR t.description LIKE ? ESCAPE '\\')
           ORDER BY t.updated_at DESC LIMIT 8""",
        (user["id"], token, token),
    )
    resources = list_resources(conn, {"q": query, "viewer_id": user["id"], "admin": user["role"] == "admin"})[:8]
    messages = many(
        conn,
        """SELECT m.id, m.body, m.group_id, m.dm_low, m.dm_high, m.created_at, g.name AS group_name
           FROM messages m LEFT JOIN groupes g ON g.id = m.group_id
           WHERE m.deleted_at IS NULL AND m.body LIKE ? ESCAPE '\\'
             AND (
               m.group_id IN (SELECT group_id FROM group_members WHERE user_id = ?)
               OR m.dm_low = ? OR m.dm_high = ?
             )
           ORDER BY m.id DESC LIMIT 8""",
        (token, user["id"], user["id"], user["id"]),
    )
    return {"people": people, "groups": groups, "tasks": tasks, "resources": resources, "messages": messages}


def group_files(conn, group_id: int):
    return many(
        conn,
        f"""SELECT f.*, u.name AS uploader_name
            FROM files f JOIN users u ON u.id = f.uploader_id
            WHERE f.group_id = ? ORDER BY f.id DESC""",
        (group_id,),
    )


def get_file(conn, file_id: int):
    return one(conn, "SELECT * FROM files WHERE id = ?", (file_id,))


def categories(conn):
    return many(conn, "SELECT * FROM categories ORDER BY name")


def add_category(conn, name: str):
    name = name.strip()[:60]
    if len(name) < 2:
        raise ValueError("Nom de catégorie trop court.")
    conn.execute("INSERT INTO categories(name, created_at) VALUES (?, ?)", (name, now()))


def user_stats(conn, user_id: int):
    messages = one(conn, "SELECT COUNT(*) AS c FROM messages WHERE user_id = ? AND deleted_at IS NULL", (user_id,))["c"]
    resources = one(conn, "SELECT COUNT(*) AS c FROM resources WHERE author_id = ? AND status = 'published'", (user_id,))["c"]
    owned = one(conn, "SELECT COUNT(*) AS c FROM groupes WHERE owner_id = ?", (user_id,))["c"]
    done = one(
        conn,
        """SELECT COUNT(*) AS c FROM task_assignees ta
           JOIN tasks t ON t.id = ta.task_id
           WHERE ta.user_id = ? AND t.status = 'done'""",
        (user_id,),
    )["c"]
    finished_project = one(
        conn,
        """SELECT 1 AS ok FROM group_members gm
           WHERE gm.user_id = ?
             AND EXISTS(SELECT 1 FROM tasks t WHERE t.group_id = gm.group_id)
             AND NOT EXISTS(SELECT 1 FROM tasks t WHERE t.group_id = gm.group_id AND t.status != 'done')""",
        (user_id,),
    )
    return {
        "messages": messages,
        "resources": resources,
        "owned": owned,
        "tasks_done": done,
        "finished_project": bool(finished_project),
    }


def badges_for(stats: dict):
    badges = []
    if stats["messages"] >= 8:
        badges.append({"code": "contributeur", "label": "Contributeur", "detail": "Au moins 8 messages utiles dans les espaces du campus."})
    if stats["resources"] >= 1:
        badges.append({"code": "partageur", "label": "Partageur", "detail": "Au moins une ressource publiée dans la bibliothèque."})
    if stats["owned"] >= 1:
        badges.append({"code": "organisateur", "label": "Organisateur", "detail": "A créé un groupe de travail."})
    if stats["tasks_done"] >= 3:
        badges.append({"code": "collaborateur", "label": "Collaborateur", "detail": "Au moins 3 tâches attribuées menées au statut Terminé."})
    if stats["finished_project"]:
        badges.append({"code": "projet", "label": "Projet bouclé", "detail": "Membre d'un groupe dont toutes les tâches sont terminées."})
    return badges


def dashboard(conn, user: dict):
    groups = my_groups(conn, user["id"])
    enriched = []
    for group in groups:
        group = dict(group)
        group["progress"] = progress(conn, group["id"])
        group["unread"] = scope_unread(conn, user["id"], f"g:{group['id']}", group_id=group["id"])
        enriched.append(group)
    tasks = my_tasks(conn, user["id"], open_only=True)
    late = [task for task in tasks if task["due_at"] and task["due_at"] < now()]
    urgent = [task for task in tasks if task["priority"] in ("urgent", "high")]
    events, deadlines = upcoming(conn, user["id"], 5)
    activity = many(
        conn,
        """SELECT a.*, u.name AS actor_name, g.name AS group_name
           FROM activity a
           LEFT JOIN users u ON u.id = a.actor_id
           LEFT JOIN groupes g ON g.id = a.group_id
           WHERE a.group_id IN (SELECT group_id FROM group_members WHERE user_id = ?)
           ORDER BY a.id DESC LIMIT 8""",
        (user["id"],),
    )
    resources = many(
        conn,
        """SELECT r.id, r.title, r.kind, r.created_at, u.name AS author_name
           FROM resources r JOIN users u ON u.id = r.author_id
           WHERE r.status = 'published'
             AND (
               r.group_id IS NULL
               OR EXISTS (
                 SELECT 1 FROM group_members gm
                 WHERE gm.group_id = r.group_id AND gm.user_id = ?
               )
             )
           ORDER BY r.created_at DESC LIMIT 4""",
        (user["id"],),
    )
    return {
        "groups": enriched,
        "tasks": tasks[:6],
        "late": late,
        "urgent": urgent[:6],
        "open_tasks": tasks,
        "events": events,
        "deadlines": deadlines,
        "activity": activity,
        "resources": resources,
        "invitations": pending_invitations(conn, user["id"]),
        "connections": [row for row in list_connections(conn, user["id"], "pending") if row["addressee_id"] == user["id"]],
        "favorites": list_favorites(conn, user["id"])[:4],
        "unread_messages": sum(group["unread"] for group in enriched),
    }


def admin_stats(conn):
    def count(sql):
        return one(conn, sql)["c"]

    week = later(days=-7)
    return {
        "users": count("SELECT COUNT(*) AS c FROM users WHERE role = 'student'"),
        "active": count(f"SELECT COUNT(*) AS c FROM users WHERE last_seen >= '{week}'"),
        "groups": count("SELECT COUNT(*) AS c FROM groupes"),
        "tasks": count("SELECT COUNT(*) AS c FROM tasks"),
        "resources": count("SELECT COUNT(*) AS c FROM resources WHERE status = 'published'"),
        "messages": count("SELECT COUNT(*) AS c FROM messages WHERE deleted_at IS NULL"),
        "reports": (
            count("SELECT COUNT(*) AS c FROM reports WHERE status = 'pending'")
            + count("SELECT COUNT(*) AS c FROM publication_reports WHERE status = 'pending'")
        ),
    }


def admin_users(conn, query: str = ""):
    if query.strip():
        token = like(query.strip())
        return many(
            conn,
            f"""SELECT {user_columns()} FROM users
                WHERE name LIKE ? ESCAPE '\\' OR email LIKE ? ESCAPE '\\'
                ORDER BY created_at DESC LIMIT 80""",
            (token, token),
        )
    return many(conn, f"SELECT {user_columns()} FROM users ORDER BY created_at DESC LIMIT 80")


def set_suspended(conn, user_id: int, suspended: bool):
    conn.execute("UPDATE users SET suspended = ? WHERE id = ?", (1 if suspended else 0, user_id))
    if suspended:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def list_reports(conn, status: str = "pending"):
    return many(
        conn,
        f"""SELECT r.*, u.name AS reporter_name
            FROM reports r JOIN users u ON u.id = r.reporter_id
            WHERE r.status = ? ORDER BY r.created_at DESC""",
        (status,),
    )


def resolve_report(conn, report_id: int, status: str, note: str, resolver_id: int):
    conn.execute(
        """UPDATE reports SET status = ?, admin_note = ?, resolved_at = ?, resolver_id = ?
           WHERE id = ?""",
        (status, note[:500], now(), resolver_id, report_id),
    )


def log_admin_action(conn, actor_id: int, action: str, target_type: str, target_id: int | None = None, detail: str = ""):
    conn.execute(
        """INSERT INTO admin_audit(actor_id, action, target_type, target_id, detail, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (actor_id, action[:80], target_type[:40], target_id, detail[:500], now()),
    )


def list_admin_audit(conn, limit: int = 100):
    return many(
        conn,
        """SELECT a.*, u.name AS actor_name
           FROM admin_audit a JOIN users u ON u.id=a.actor_id
           ORDER BY a.created_at DESC, a.id DESC LIMIT ?""",
        (limit,),
    )


def recent_resources_in_groups(conn, user_id: int):
    return many(
        conn,
        """SELECT f.id, f.original_name, f.created_at, g.name AS group_name, g.id AS group_id
           FROM files f JOIN groupes g ON g.id = f.group_id
           WHERE f.group_id IN (SELECT group_id FROM group_members WHERE user_id = ?)
           ORDER BY f.id DESC LIMIT 5""",
        (user_id,),
    )


def reactions_for(conn, message_ids: list[int], viewer_id: int):
    if not message_ids:
        return {}
    marks = ",".join("?" for _ in message_ids)
    rows = many(
        conn,
        f"SELECT message_id, emoji, user_id FROM reactions WHERE message_id IN ({marks})",
        message_ids,
    )
    grouped: dict[int, dict] = {}
    for row in rows:
        bucket = grouped.setdefault(row["message_id"], {})
        entry = bucket.setdefault(row["emoji"], {"emoji": row["emoji"], "count": 0, "mine": False})
        entry["count"] += 1
        if row["user_id"] == viewer_id:
            entry["mine"] = True
    return {key: list(value.values()) for key, value in grouped.items()}


def message_task_map(conn, message_ids: list[int]):
    if not message_ids:
        return {}
    marks = ",".join("?" for _ in message_ids)
    rows = many(
        conn,
        f"SELECT id, source_message_id FROM tasks WHERE source_message_id IN ({marks})",
        message_ids,
    )
    return {row["source_message_id"]: row["id"] for row in rows}
