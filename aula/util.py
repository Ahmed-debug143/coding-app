import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
MONTHS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MENTION_RE = re.compile(r'@"([^"]{1,80})"|\@([A-Za-zÀ-ÿ][\wÀ-ÿ\'-]{1,40})', re.UNICODE)
WEEKDAYS = {
    "lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3,
    "vendredi": 4, "samedi": 5, "dimanche": 6,
}


def now() -> str:
    return datetime.now(PARIS).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")


def later(*, days: int = 0, hours: int = 0, minutes: int = 0) -> str:
    dt = datetime.now(PARIS) + timedelta(days=days, hours=hours, minutes=minutes)
    return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def pretty(value: str | None) -> str:
    dt = parse_dt(value)
    if not dt:
        return ""
    return f"{dt.day} {MONTHS[dt.month - 1]} {dt.year} à {dt.strftime('%H:%M')}"


def day_label(value: str | None) -> str:
    dt = parse_dt(value) if value and "T" in value else None
    if value and dt is None:
        try:
            dt = datetime.strptime(value[:10], "%Y-%m-%d")
        except ValueError:
            return value or ""
    if not dt:
        return ""
    return f"{dt.day} {MONTHS[dt.month - 1]}"


def ago(value: str | None) -> str:
    dt = parse_dt(value)
    if not dt:
        return ""
    current = datetime.now(PARIS).replace(tzinfo=None, microsecond=0)
    seconds = (current - dt).total_seconds()
    if seconds < 45:
        return "à l'instant"
    if seconds < 3600:
        return f"il y a {int(seconds // 60)} min"
    if seconds < 86400:
        return f"il y a {int(seconds // 3600)} h"
    if seconds < 86400 * 7:
        return f"il y a {int(seconds // 86400)} j"
    return pretty(value)


def initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def loads(value, fallback):
    try:
        data = json.loads(value or "")
    except (json.JSONDecodeError, TypeError):
        return fallback
    return data


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def like(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def split_tags(raw: str) -> list[str]:
    seen = []
    for part in (raw or "").replace(";", ",").split(","):
        item = part.strip()
        if item and item.lower() not in {s.lower() for s in seen}:
            seen.append(item[:40])
        if len(seen) >= 12:
            break
    return seen


def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match((email or "").strip())) and len(email) <= 160


def mentioned_ids(body: str, members: list[dict]) -> list[int]:
    found: list[int] = []
    explicit = []
    for match in MENTION_RE.finditer(body or ""):
        explicit.append((match.group(1) or match.group(2) or "").lower())
    for member in members:
        name = member["name"]
        first = name.split()[0]
        targets = {name.lower(), first.lower()}
        if targets & set(explicit):
            found.append(member["id"])
            continue
        if re.search(rf"\b{re.escape(first)}\b", body or "", re.IGNORECASE):
            found.append(member["id"])
    dedup = []
    for item in found:
        if item not in dedup:
            dedup.append(item)
    return dedup


def suggest_due(body: str) -> str | None:
    low = (body or "").lower()
    today = datetime.now(PARIS).date()
    iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", low)
    if iso:
        return iso.group(1)
    for name, index in WEEKDAYS.items():
        if re.search(rf"\b{name}\b", low):
            delta = (index - today.weekday()) % 7
            if delta == 0:
                delta = 7
            return (today + timedelta(days=delta)).strftime("%Y-%m-%d")
    return None


def suggest_title(body: str) -> str:
    line = " ".join((body or "").strip().split())
    line = re.sub(r'^@\"[^\"]+\"\s*', "", line)
    line = re.sub(r"^@[\wÀ-ÿ'’.-]+\s*", "", line)
    if len(line) > 110:
        return line[:107].rstrip() + "…"
    return line or "Tâche issue de la discussion"


def file_size(n: int) -> str:
    if n < 1024:
        return f"{n} o"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} Ko"
    return f"{n / (1024 * 1024):.1f} Mo"


def dm_pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


FLASH = {
    "compte-cree": "Votre compte est créé. Vous pouvez compléter votre profil.",
    "connecte": "Bon retour.",
    "deconnecte": "Vous êtes déconnecté.",
    "suspendu": "Ce compte est suspendu. Écrivez à l'administration de la plateforme.",
    "profil": "Profil mis à jour.",
    "mot-de-passe": "Mot de passe modifié. Les autres sessions ont été fermées.",
    "email-verifie": "Adresse e-mail confirmée.",
    "lien-invalide": "Ce lien n'est plus valable.",
    "groupe-cree": "Le groupe a été créé.",
    "groupe-maj": "Le groupe a été mis à jour.",
    "groupe-supprime": "Le groupe a été supprimé.",
    "demande-envoyee": "Votre demande a été envoyée.",
    "invitation-envoyee": "Invitation envoyée.",
    "membre-ajoute": "Le membre a rejoint le groupe.",
    "membre-retire": "Le membre a été retiré.",
    "quitte": "Vous avez quitté le groupe.",
    "role": "Le rôle a été mis à jour.",
    "tache": "Tâche enregistrée.",
    "tache-supprimee": "Tâche supprimée.",
    "ressource": "Ressource publiée.",
    "signalement": "Signalement transmis à la modération.",
    "evenement": "Événement ajouté au calendrier.",
    "evenement-supprime": "Événement supprimé.",
    "connexion": "Demande de connexion envoyée.",
    "connexion-maj": "Connexion mise à jour.",
    "bloque": "Utilisateur bloqué. Il ne peut plus vous écrire.",
    "notif": "Notifications mises à jour.",
    "admin": "Action enregistrée.",
    "favori": "Favoris mis à jour.",
    "fichier": "Fichier ajouté.",
    "publie": "Le document est maintenant dans la bibliothèque.",
    "objectif": "Objectif du jour enregistré.",
    "erreur": "L'action n'a pas pu être terminée.",
}

STATUS_LABELS = {"todo": "À faire", "doing": "En cours", "review": "En révision", "done": "Terminé"}
PRIORITY_LABELS = {"low": "Basse", "normal": "Normale", "high": "Haute", "urgent": "Urgente"}
KIND_LABELS = {
    "reunion": "Réunion",
    "travail": "Session de travail",
    "echeance": "Échéance",
    "autre": "Autre",
}
ROLE_LABELS = {"owner": "Propriétaire", "admin": "Responsable", "member": "Membre"}
LEVELS = ["L1", "L2", "L3", "M1", "M2", "Doctorat", "Autre"]
DEFAULT_PREFS = {"messages": True, "tasks": True, "groups": True, "resources": True, "events": True}
PREF_KEYS = tuple(DEFAULT_PREFS)
NOTIF_PREF = {
    "message": "messages",
    "mention": "messages",
    "reply": "messages",
    "join_request": "groups",
    "invitation": "groups",
    "invitation_accepted": "groups",
    "connection": "groups",
    "task_assigned": "tasks",
    "task_updated": "tasks",
    "due_soon": "tasks",
    "overdue": "tasks",
    "document": "resources",
    "event": "events",
}
ALLOWED_EMOJI = ["👍", "✅", "❓", "👀"]
