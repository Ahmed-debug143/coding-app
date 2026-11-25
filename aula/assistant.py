import json
import re

import httpx

from aula.config import AI_API_KEY, AI_BASE_URL, AI_MODEL

SYSTEM = """Tu es l'assistant d'organisation d'Aula, une plateforme universitaire.
Tu réponds en français, de façon concrète et brève.
Tu ne remplaces pas un enseignant.
Tu ne présentes comme décision, tâche ou date que ce qui est explicitement présent dans les données fournies.
Si une information manque, tu le dis.
Tu n'inventes pas de source, de citation ni de contenu de cours.
Quand on te demande du JSON, tu renvoies uniquement du JSON valide."""


def configured() -> bool:
    return bool(AI_API_KEY)


def _excerpt(body: str, limit: int = 180) -> str:
    text = " ".join((body or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def summarize_local(messages: list[dict]) -> dict:
    decisions, questions, pending = [], [], []
    for message in messages:
        if message.get("deleted_at") or not (message.get("body") or "").strip():
            continue
        body = message["body"].strip()
        low = body.lower()
        line = f"{message.get('author_name', 'Un membre')} : {_excerpt(body)}"
        if any(token in low for token in ("décision", "decision", "on valide", "on décide", "on decide", "validé", "valide :")):
            decisions.append(line)
        if "?" in body:
            questions.append(line)
        if any(token in low for token in ("en attente", "à confirmer", "pas encore", "risque", "bloque", "bloqué")):
            pending.append(line)
    sections = []
    sections.append({"heading": "Décisions repérées dans les messages", "items": decisions or ["Aucune formulation de décision n'a été repérée."]})
    sections.append({"heading": "Questions encore écrites dans le fil", "items": questions or ["Aucune question explicite."]})
    sections.append({"heading": "Points de vigilance mentionnés", "items": pending or ["Aucun point en attente n'a été repéré par les mots-clés."]})
    return {
        "mode": "local",
        "title": "Synthèse automatique locale",
        "intro": "Cette synthèse ne lit que les messages fournis. Elle repère des formulations, sans modèle de langage. Ce n'est pas une interprétation.",
        "sections": sections,
        "proposals": [],
    }


def propose_tasks_local(messages: list[dict], existing_titles: list[str]) -> dict:
    known = {title.lower() for title in existing_titles}
    proposals = []
    patterns = ("peux-tu", "peux tu", "il faut", "à faire", "a faire", "merci de", "pense à", "pense a")
    for message in messages:
        body = (message.get("body") or "").strip()
        if not body or message.get("deleted_at") or message.get("task_id"):
            continue
        low = body.lower()
        if not any(pattern in low for pattern in patterns):
            continue
        title = _excerpt(body, 110)
        if title.lower() in known:
            continue
        proposals.append({
            "title": title,
            "description": f"Issue du message de {message.get('author_name', 'un membre')} : {body}",
            "priority": "high" if "urgent" in low or "avant" in low else "normal",
            "source_message_id": message.get("id"),
        })
        if len(proposals) >= 5:
            break
    return {
        "mode": "local",
        "title": "Tâches proposées à partir des messages",
        "intro": "Rien n'est créé tant que vous ne validez pas. Chaque proposition reprend une phrase réellement présente.",
        "sections": [],
        "proposals": proposals,
    }


def organize_local(group: dict, progress: dict, workload: list[dict], tasks: list[dict]) -> dict:
    items = []
    if progress["total"] == 0:
        items.append("Le groupe n'a pas encore de tâche. Découpez l'objectif en livrables vérifiables, chacun avec un responsable et une date.")
    else:
        items.append(
            f"{progress['done']} tâche(s) terminée(s) sur {progress['total']} — la progression affichée est ce ratio, sans pondération par la difficulté."
        )
    late = [task for task in tasks if task.get("late")]
    if late:
        items.append("À traiter d'abord : " + " ; ".join(task["title"] for task in late[:4]) + ".")
    doing = [task["title"] for task in tasks if task.get("status") == "doing"]
    if doing:
        items.append("Déjà en cours : " + " ; ".join(doing[:4]) + ".")
    if workload:
        counts = [row["open_tasks"] or 0 for row in workload]
        if sum(counts) >= 3 and max(counts) >= 2 and max(counts) > (sum(counts) / max(len(counts), 1)) * 1.8:
            busiest = max(workload, key=lambda row: row["open_tasks"] or 0)
            items.append(
                f"{busiest['name']} porte {busiest['open_tasks']} tâches ouvertes, davantage que les autres. Ce chiffre compte les tâches, pas l'effort réel."
            )
    if group.get("objective"):
        items.append("Objectif écrit du groupe : " + _excerpt(group["objective"], 220))
    return {
        "mode": "local",
        "title": "Organisation du projet",
        "intro": "Lecture directe des tâches et de l'objectif enregistrés. Aucun modèle de langage n'est utilisé.",
        "sections": [{"heading": "Prochaines étapes utiles", "items": items}],
        "proposals": [],
    }


def study_local(question: str) -> dict:
    return {
        "mode": "local",
        "title": "Aide à l'organisation du travail",
        "intro": "Aucun modèle de langage n'est configuré. Aula ne peut donc pas expliquer un cours ni inventer un contenu. L'aide ci-dessous reste méthodologique.",
        "sections": [{
            "heading": "Méthode",
            "items": [
                "Reformulez la question en une phrase, puis séparez ce que vous savez déjà de ce qu'il reste à vérifier.",
                "Cherchez d'abord dans la bibliothèque du campus et dans les documents du groupe.",
                "Notez la source de chaque information. L'assistant ne doit pas devenir une source.",
                "Découpez le travail en une session de 25 à 40 minutes avec un livrable visible à la fin.",
                f"Votre question a bien été lue : {_excerpt(question or 'organisation du travail', 160)}",
            ],
        }],
        "proposals": [],
    }


def _model(user_text: str) -> str | None:
    if not configured():
        return None
    response = httpx.post(
        f"{AI_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": AI_MODEL,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user_text},
            ],
        },
        timeout=40,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _as_sections(text: str) -> dict:
    cleaned = text.strip()
    fenced = re.search(r"\{.*\}", cleaned, re.S)
    if fenced:
        try:
            data = json.loads(fenced.group(0))
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            sections = []
            for key, heading in (
                ("decisions", "Décisions présentes dans les messages"),
                ("questions", "Questions ouvertes"),
                ("pending", "Points en attente"),
                ("steps", "Étapes proposées"),
                ("risks", "Risques mentionnés ou déduits avec prudence"),
            ):
                values = data.get(key) or []
                if values:
                    sections.append({"heading": heading, "items": [str(item) for item in values[:8]]})
            proposals = []
            for item in data.get("proposals") or []:
                if isinstance(item, dict) and item.get("title"):
                    proposals.append({
                        "title": str(item["title"])[:140],
                        "description": str(item.get("description") or "")[:500],
                        "priority": item.get("priority") if item.get("priority") in {"low", "normal", "high", "urgent"} else "normal",
                        "source_message_id": None,
                    })
            if sections or proposals:
                return {
                    "mode": "model",
                    "title": "Assistant configuré",
                    "intro": "Réponse du modèle branché sur le serveur. Vérifiez chaque point dans les messages : une suggestion n'est pas une décision.",
                    "sections": sections,
                    "proposals": proposals[:6],
                }
    return {
        "mode": "model",
        "title": "Assistant configuré",
        "intro": "Réponse du modèle. Traitez-la comme une aide à relire, pas comme un compte-rendu officiel.",
        "sections": [{"heading": "Réponse", "items": [cleaned[:2000]]}],
        "proposals": [],
    }


def answer(action: str, payload: dict) -> dict:
    local = {
        "summary": lambda: summarize_local(payload.get("messages") or []),
        "tasks": lambda: propose_tasks_local(payload.get("messages") or [], payload.get("titles") or []),
        "organize": lambda: organize_local(payload.get("group") or {}, payload.get("progress") or {"total": 0, "done": 0}, payload.get("workload") or [], payload.get("tasks") or []),
        "study": lambda: study_local(payload.get("question") or ""),
        "partners": lambda: payload.get("partner_result"),
    }[action]()
    if action == "partners":
        return local
    if not configured():
        return local
    try:
        text = _model(json.dumps({"action": action, "donnees": payload, "consigne": "Réponds en JSON avec les clés decisions, questions, pending, steps, risks, proposals."}, ensure_ascii=False))
    except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError):
        local["intro"] += " Le service de modèle a échoué : la synthèse locale est affichée à la place."
        return local
    if not text:
        return local
    modeled = _as_sections(text)
    modeled["fallback_note"] = local["intro"]
    return modeled
