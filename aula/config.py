import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("AULA_DATA", ROOT / "data"))
DB_PATH = DATA_DIR / "aula.db"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPOSE_RESET_LINKS = os.environ.get("AULA_EXPOSE_RESET_LINKS", "1") == "1"
AI_API_KEY = os.environ.get("AULA_AI_API_KEY", "").strip()
AI_BASE_URL = os.environ.get("AULA_AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
AI_MODEL = os.environ.get("AULA_AI_MODEL", "gpt-4o-mini")
MAX_UPLOAD = 8 * 1024 * 1024
MAX_AVATAR = 2 * 1024 * 1024
HOST = os.environ.get("AULA_HOST", "127.0.0.1")
PORT = int(os.environ.get("AULA_PORT", "8765"))
SESSION_DAYS = 14

GROUP_COLORS = ["#185744", "#1d4e89", "#8a3f24", "#6d4c1d", "#3f4d3a", "#7a3048"]
DEMO_PASSWORD = "Atlas-2026!"
