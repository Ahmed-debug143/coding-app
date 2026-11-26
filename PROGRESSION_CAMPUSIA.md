# Rapport d'avancement Campusia

Dernière mise à jour: 2026-11-26

## Statut global

Campusia est fortement avancée et conserve son architecture FastAPI, SQLite, HTML, CSS et JavaScript.
La vérification initiale part de l'état réel du dépôt: l'ancien rapport a été vérifié sans modification de données.

## PHASE 1 - Audit complet

### Réalisé

- Architecture réelle cartographiée.
- Routeurs FastAPI identifiés.
- Base SQLite actuelle inspectée sans modification.
- Suite automatique exécutée sur une base isolée.
- Interface principale vérifiée précédemment sur bureau et mobile.
- Documentation, migrations et fonctions backend recensées.

### Fichiers créés ou modifiés

- [README.md](/Users/mrdra/Desktop/coding app/coding app/README.md): procédure d'installation, lancement et déploiement.
- Ce rapport: suivi des phases et décisions.
- Aucun fichier ou dossier de données utilisateur n'a été supprimé.

### Migrations effectuées

- Aucun changement destructif.
- Les quatre migrations existantes étaient déjà appliquées dans la base locale: `001_init.sql`, `002_student_profile.sql`, `003_collaboration_discovery.sql`, `004_task_management.sql`.
- La base existante n'a pas été réinitialisée.

### Tests exécutés

- `python -m pytest -q`
- Résultat vérifié: **56 tests réussis sur 56**.
- Le seul avertissement est une dépréciation FastAPI/TestClient liée à `httpx2`.

### Vérifications manuelles

- Inscription, tableau de bord et ajout d'un événement déjà vérifiés avec le navigateur partagé.
- Vérification mobile effectuée à une largeur de 390 px.
- Serveur local démarré puis arrêté après le contrôle `/health`.

### Audit des modules

#### Fonctionnalités terminées et testées

- Inscription, connexion, déconnexion et sessions HTTP-only.
- Profils réels et photo de profil.
- Recherche d'étudiants et recommandations explicables.
- Connexions entre étudiants.
- Groupes, invitations, demandes d'adhésion et rôles.
- Tâches, affectations, priorités, échéances, commentaires, historique et Kanban.
- Messagerie de groupe, réactions, fichiers, recherche et WebSocket.
- Messagerie privée autorisée, historique, lecture, modification et suppression.
- Ressources publiées, téléversement, téléchargement, favoris et signalements.
- Calendrier personnel avec création et suppression.
- Notifications persistantes avec marquage individuel.
- Administration de base, suspension des comptes et traitement des signalements.
- Assistant avec réponse locale explicite et intégration externe optionnelle.

#### Fonctionnalités terminées mais nécessitant une configuration externe

- Modèle IA externe via `AULA_AI_API_KEY`, `AULA_AI_BASE_URL` et `AULA_AI_MODEL`.
- Déploiement HTTPS/CORS via les variables d'environnement.

#### Fonctionnalités partiellement opérationnelles

- Modification du mot de passe: logique backend présente, mais aucune route/API ni formulaire complet.
- Réinitialisation de mot de passe: jetons présents en base, aucun service e-mail ni parcours HTTP complet.
- Modification du calendrier: création/suppression disponibles, modification manque.
- Suppression des groupes: logique repository présente, aucune route ni confirmation utilisateur.
- Suppression des ressources: non exposée côté propriétaire/administrateur.
- Suppression des notifications: aucun endpoint.
- Suppression des connexions: logique repository présente, aucune route claire.
- Administration: statistiques et suspension présentes, historique administratif absent.
- Publications communautaires: absentes.
- WebSocket privé: absent; la messagerie privée reste fonctionnelle par API.
- Vue calendrier semaine/jour: seule une vue mensuelle/agrégée existe.
- Gestion des rappels: non persistante dans une interface dédiée.

#### Fonctionnalités non réalisées

