# MED_ETUD

MED_ETUD est une plateforme universitaire collaborative construite avec FastAPI, SQLite,
HTML, CSS et JavaScript.

## Installation

Depuis la racine du projet:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8765
```

Ouvrez ensuite `http://127.0.0.1:8765`.

## Variables d'environnement

Les valeurs suivantes sont optionnelles:

```powershell
$env:AULA_DATA="C:\chemin\data-med-etud"
$env:AULA_CORS_ORIGINS="https://med-etud.example.edu"
$env:AULA_HOST="127.0.0.1"
$env:AULA_PORT="8765"
$env:AULA_AI_API_KEY="cle-api"
$env:AULA_AI_BASE_URL="https://api.openai.com/v1"
$env:AULA_AI_MODEL="gpt-4o-mini"
$env:AULA_RESET_BASE_URL="https://med-etud.example.edu"
$env:AULA_SMTP_HOST="smtp.example.edu"
$env:AULA_SMTP_PORT="587"
$env:AULA_SMTP_USER="noreply@example.edu"
$env:AULA_SMTP_PASSWORD="secret"
$env:AULA_SMTP_FROM="noreply@example.edu"
$env:AULA_SMTP_TLS="1"
```

- `AULA_DATA` définit le dossier contenant SQLite et les fichiers téléversés.
- `AULA_CORS_ORIGINS` accepte une liste d'origines séparées par des virgules.
- `AULA_AI_API_KEY` active le modèle externe de l'assistant.
- Sans clé, l'assistant utilise uniquement des analyses locales explicables.
- `AULA_RESET_BASE_URL` est l'origine HTTPS/HTTP explicitement autorisée pour les liens de réinitialisation. Sans cette valeur, aucun lien ni e-mail de réinitialisation n'est généré.
- `AULA_SMTP_*` active l'envoi réel des e-mails. Sans SMTP, la demande reste sécurisée mais aucun e-mail n'est envoyé.

Ne configurez jamais `AULA_CORS_ORIGINS=*`.

## Tests

Les tests utilisent une base SQLite temporaire et un dossier d'uploads temporaire:

```powershell
python -m pytest -q
```

## Fonctionnalités disponibles

- Authentification, profils et changement de mot de passe.
- Recherche d'étudiants, connexions, groupes et invitations.
- Tâches, Kanban, commentaires et historique.
- Messagerie de groupe et messagerie privée autorisée.
- Bibliothèque de ressources, favoris, téléchargement et signalements.
- Calendrier personnel et réunions de groupe.
- Publications communautaires, commentaires, réactions et modération.
- Administration, suspensions et traitement des signalements.
- Assistant local avec modèle externe optionnel.

## API principales

- `/api/auth/*`: inscription, connexion, session, déconnexion et mot de passe.
- `/api/profile/me`, `/api/dashboard`: profil et tableau de bord.
- `/api/groups/*`, `/api/students*`, `/api/connections*`: collaboration.
- `/api/groups/{id}/tasks`, `/api/tasks/*`: tâches.
- `/api/dm/*`, `/api/groups/{id}/messages`: communication.
- `/api/resources*`: bibliothèque.
- `/api/calendar*`: calendrier.
- `/api/publications*`: vie étudiante.
- `/api/admin/*`: administration strictement réservée aux rôles administrateurs.

Toutes les mutations utilisent un jeton CSRF transmis dans l'en-tête `X-CSRF-Token`.

## Déploiement

Pour un premier déploiement, utilisez une origine HTTPS explicite, un stockage persistant
pour `AULA_DATA` et une sauvegarde régulière de `data/aula.db`.

Exemple de lancement en production derrière un proxy HTTPS:

```powershell
$env:AULA_HOST="0.0.0.0"
$env:AULA_PORT="8765"
$env:AULA_CORS_ORIGINS="https://med-etud.example.edu"
python -m uvicorn main:app --host $env:AULA_HOST --port $env:AULA_PORT
```

Ne lancez aucune migration destructive, ne réinitialisez pas `data/aula.db` et ne supprimez
pas le dossier `uploads`.

## Migrations

Les migrations SQL sont situées dans `aula/migrations`. Elles sont appliquées automatiquement
au démarrage à partir de leur nom. Les migrations sont additives dans les versions actuelles;
aucune migration destructive n'est fournie.

`005_publications.sql` ajoute uniquement les publications, commentaires, réactions et
signalements associés.

Avant une mise à jour, sauvegardez `data/aula.db` et le dossier `data/uploads`.

## Limites actuelles

- La réinitialisation par e-mail nécessite `AULA_SMTP_*`; sans SMTP, aucun lien n'est envoyé.
- Le modèle IA est uniquement actif après configuration de la clé API externe.
- Les publications utilisent le rechargement HTTP plutôt qu'un WebSocket dédié.
- SQLite convient au lancement actuel; PostgreSQL doit être évalué pour une charge multi-instance.

## Scénario de démonstration

Durée cible: 5 à 7 minutes. Utilisez uniquement des comptes de démonstration isolés.

1. **0:00-0:45** — Inscrire Alice, se connecter et compléter le profil.
2. **0:45-1:20** — Inscrire ou basculer vers Bob, montrer la recherche par filière/compétences
   et envoyer une demande de connexion.
3. **1:20-1:50** — Accepter la demande, ouvrir une conversation privée et envoyer un message.
4. **1:50-2:35** — Alice crée « Projet concours », invite Bob et lui attribue un rôle.
5. **2:35-3:15** — Bob rejoint le groupe, partage un fichier, puis Alice crée une tâche.
6. **3:15-3:55** — Bob affiche le Kanban, passe la tâche en cours/terminée et commente.
7. **3:55-4:30** — Publier une ressource, ouvrir le calendrier, créer une réunion.
8. **4:30-5:05** — Publier dans « Vie étudiante », commenter et réagir.
9. **5:05-5:35** — Montrer les notifications et le tableau de bord réel.
10. **5:35-6:15** — Se déconnecter puis se reconnecter; vérifier la persistance.
11. **6:15-6:45** — Si un compte administrateur de démonstration existe, ouvrir les statistiques,
    suspendre/réactiver un utilisateur test et montrer l'historique.

Procédure de secours:

- Garder les comptes Alice/Bob ouverts dans deux sessions privées.
- Préparer avant la démonstration un groupe, une ressource et un événement de test.
- Si l'IA externe est inactive, présenter le mode local explicite.
- Si SMTP est absent, ne pas présenter la réinitialisation comme un envoi réel.
