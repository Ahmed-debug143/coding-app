from aula.util import LEVELS, loads


def _bag(value) -> set[str]:
    if isinstance(value, list):
        items = value
    else:
        items = loads(value, [])
    return {str(item).strip().lower() for item in items if str(item).strip()}


def _level_distance(a: str, b: str) -> int | None:
    if a not in LEVELS or b not in LEVELS:
        return None
    return abs(LEVELS.index(a) - LEVELS.index(b))


def explain(me: dict, other: dict, wanted: list[str] | None = None) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    my_skills = _bag(me.get("skills"))
    their_skills = _bag(other.get("skills"))
    shared_interests = _bag(me.get("interests")) & _bag(other.get("interests"))
    complementary = sorted(their_skills - my_skills)
    shared_skills = sorted(my_skills & their_skills)

    if me.get("filiere") and me.get("filiere") == other.get("filiere"):
        score += 28
        reasons.append(f"vous êtes tous les deux en {me['filiere']}")
    if me.get("school") and me.get("school") == other.get("school"):
        score += 10
        reasons.append("vous étudiez dans le même établissement")
    distance = _level_distance(me.get("level") or "", other.get("level") or "")
    if distance == 0 and me.get("level"):
        score += 8
        reasons.append(f"vous êtes au même niveau ({me['level']})")
    elif distance == 1:
        score += 4
        reasons.append("vos niveaux d'étude sont proches")
    if shared_interests:
        score += min(16, 8 * len(shared_interests))
        shown = ", ".join(shared_interests[:3])
        reasons.append(f"vous partagez {shown}")
    if complementary:
        score += min(24, 12 * len(complementary))
        shown = ", ".join(complementary[:3])
        reasons.append(f"ses compétences en {shown} complètent les vôtres")
    elif shared_skills:
        score += min(8, 4 * len(shared_skills))
        reasons.append(f"vous avez déjà {', '.join(shared_skills[:2])} en commun")
    wanted_set = {item.lower() for item in (wanted or [])}
    matched_needs = sorted(their_skills & wanted_set)
    if matched_needs:
        score += min(18, 9 * len(matched_needs))
        reasons.append(f"le groupe recherche {', '.join(matched_needs[:3])}")
    mine_av = (me.get("availability") or "").lower()
    their_av = (other.get("availability") or "").lower()
    if mine_av and their_av:
        tokens = ("matin", "après-midi", "soir", "semaine", "samedi", "dimanche", "weekend", "week-end")
        overlap = [token for token in tokens if token in mine_av and token in their_av]
        if overlap:
            score += 8
            reasons.append("vos disponibilités se recoupent")
    return score, reasons


def sentence(reasons: list[str]) -> str:
    if not reasons:
        return "Recommandation faible : peu de critères communs."
    if len(reasons) == 1:
        text = reasons[0]
    elif len(reasons) == 2:
        text = f"{reasons[0]} et {reasons[1]}"
    else:
        text = ", ".join(reasons[:-1]) + " et " + reasons[-1]
    return "Recommandé parce que " + text + "."


def rank(me: dict, others: list[dict], *, wanted: list[str] | None = None, limit: int = 6):
    ranked = []
    for other in others:
        if other["id"] == me["id"]:
            continue
        score, reasons = explain(me, other, wanted)
        if score < 12 or not reasons:
            continue
        ranked.append({
            "user": other,
            "score": score,
            "reasons": reasons,
            "sentence": sentence(reasons),
        })
    ranked.sort(key=lambda item: (-item["score"], item["user"]["name"]))
    return ranked[:limit]
