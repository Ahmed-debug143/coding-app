import sqlite3
from contextlib import contextmanager
from pathlib import Path

from aula.config import DATA_DIR, DB_PATH, UPLOAD_DIR
from aula.util import now

MIGRATIONS = Path(__file__).resolve().parent / "migrations"
DEFAULT_CATEGORIES = [
    "Cours", "TD", "TP", "Résumé", "Fiche de révision", "Ancien examen",
    "Corrigé", "Document", "Lien", "Vidéo", "Tutoriel",
]


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def one(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def many(conn, sql, params=()):
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def ensure_categories(conn):
    for name in DEFAULT_CATEGORIES:
        conn.execute(
            "INSERT OR IGNORE INTO categories(name, created_at) VALUES (?, ?)",
            (name, now()),
        )


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with session() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )"""
        )
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in applied:
                continue
            conn.executescript(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (path.name, now()),
            )
        ensure_categories(conn)
