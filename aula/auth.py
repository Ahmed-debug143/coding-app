import hashlib
import hmac
import secrets
import time

from aula.config import SESSION_DAYS
from aula.db import one
from aula.util import DEFAULT_PREFS, dumps, later, now, valid_email

USER_COLS = """
id, email, name, avatar_file, bio, school, faculty, filiere, level, skills, interests,
project_types, collab_prefs, availability, notif_prefs, focus_goal, role, suspended, email_verified, is_demo,
last_seen, swept_at, created_at, discoverable
""".strip()

_FAILS: dict[str, list[float]] = {}
_DUMMY = None


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _scheme, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32
        )
        return hmac.compare_digest(digest, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


def _dummy() -> str:
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password("mot-de-passe-factice")
    return _DUMMY


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def allow_attempt(key: str, limit: int = 8, window: int = 600) -> bool:
    stamp = time.time()
    recent = [item for item in _FAILS.get(key, []) if stamp - item < window]
    _FAILS[key] = recent
    return len(recent) < limit


def record_failure(key: str):
    _FAILS.setdefault(key, []).append(time.time())


def clear_failures(key: str):
    _FAILS.pop(key, None)


def create_user(conn, *, email, password, name, role="student", filiere="", level="", school="", is_demo=0, verified=0, **extra):
    email = email.strip().lower()
    if not valid_email(email):
        raise ValueError("Adresse e-mail invalide.")
    if not isinstance(password, str) or not 10 <= len(password) <= 128:
        raise ValueError("Le mot de passe doit contenir entre 10 et 128 caractères.")
    if len(name.strip()) < 2:
        raise ValueError("Indiquez votre nom.")
    prefs = extra.pop("notif_prefs", None) or DEFAULT_PREFS
    conn.execute(
        """INSERT INTO users (
            email, password_hash, name, bio, school, filiere, level, skills, interests,
            availability, notif_prefs, focus_goal, role, email_verified, is_demo, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            email,
            hash_password(password),
            name.strip()[:80],
            extra.get("bio", "")[:2000],
            (school or "")[:120],
            (filiere or "")[:80],
            level or "",
            dumps(extra.get("skills") or []),
            dumps(extra.get("interests") or []),
            extra.get("availability", "")[:200],
            dumps(prefs),
            extra.get("focus_goal", "")[:180],
            role,
            1 if verified else 0,
            1 if is_demo else 0,
            extra.get("created_at") or now(),
        ),
    )
    return one(conn, f"SELECT {USER_COLS} FROM users WHERE email = ?", (email,))


def authenticate(conn, email: str, password: str):
    email = (email or "").strip().lower()
    if not allow_attempt(f"login:{email}"):
        return None, "Trop de tentatives. Réessayez dans quelques minutes."
    row = one(conn, "SELECT * FROM users WHERE email = ?", (email,))
    stored = row["password_hash"] if row else _dummy()
    ok = verify_password(password or "", stored)
    if not row or not ok:
        record_failure(f"login:{email}")
        return None, "Adresse e-mail ou mot de passe incorrect."
    if row["suspended"]:
        return None, "Ce compte est suspendu. Écrivez à l'administration de la plateforme."
    clear_failures(f"login:{email}")
    return open_session(conn, row["id"])


def open_session(conn, user_id: int):
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    conn.execute(
        "INSERT INTO sessions(token_hash, user_id, csrf, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
        (token_hash(token), user_id, csrf, later(days=SESSION_DAYS), now()),
    )
    user = one(conn, f"SELECT {USER_COLS} FROM users WHERE id = ?", (user_id,))
    return {"token": token, "csrf": csrf, "user": user}, None


def user_columns(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return ", ".join(prefix + column.strip() for column in USER_COLS.split(","))


def resolve_session(conn, token: str | None):
    if not token:
        return None
    row = one(
        conn,
        f"""SELECT s.csrf AS csrf, s.expires_at AS expires_at, {user_columns("u")}
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ?""",
        (token_hash(token),),
    )
    if not row:
        return None
    if row["expires_at"] < now() or row["suspended"]:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(token),))
        return None
    if not row["last_seen"] or row["last_seen"] < later(minutes=-2):
        conn.execute("UPDATE users SET last_seen = ? WHERE id = ?", (now(), row["id"]))
        row["last_seen"] = now()
    return row


def destroy_session(conn, token: str | None):
    if token:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(token),))


def destroy_user_sessions(conn, user_id: int):
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def issue_email_token(conn, user_id: int, purpose: str, hours: int = 2) -> str:
    token = secrets.token_urlsafe(24)
    conn.execute("DELETE FROM email_tokens WHERE user_id = ? AND purpose = ?", (user_id, purpose))
    conn.execute(
        "INSERT INTO email_tokens(token_hash, user_id, purpose, expires_at) VALUES (?, ?, ?, ?)",
        (token_hash(token), user_id, purpose, later(hours=hours)),
    )
    return token


def consume_email_token(conn, token: str, purpose: str):
    row = one(
        conn,
        "SELECT * FROM email_tokens WHERE token_hash = ? AND purpose = ?",
        (token_hash(token), purpose),
    )
    if not row or row["used"] or row["expires_at"] < now():
        return None
    conn.execute("UPDATE email_tokens SET used = 1 WHERE token_hash = ?", (token_hash(token),))
    return row["user_id"]


def change_password(conn, user_id: int, current: str, new: str):
    row = one(conn, "SELECT password_hash FROM users WHERE id = ?", (user_id,))
    if not row or not verify_password(current, row["password_hash"]):
        raise ValueError("Le mot de passe actuel est incorrect.")
    if not isinstance(new, str) or not 10 <= len(new) <= 128:
        raise ValueError("Le nouveau mot de passe doit contenir entre 10 et 128 caractères.")
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new), user_id))
    destroy_user_sessions(conn, user_id)


def reset_password(conn, token: str, new_password: str):
    if not isinstance(new_password, str) or not 10 <= len(new_password) <= 128:
        raise ValueError("Le nouveau mot de passe doit contenir entre 10 et 128 caractères.")
    user_id = consume_email_token(conn, token, "reset")
    if not user_id:
        raise ValueError("Ce lien de réinitialisation est invalide ou expiré.")
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new_password), user_id))
    destroy_user_sessions(conn, user_id)