- Fil d'actualité communautaire étudiant.
- Commentaires/réponses et réactions aux publications.
- Modération dédiée aux publications.
- Service SMTP ou fournisseur e-mail de réinitialisation.
- Stockage objet externe et migration PostgreSQL.
- Historique complet des actions administratives.

### Problèmes connus

- L'ancien fichier `README.md` ne documentait pas encore toutes les routes ni les limites.
- Aucun fichier `.env.example` n'existait.
- Aucune confirmation explicite côté serveur pour certaines suppressions annoncées.
- Les publications ne doivent pas être ajoutées comme données fictives.
- SQLite est adapté aux fonctions locales actuelles, pas à une charge multi-instance élevée.

### Problème technique résolu lors de l'audit

- [pytest.ini](/Users/mrdra/Desktop/coding app/coding app/pytest.ini) inclut maintenant `pythonpath = .`, permettant `pytest -q` depuis la racine.

### Plan d'exécution priorisé

1. Ajouter les parcours manquants sans migration destructrice: changement de mot de passe, suppression des groupes, ressources, connexions et notifications.
2. Compléter la modification des événements et l'affichage jour/semaine/mois.
3. Ajouter les publications avec tables additive, routes, interface, permissions et modération.
4. Ajouter l'historique administratif et les actions sécurité/audit.
5. Documenter les API, les rôles, les variables d'environnement et le déploiement.
6. Exécuter les tests complets après chaque grande phase.

### Dépendances ou configuration nécessaires

- Python 3.11+ recommandé.
- FastAPI, Uvicorn, SQLite et dépendances du fichier [requirements.txt](/Users/mrdra/Desktop/coding app/coding app/requirements.txt).
- IA externe optionnelle.
- SMTP externe nécessaire avant toute réinitialisation par e-mail.

### Limites restantes

- Aucun service de messagerie privé WebSocket dédié.
- Aucun stockage externe configuré.
- Publications communautaires non implémentées à ce stade.

### Prochaine phase

PHASE 3 - consolidation des publications, de la modération et de la documentation.

---

## PHASE 2 - Fiabilisation de l'authentification, des suppressions et du calendrier

### Réalisé

- Route serveur de changement de mot de passe avec CSRF.
- Anciennes sessions supprimées lors du changement de mot de passe.
- Suppression autorisée des groupes par leur propriétaire.
- Suppression autorisée des ressources par l'auteur ou un administrateur.
- Suppression des connexions.
- Suppression des notifications.
- Modification des événements personnels et de groupe.
- Interface pour changer le mot de passe.
- Interface pour modifier/supprimer les événements.
- Interface pour supprimer les groupes, ressources et notifications.

### Fichiers créés ou modifiés

- [auth_routes.py](/Users/mrdra/Desktop/coding app/coding app/aula/auth_routes.py)
- [collaboration_routes.py](/Users/mrdra/Desktop/coding app/coding app/aula/collaboration_routes.py)
- [resource_routes.py](/Users/mrdra/Desktop/coding app/coding app/aula/resource_routes.py)
- [calendar_routes.py](/Users/mrdra/Desktop/coding app/coding app/aula/calendar_routes.py)
- [profile_routes.py](/Users/mrdra/Desktop/coding app/coding app/aula/profile_routes.py)
- [app.js](/Users/mrdra/Desktop/coding app/coding app/static/app.js)
- [main.py](/Users/mrdra/Desktop/coding app/coding app/main.py)
- [test_phase2_permissions.py](/Users/mrdra/Desktop/coding app/coding app/tests/test_phase2_permissions.py)

### Migrations effectuées

- Aucune migration destructive.
- Les suppressions utilisent les relations SQLite existantes et les cascades déjà déclarées.

### Tests exécutés

- `python -m pytest -q tests/test_phase2_permissions.py tests/test_resource_calendar_api.py tests/test_dm_admin_api.py`
- Résultat: **8 tests réussis sur 8**.

