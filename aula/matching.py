import re

from aula.util import LEVELS, loads

STOP_WORDS = {"avec", "dans", "pour", "vous", "nous", "leur", "leurs", "projet", "étudiant", "etude", "études", "objectif", "une", "des", "les", "sur", "par", "pour", "aux", "the", "and", "for", "with"}


def _bag(value) -> set[str]:
    if isinstance(value, list):
        items = value
    else:
        items = loads(value, [])
    return {str(item).strip().casefold() for item in items if str(item).strip()}


def _words(value) -> set[str]:
    return {word for word in re.findall(r"[\wÀ-ÿ]{3,}", (value or "").casefold()) if word not in STOP_WORDS}


def _level_distance(a: str, b: str) -> int | None:
    if a not in LEVELS or b not in LEVELS:
        return None
    return abs(LEVELS.index(a) - LEVELS.index(b))


def explain(me: dict, other: dict, wanted: list[str] | None = None) -> tuple[int, list[str]]:
    """Return a private ordering weight and understandable evidence, never a probability."""
    score = 0
    reasons: list[str] = []
    my_skills, their_skills = _bag(me.get("skills")), _bag(other.get("skills"))
    shared_interests = _bag(me.get("interests")) & _bag(other.get("interests"))
    shared_projects = _bag(me.get("project_types")) & _bag(other.get("project_types"))
    goal_overlap = _words(me.get("focus_goal")) & _words(other.get("focus_goal"))

    if me.get("filiere") and me.get("filiere", "").casefold() == other.get("filiere", "").casefold():
        score += 12
        reasons.append(f"vous étudiez tous les deux en {me['filiere']}")
    if me.get("school") and me.get("school", "").casefold() == other.get("school", "").casefold():
        score += 5
        reasons.append("vous étudiez dans le même établissement")
    distance = _level_distance(me.get("level") or "", other.get("level") or "")
    if distance == 0:
        score += 4
        reasons.append(f"vous êtes au même niveau ({me['level']})")
    elif distance == 1:
        score += 2
        reasons.append("vos niveaux d’étude sont proches")
    if shared_interests:
        score += min(12, 4 * len(shared_interests))
        reasons.append("vous partagez les intérêts " + ", ".join(sorted(shared_interests)[:3]))
    if shared_projects:
        score += min(10, 5 * len(shared_projects))
        reasons.append("vous recherchez des projets du même type : " + ", ".join(sorted(shared_projects)[:3]))

    needed_skills = {item.casefold() for item in (wanted or [])}
    matched_needs = their_skills & needed_skills
    if matched_needs:
        score += min(20, 8 * len(matched_needs))
        reasons.append("ses compétences répondent au besoin " + ", ".join(sorted(matched_needs)[:3]))
    complementary = their_skills - my_skills
    if complementary and not matched_needs and (shared_projects or goal_overlap):
        score += min(8, 2 * len(complementary))
        reasons.append("pour un projet qui vous intéresse, il apporte des compétences différentes : " + ", ".join(sorted(complementary)[:3]))
    shared_skills = my_skills & their_skills
    if shared_skills and not complementary:
        score += min(4, 2 * len(shared_skills))
        reasons.append("vous partagez les compétences " + ", ".join(sorted(shared_skills)[:3]))

    if goal_overlap:
        score += min(8, 2 * len(goal_overlap))
        reasons.append("vos objectifs évoquent " + ", ".join(sorted(goal_overlap)[:3]))
    my_prefs, their_prefs = _bag(me.get("collab_prefs")), _bag(other.get("collab_prefs"))
    shared_prefs = my_prefs & their_prefs
    if shared_prefs:
        score += min(6, 2 * len(shared_prefs))
        labels = {"remote": "à distance", "in_person": "en présentiel", "hybrid": "hybride", "structured": "structurée", "flexible": "flexible", "weekly": "hebdomadaire", "async": "asynchrone"}
        reasons.append("vos préférences de collaboration concordent : " + ", ".join(labels.get(item, item) for item in sorted(shared_prefs)[:3]))
    return score, reasons


def sentence(reasons: list[str]) -> str:
    if not reasons:
        return "Aucun critère commun renseigné pour le moment."
    if len(reasons) == 1:
        text = reasons[0]
    elif len(reasons) == 2:
        text = f"{reasons[0]} et {reasons[1]}"
    else:
        text = ", ".join(reasons[:-1]) + " et " + reasons[-1]
    return "Cette suggestion s’appuie sur le fait que " + text + "."


def rank(me: dict, others: list[dict], *, wanted: list[str] | None = None, limit: int = 20):
    ranked = []
    for other in others:
        if other["id"] == me["id"]:
            continue
        score, reasons = explain(me, other, wanted)
        if score <= 0 or not reasons:
            continue
        ranked.append({"user": other, "score": score, "reasons": reasons, "sentence": sentence(reasons)})
    ranked.sort(key=lambda item: (-item["score"], item["user"]["name"].casefold()))
    return ranked[:max(1, min(limit, 40))]
