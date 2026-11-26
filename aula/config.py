import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("AULA_DATA", ROOT / "data"))
DB_PATH = DATA_DIR / "aula.db"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPOSE_RESET_LINKS = os.environ.get("AULA_EXPOSE_RESET_LINKS", "0").strip().lower() in {
    "1", "true", "yes",
}
SMTP_HOST = os.environ.get("AULA_SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("AULA_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("AULA_SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("AULA_SMTP_PASSWORD", "").strip()
SMTP_FROM = os.environ.get("AULA_SMTP_FROM", SMTP_USER).strip()
SMTP_TLS = os.environ.get("AULA_SMTP_TLS", "1").strip().lower() in {"1", "true", "yes"}
RESET_BASE_URL = os.environ.get("AULA_RESET_BASE_URL", "").strip()


def parse_reset_base_url(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    from urllib.parse import urlsplit
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("AULA_RESET_BASE_URL doit être une URL HTTP(S) valide.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("AULA_RESET_BASE_URL ne doit pas contenir d'identifiants, de requête ni de fragment.")
    if parsed.path not in {"", "/"}:
        raise ValueError("AULA_RESET_BASE_URL ne doit contenir aucun chemin.")
    return value.rstrip("/")


RESET_BASE_URL = parse_reset_base_url(RESET_BASE_URL)


def parse_cors_origins(value: str) -> list[str]:
    origins = [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
    if "*" in origins:
        raise ValueError("AULA_CORS_ORIGINS doit contenir des origines explicites, jamais '*'.")
    return origins


CORS_ORIGINS = parse_cors_origins(os.environ.get("AULA_CORS_ORIGINS", ""))
AI_API_KEY = os.environ.get("AULA_AI_API_KEY", "").strip()
AI_BASE_URL = os.environ.get("AULA_AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
AI_MODEL = os.environ.get("AULA_AI_MODEL", "gpt-4o-mini")
MAX_UPLOAD = 8 * 1024 * 1024
MAX_AVATAR = 2 * 1024 * 1024
HOST = os.environ.get("AULA_HOST", "127.0.0.1")
PORT = int(os.environ.get("AULA_PORT") or os.environ.get("PORT", "8765"))
SESSION_DAYS = 14

GROUP_COLORS = ["#185744", "#1d4e89", "#8a3f24", "#6d4c1d", "#3f4d3a", "#7a3048"]
DEMO_PASSWORD = "Atlas-2026!"