### Fonctionnalités vérifiées

- CSRF refusé en l'absence du jeton.
- Changement de mot de passe avec ancien mot de passe refusé ensuite.
- Mise à jour du calendrier persistée.
- Suppression du groupe par propriétaire.
- Suppression de ressource et tentative correcte du fichier isolé.

### Problèmes rencontrés

- Aucune perte de données n'a été constatée sur la base locale.
- La réinitialisation par e-mail reste dépendante d'un fournisseur SMTP, non ajouté.

### Limites restantes

- Réinitialisation par e-mail non finalisée.
- Aucun tableau historique d'audit administratif pour toutes les actions.
- Aucune vue calendrier jour/semaine dédiée.

### Prochaine phase

PHASE 3 - publications communautaires et modération.

---

## PHASE 3 - Publications communautaires

### Réalisé

- Migration additive `005_publications.sql`.
- Publications persistantes avec liens.
- Commentaires.
- Réactions.
- Signalements séparés des signalements existants.
- Suppression par auteur ou administrateur.
- Interface « Vie étudiante ».
- Modération des publications dans l'administration.

### Fichiers créés ou modifiés

- [005_publications.sql](/Users/mrdra/Desktop/coding app/coding app/aula/migrations/005_publications.sql)
- [publication_routes.py](/Users/mrdra/Desktop/coding app/coding app/aula/publication_routes.py)
- [admin_routes.py](/Users/mrdra/Desktop/coding app/coding app/aula/admin_routes.py)
- [test_publications_api.py](/Users/mrdra/Desktop/coding app/coding app/tests/test_publications_api.py)
- Interface dans [main.py](/Users/mrdra/Desktop/coding app/coding app/main.py) et [app.js](/Users/mrdra/Desktop/coding app/coding app/static/app.js).

### Migration

- Migration additive uniquement.
- Compatible avec les données anciennes: aucune table existante n'est supprimée ni modifiée.
- Quatre nouvelles tables et deux nouveaux index sont créés.

### Tests exécutés

- `python -m compileall -q main.py aula tests`
- `python -m pytest -q tests/test_publications_api.py tests/test_phase2_permissions.py`
- Résultat: **4 tests réussis sur 4**.

### Dépendances

- Aucune dépendance externe ajoutée.
- Toutes les publications restent persistées dans SQLite.

### Limites

- Pas de pièces jointes dans les publications; les documents doivent être publiés séparément dans la bibliothèque.
- Pas de WebSocket dédié aux publications; le fil doit être rechargé.

### Tests finaux

- `python -m pytest -q`
- Résultat final vérifié: **62 tests réussis sur 62**.
- Aucun test ne signale de perte de données lors de la compatibilité des migrations.
- Un avertissement FastAPI/TestClient reste lié à `httpx2`.

### Étapes restantes clairement identifiées

- Configurer un fournisseur SMTP valide pour l'envoi réel des liens de réinitialisation.
- Configurer PostgreSQL uniquement si le déploiement dépasse les limites locales de SQLite.
- Préparer PostgreSQL ou un stockage externe uniquement après montée en charge réelle.

### État final de cette séquence

- L'audit a été conservé dans ce rapport.
- Les phases de fiabilisation et de publications ont été testées.
- Les données locales existantes n'ont pas été réinitialisées.
- Aucun dossier `uploads` existant n'a été supprimé.

---

## PHASE 4 - Réinitialisation, calendrier complet et audit

### Réalisé

- Réinitialisation de mot de passe par jeton à usage unique.
- Toutes les sessions sont fermées après réinitialisation.
- Réponse anti-énumération pour les demandes de réinitialisation.
- Envoi SMTP optionnel via variables `AULA_SMTP_*`.
- Le lien n'est exposé que lorsque `AULA_EXPOSE_RESET_LINKS=1` est explicitement activé.
- Vues calendrier jour, semaine et mois.
- Migration additive `006_admin_audit.sql`.
- Historique persistant des suspensions et résolutions de signalements.
- Interface administrateur affichant l'historique.

