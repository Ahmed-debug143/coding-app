class Denied(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def membership(conn, group_id: int, user_id: int):
    from aula.db import one

    return one(
        conn,
        "SELECT * FROM group_members WHERE group_id = ? AND user_id = ?",
        (group_id, user_id),
    )


def group_or_404(conn, group_id: int, user: dict):
    from aula.db import one

    group = one(conn, "SELECT * FROM groupes WHERE id = ?", (group_id,))
    if not group:
        raise Denied(404, "Groupe introuvable.")
    member = membership(conn, group_id, user["id"])
    if group["visibility"] == "private" and not member and user["role"] != "admin":
        raise Denied(404, "Groupe introuvable.")
    return group, member


def require_collab(conn, group_id: int, user: dict):
    group, member = group_or_404(conn, group_id, user)
    if not member and user["role"] != "admin":
        raise Denied(403, "Les échanges de ce groupe sont réservés aux membres.")
    return group, member


def require_writer(conn, group_id: int, user: dict):
    group, member = group_or_404(conn, group_id, user)
    if not member:
        raise Denied(403, "Rejoignez le groupe pour participer.")
    return group, member


def require_manager(conn, group_id: int, user: dict):
    group, member = require_writer(conn, group_id, user)
    if member["role"] not in ("owner", "admin") and user["role"] != "admin":
        raise Denied(403, "Cette action est réservée aux responsables du groupe.")
    return group, member


def is_blocked(conn, a: int, b: int) -> bool:
    from aula.db import one

    row = one(
        conn,
        """SELECT status FROM connections
           WHERE (requester_id = ? AND addressee_id = ?)
              OR (requester_id = ? AND addressee_id = ?)""",
        (a, b, b, a),
    )
    return bool(row and row["status"] == "blocked")


def share_group(conn, a: int, b: int) -> bool:
    from aula.db import one

    row = one(
        conn,
        """SELECT 1 AS ok FROM group_members m1
           JOIN group_members m2 ON m1.group_id = m2.group_id
           WHERE m1.user_id = ? AND m2.user_id = ?""",
        (a, b),
    )
    return bool(row)


def connection_status(conn, a: int, b: int):
    from aula.db import one

    return one(
        conn,
        """SELECT * FROM connections
           WHERE (requester_id = ? AND addressee_id = ?)
              OR (requester_id = ? AND addressee_id = ?)""",
        (a, b, b, a),
    )


def can_dm(conn, a: int, b: int) -> bool:
    if a == b or is_blocked(conn, a, b):
        return False
    link = connection_status(conn, a, b)
    if link and link["status"] == "accepted":
        return True
    return share_group(conn, a, b)
