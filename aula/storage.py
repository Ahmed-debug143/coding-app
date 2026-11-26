import re
import uuid
from pathlib import Path

from aula.config import MAX_AVATAR, MAX_UPLOAD, UPLOAD_DIR
from aula.db import one
from aula.util import now

ALLOWED = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".zip": "application/zip",
}
IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
STORED_RE = re.compile(r"^[a-f0-9]{32}\.[a-z0-9]+$")


def _magic_ok(ext: str, data: bytes) -> bool:
    if ext == ".pdf":
        return data.startswith(b"%PDF")
    if ext == ".png":
        return data.startswith(b"\x89PNG")
    if ext in {".jpg", ".jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if ext == ".gif":
        return data.startswith(b"GIF8")
    if ext == ".webp":
        return data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    if ext == ".zip" or ext in {".docx", ".pptx", ".xlsx"}:
        return data.startswith(b"PK\x03\x04")
    if ext in {".doc", ".ppt", ".xls"}:
        return data.startswith(b"\xd0\xcf\x11\xe0")
    if ext in {".txt", ".md", ".csv"}:
        if b"\x00" in data:
            return False
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return False
        sample = text[:500].lower()
        if "<script" in sample or "<!doctype html" in sample or "<html" in sample:
            return False
        return True
    return False


def safe_stored_path(stored_name: str) -> Path:
    if not STORED_RE.fullmatch(stored_name or ""):
        raise ValueError("Nom de fichier invalide.")
    root = UPLOAD_DIR.resolve()
    path = (root / stored_name).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Chemin refusé.")
    return path


def save_upload(conn, upload, user_id: int, group_id: int | None = None, *, avatar=False):
    if upload is None or not getattr(upload, "filename", None):
        raise ValueError("Aucun fichier reçu.")
    original = re.sub(r"[\x00-\x1f\x7f]", "", Path(upload.filename).name).strip()
    ext = Path(original).suffix.lower()
    if ext not in ALLOWED:
        raise ValueError("Format non autorisé. Utilisez un PDF, une image, un document Office, un texte ou un ZIP.")
    if avatar and ext not in IMAGES:
        raise ValueError("L'avatar doit être une image.")
    limit = MAX_AVATAR if avatar else MAX_UPLOAD
    data = upload.file.read(limit + 1)
    if not data:
        raise ValueError("Le fichier est vide.")
    if len(data) > limit:
        raise ValueError("Le fichier dépasse la taille maximale autorisée.")
    if not _magic_ok(ext, data):
        raise ValueError("Le contenu du fichier ne correspond pas à son format.")
    stored = uuid.uuid4().hex + ext
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = safe_stored_path(stored)
    path.write_bytes(data)
    try:
        cur = conn.execute(
            """INSERT INTO files(uploader_id, group_id, stored_name, original_name, mime, size, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, group_id, stored, original[:180], ALLOWED[ext], len(data), now()),
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return one(conn, "SELECT * FROM files WHERE id = ?", (cur.lastrowid,))


def save_bytes(conn, *, original_name: str, data: bytes, user_id: int, group_id: int | None, mime: str):
    ext = Path(original_name).suffix.lower()
    stored = uuid.uuid4().hex + ext
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_stored_path(stored).write_bytes(data)
    cur = conn.execute(
        """INSERT INTO files(uploader_id, group_id, stored_name, original_name, mime, size, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, group_id, stored, original_name[:180], mime, len(data), now()),
    )
    return one(conn, "SELECT * FROM files WHERE id = ?", (cur.lastrowid,))


def can_read_file(conn, user: dict, file_row: dict) -> bool:
    if not file_row:
        return False
    if user["role"] == "admin" or file_row["uploader_id"] == user["id"]:
        if user["role"] == "admin":
            return True
    if file_row["group_id"]:
        member = one(
            conn,
            "SELECT 1 AS ok FROM group_members WHERE group_id = ? AND user_id = ?",
            (file_row["group_id"], user["id"]),
        )
        if member:
            return True
    resource = one(
        conn,
        "SELECT status, author_id FROM resources WHERE file_id = ? ORDER BY id DESC LIMIT 1",
        (file_row["id"],),
    )
    if resource:
        if resource["status"] == "published":
            return True
        if resource["status"] != "rejected" and resource["author_id"] == user["id"]:
            return True
        if user["role"] == "admin":
            return True
    if user["role"] == "admin" or file_row["uploader_id"] == user["id"]:
        return file_row["group_id"] is None
    avatar = one(conn, "SELECT 1 AS ok FROM users WHERE avatar_file = ?", (file_row["stored_name"],))
    return bool(avatar)