### Fichiers créés ou modifiés

- [auth_routes.py](/Users/mrdra/Desktop/coding app/coding app/aula/auth_routes.py)
- [auth.py](/Users/mrdra/Desktop/coding app/coding app/aula/auth.py)
- [config.py](/Users/mrdra/Desktop/coding app/coding app/aula/config.py)
- [006_admin_audit.sql](/Users/mrdra/Desktop/coding app/coding app/aula/migrations/006_admin_audit.sql)
- [admin_routes.py](/Users/mrdra/Desktop/coding app/coding app/aula/admin_routes.py)
- [main.py](/Users/mrdra/Desktop/coding app/coding app/main.py)
- [app.js](/Users/mrdra/Desktop/coding app/coding app/static/app.js)
- [.env.example](/Users/mrdra/Desktop/coding app/coding app/.env.example)

### Migrations

- `006_admin_audit.sql` ajoute uniquement la table `admin_audit` et son index.
- Aucun changement destructif sur les données existantes.

### Tests exécutés

- `python -m compileall -q main.py aula tests`
- `python -m pytest -q`
- Résultat final: **62 tests réussis sur 62**.

### Vérifications manuelles

- Écran de calendrier vérifié avec les boutons Jour, Semaine et Mois.
- Écran « Mot de passe oublié » vérifié dans le navigateur.
- Déconnexion puis affichage de l'écran de réinitialisation vérifiés.

### Configurations externes restantes

- SMTP réel nécessaire pour envoyer les liens à de vrais destinataires.
- IA externe optionnelle déjà intégrée.

### Limites restantes

- PostgreSQL et stockage objet ne sont pas nécessaires pour le lancement local.
- La migration vers ces services doit être décidée selon la charge réelle.

---

## PHASE 5 - Corrections de sécurité prioritaires

### Vulnérabilités corrigées

1. **Lien de réinitialisation dérivé de Host**
   - Fichier: `aula/auth_routes.py`
   - Correction: ajout de `AULA_RESET_BASE_URL`.
   - Validation stricte d'origine sans identifiants, requête, fragment ou chemin.
   - Si la configuration est absente, aucune génération de lien ni appel SMTP n'est effectué.
   - Le comportement est anti-énumération même pour les comptes connus ou inconnus.

2. **WebSocket conservé après suspension**
   - Fichiers: `aula/message_routes.py`, `aula/hub.py`, `aula/admin_routes.py`.
   - Une suspension publie immédiatement un événement `force_disconnect`.
   - Le WebSocket revalide session, suspension et appartenance avant l'envoi des événements.
   - Revalidation périodique toutes les 25 secondes si aucun événement n'arrive.
   - Code de fermeture serveur WebSocket: `1008`.

### Tests de sécurité ajoutés

- Origine reset Host malveillante: lien généré uniquement depuis `AULA_RESET_BASE_URL`.
- Base reset absente: aucun SMTP ni lien exposé.
- Validation des URL reset invalides ou contenant identifiants, requête, fragment ou chemin.
- Suspension avec une connexion WebSocket ouverte: fermeture avec code `1008`.
- Le test suspendu vérifie qu'aucun message ultérieur n'est reçu.

### Résultats

- Reproduction reset: tests ciblés passés après correction.
- Reproduction WebSocket: test ciblé passé après correction.
- Suite complète: **66 tests réussis sur 66**.
- Compilation Python: réussie.
- Aucun échec de test restant.

### Vérifications manuelles

- Écran « Mot de passe oublié » inspecté dans le navigateur.
- Boutons Jour/Semaine/Mois vérifiés précédemment.
- Interface connexion et navigation principale vérifiée.
- Serveur local démarré et navigateur utilisé sur `http://127.0.0.1:8765/`.

### État des risques

- Risque Host Header corrigé.
- Risque WebSocket suspendu corrigé par déconnexion immédiate et revalidation périodique.
- Aucun problème critique ou haute vulnérabilité supplémentaire confirmé par la revue ciblée.

---

## PHASE 6 - Validation finale orientée produit

### Audit réalisé

- Suite globale exécutée sur une base temporaire de test.
- Revue des permissions groupes, fichiers, profils, ressources, DM, publications et administration.
- Parcours réel à deux étudiants ajouté à la suite automatisée.
- Inspection navigateur à 1440 px, 1024 px et 390 px.
- Vérification des titres de navigation, débordements horizontaux et chargement du tableau de bord.

### Bugs corrigés

1. **Tableau de bord JavaScript**
   - Cause: `renderDashboard()` manipulait `#resourcesList`, ancien élément supprimé lors de la bibliothèque.
   - Correction: accès conditionnel à l'ancien emplacement optionnel.
   - Vérification: rechargement navigateur sans erreur ni état « Impossible de charger vos informations ».

2. **Fuite de métadonnées privées des ressources**
   - Cause: les listes et le tableau de bord ne tenaient pas compte de l'appartenance au groupe.
   - Correction: filtre SQL sur `group_members`, contrôle sur favoris/signaler, détail et téléchargement.
   - Test: une ressource privée n'est ni listée ni retournée à un étudiant extérieur.

3. **Profil public direct après blocage**
   - Cause: les endpoints profil/avatar ne vérifiaient pas le lien bloqué.
   - Correction: ajout du contrôle `is_blocked`.

4. **Titres de pages avec icônes visibles**
   - Cause: expression de nettoyage des icônes limitée.
   - Correction: ajout des icônes privées, publications, calendrier, assistant et administration.

### Parcours intégré ajouté

Le test `test_final_journey.py` vérifie avec deux comptes temporaires:

- inscription;
- modification des profils;
- recherche par filière;
- demande et acceptation de connexion;
- conversation privée;
- création d'un groupe et invitation;
- adhésion;
- fichier de groupe;
- création et affectation d'une tâche;
- passage de statut;
- ressource partagée;
- publication/commentaire/réaction;
- tableau de bord;
- déconnexion/reconnexion;
- persistance du profil.

### Tests

- Nouvelle suite complète relancée le 2026-11-26: **69 tests réussis sur 69**.
- Compilation Python relancée avec `python -m compileall -q main.py aula tests`: réussie.
- Résultat final vérifié: **69 tests réussis sur 69**.
- L'ajout du test statique doit être inclus dans la prochaine suite complète.
- Aucun échec restant connu dans les modules audités.
- La dépréciation FastAPI/TestClient liée à `httpx2` reste seule avertissement connu.

### Vérifications visuelles manuelles

- Desktop 1440x900: aucune largeur horizontale dépassée sur les vues auditées.
- Écran 1024x768: aucune largeur horizontale dépassée sur les vues auditées.
- Mobile 390x844: aucune largeur horizontale dépassée sur les vues auditées.
- Pages inspectées: connexion, reset, dashboard, groupes, découverte, personnes, tâches,
  messages privés, vie étudiante, ressources, calendrier, assistant et profil.
- Le tableau de bord a été vérifié après rechargement réel et affiche les données de session.

### État de préparation au concours

- Niveau: préparé pour une démonstration locale avec comptes de test.
- Les parcours principaux sont persistants et les permissions essentielles sont testées.
- SMTP, IA externe et PostgreSQL restent des dépendances/configurations optionnelles.
- SQLite convient au concours et au lancement local.
- Ne pas présenter la réinitialisation SMTP comme opérationnelle sans variables SMTP réelles.

### Limites transparentes

- Présence en ligne WebSocket limitée aux groupes ouverts.
- Publications sans WebSocket temps réel dédié.
- Pas de stockage externe ou PostgreSQL.
- Pas de déploiement public effectué.
- Les tests navigateur automatisés restent limités aux pages TestClient/Playwright disponibles.
