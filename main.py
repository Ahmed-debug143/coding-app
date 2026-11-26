from contextlib import asynccontextmanager
import asyncio
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from aula.config import CORS_ORIGINS, ROOT
from aula import auth
from aula.auth_routes import SESSION_COOKIE, router as auth_router
from aula.db import init_db, session, one
from aula.profile_routes import router as profile_router
from aula.collaboration_routes import router as collaboration_router
from aula.task_routes import router as task_router
from aula.message_routes import router as message_router
from aula.resource_routes import router as resource_router
from aula.calendar_routes import reminder_worker, router as calendar_router
from aula.admin_routes import router as admin_router
from aula.assistant_routes import router as assistant_router
from aula.publication_routes import router as publication_router
from aula.help_routes import router as help_router
from aula.hub import hub


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    hub.bind(asyncio.get_running_loop())
    reminder_task = asyncio.create_task(reminder_worker())
    try:
        yield
    finally:
        reminder_task.cancel()
        try:
            await reminder_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="MED_ETUD", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(collaboration_router)
app.include_router(task_router)
app.include_router(message_router)
app.include_router(resource_router)
app.include_router(calendar_router)
app.include_router(admin_router)
app.include_router(assistant_router)
app.include_router(publication_router)
app.include_router(help_router)
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    )


def page_html() -> str:
    return """
    <!doctype html>
    <html lang="fr">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>MED_ETUD — Tableau de bord</title>
      <link rel="stylesheet" href="/static/styles.css">
      <link rel="stylesheet" href="/static/med-etud-theme.css">
    </head>
    <body>
      <section class="auth-shell" id="authShell">
        <div class="auth-visual">
          <div class="auth-brand"><span class="brand-mark">M</span><span>MED_ETUD</span></div>
          <div class="auth-visual-copy"><p>UN ESPACE POUR AVANCER ENSEMBLE</p><h2>Les bons projets commencent ici.</h2><span>Retrouve ton équipe, partage tes ressources et progresse avec la communauté étudiante.</span></div>
          <img src="/static/med-etud-students.png" alt="Quatre jeunes étudiants noirs, souriants et prêts pour leurs études" loading="eager">
        </div>
        <div class="auth-card">
          <p class="auth-eyebrow">LA COLLABORATION ÉTUDIANTE, SIMPLIFIÉE</p>
          <div id="authLoading" class="auth-loading" role="status">Vérification de votre session…</div>
          <div id="authForms" hidden>
            <div id="loginPanel">
              <h1>Heureux de vous retrouver</h1>
              <p class="auth-intro">Connectez-vous pour retrouver votre espace de travail.</p>
              <form id="loginForm" novalidate>
                <label for="loginEmail">Adresse e-mail</label>
                <input id="loginEmail" name="email" type="email" autocomplete="email" required maxlength="160">
                <p class="field-error" data-error-for="email"></p>
                <label for="loginPassword">Mot de passe</label>
                <div class="password-field"><input id="loginPassword" name="password" type="password" autocomplete="current-password" required maxlength="128"><button type="button" class="password-toggle" data-toggle-password="loginPassword" aria-label="Afficher le mot de passe">Afficher</button></div>
                <p class="field-error" data-error-for="password"></p>
                <p class="form-error" id="loginError" role="alert"></p>
                <button class="primary auth-submit" type="submit">Se connecter</button>
              </form>
              <p class="auth-switch"><button type="button" data-show-forgot>Mot de passe oublié ?</button></p>
              <p class="auth-switch">Pas encore de compte ? <button type="button" data-show-register>Créer un compte</button></p>
            </div>
            <div id="registerPanel" hidden>
              <h1>Rejoignez MED_ETUD</h1>
              <p class="auth-intro">Créez votre compte étudiant pour commencer à collaborer.</p>
              <form id="registerForm" novalidate>
                <label for="registerName">Nom complet</label>
                <input id="registerName" name="name" type="text" autocomplete="name" required minlength="2" maxlength="80">
                <p class="field-error" data-error-for="name"></p>
                <label for="registerEmail">Adresse e-mail</label>
                <input id="registerEmail" name="email" type="email" autocomplete="email" required maxlength="160">
                <p class="field-error" data-error-for="email"></p>
                <label for="registerPassword">Mot de passe</label>
                <div class="password-field"><input id="registerPassword" name="password" type="password" autocomplete="new-password" required minlength="10" maxlength="128"><button type="button" class="password-toggle" data-toggle-password="registerPassword" aria-label="Afficher le mot de passe">Afficher</button></div>
                <p class="field-hint">10 caractères minimum.</p>
                <p class="field-error" data-error-for="password"></p>
                <label for="registerConfirm">Confirmer le mot de passe</label>
                <div class="password-field"><input id="registerConfirm" name="confirm" type="password" autocomplete="new-password" required minlength="10" maxlength="128"><button type="button" class="password-toggle" data-toggle-password="registerConfirm" aria-label="Afficher le mot de passe">Afficher</button></div>
                <p class="field-error" data-error-for="confirm"></p>
                <p class="form-error" id="registerError" role="alert"></p>
                <button class="primary auth-submit" type="submit">Créer mon compte</button>
              </form>
              <p class="auth-switch">Vous avez déjà un compte ? <button type="button" data-show-login>Se connecter</button></p>
            </div>
          </div>
          <div id="forgotPanel" hidden>
            <h1>Réinitialiser le mot de passe</h1>
            <p class="auth-intro">Demandez un lien sécurisé à votre adresse e-mail.</p>
            <form id="forgotForm" novalidate>
              <label for="forgotEmail">Adresse e-mail</label>
              <input id="forgotEmail" name="email" type="email" autocomplete="email" required maxlength="160">
              <p class="form-error" id="forgotError" role="alert"></p>
              <button class="primary auth-submit" type="submit">Envoyer le lien</button>
            </form>
            <p class="auth-switch"><button type="button" data-show-login>Retour à la connexion</button></p>
          </div>
          <div id="resetPanel" hidden>
            <h1>Choisir un nouveau mot de passe</h1>
            <form id="resetForm" novalidate>
              <input id="resetToken" name="token" type="hidden">
              <label for="resetPassword">Nouveau mot de passe</label>
              <input id="resetPassword" name="password" type="password" autocomplete="new-password" minlength="10" maxlength="128" required>
              <p class="form-error" id="resetError" role="alert"></p>
              <button class="primary auth-submit" type="submit">Modifier le mot de passe</button>
            </form>
          </div>
        </div>
      </section>

      <section id="welcomeScreen" class="welcome-screen" hidden>
        <header class="welcome-header"><div class="welcome-brand"><span class="brand-mark">M</span><strong>MED_ETUD</strong></div><span class="welcome-label">TON ESPACE ÉTUDIANT</span></header>
        <main class="welcome-main">
          <div class="welcome-copy">
            <p class="welcome-eyebrow">BIENVENUE SUR MED_ETUD</p>
            <h1>Heureux de te retrouver, <span id="welcomeName">étudiant</span>.</h1>
            <p class="welcome-intro">Une plateforme facilitant le travail en groupe, le partage de ressources pédagogiques et la mise en relation des étudiants. Organise tes projets, retrouve tes groupes et avance avec les autres étudiants, au même endroit.</p>
            <button type="button" class="primary welcome-enter" id="enterApplication">Entrer dans l’application <span aria-hidden="true">→</span></button>
            <div class="welcome-highlights" aria-label="Ce que tu peux faire sur MED_ETUD">
              <div><span class="welcome-highlight-icon">◫</span><span><strong>Collaborer</strong><small>Rejoins un groupe ou lance un projet.</small></span></div>
              <div><span class="welcome-highlight-icon">✓</span><span><strong>Avancer</strong><small>Retrouve tes tâches et tes échéances.</small></span></div>
              <div><span class="welcome-highlight-icon">?</span><span><strong>Demander de l’aide</strong><small>Échange avec la communauté étudiante.</small></span></div>
            </div>
          </div>
          <figure class="welcome-image"><img src="/static/med-etud-students.png" alt="Des étudiants noirs de différentes filières réunis avant les cours" loading="eager"><figcaption>Un espace commun pour tes projets et ta vie étudiante.</figcaption></figure>
        </main>
        <button type="button" class="welcome-logout" id="welcomeLogout">Se déconnecter</button>
      </section>

      <div class="app" id="appShell" hidden>
        <aside class="sidebar">
          <div class="brand"><span class="brand-mark">M</span> MED_ETUD</div>
          <nav class="nav" aria-label="Navigation principale">
            <button class="active" data-view="dashboard">⌂ &nbsp; Tableau de bord</button>
            <button data-view="groups">◫ &nbsp; Mes groupes</button>
            <button data-view="discoverGroups">⌕ &nbsp; Découvrir des groupes</button>
            <button data-view="people">◎ &nbsp; Trouver mon équipe</button>
            <button data-view="tasks">✓ &nbsp; Mes tâches</button>
            <button data-view="messages">◌ &nbsp; Messages privés</button>
            <button data-view="help">? &nbsp; Aide</button>
            <button data-view="publications">◈ &nbsp; Publications et vie étudiante</button>
            <button data-view="resources">▧ &nbsp; Ressources</button>
            <button data-view="calendar">□ &nbsp; Calendrier</button>
            <button data-view="settings">⚙ &nbsp; Paramètres</button>
            <button data-view="admin" id="adminNav" hidden>⚙ &nbsp; Administration</button>
          </nav>
          <div class="profile-mini"><div class="avatar" id="profileAvatar">?</div><div class="profile-copy"><strong id="profileName">Étudiant</strong><small id="profileEmail"></small></div></div>
          <button type="button" class="logout-btn" id="logoutButton">Se déconnecter</button>
        </aside>

        <main class="main">
          <header class="topbar">
            <h1 id="pageTitle">Tableau de bord</h1>
            <div class="top-actions">
              <div class="search-wrap"><input type="search" id="search" placeholder="Rechercher"></div>
              <button class="icon-btn" id="notifications" aria-label="Notifications non lues">♢ <span id="notifBadge" hidden>0</span></button>
            </div>
          </header>

          <section id="dashboard" class="view active">
            <div class="grid dashboard-grid">
              <div>
                <article class="card dashboard-hero">
                  <div class="dashboard-greeting">
                    <div class="dashboard-greeting-avatar" id="dashboardGreetingAvatar">?</div>
                    <div><small>TON ESPACE ÉTUDIANT</small><h2>Bonjour, <span id="greetingName">…</span></h2><p id="greetingText">Tes groupes, tâches et prochaines échéances apparaîtront ici.</p></div>
                  </div>
                  <div class="dashboard-hero-profile"><div class="dashboard-completion-ring" id="dashboardCompletionRing"><strong id="dashboardCompletion">0 %</strong></div><div><small>Profil complété</small><button class="hero-link" type="button" data-open-profile>Compléter mon profil <span aria-hidden="true">→</span></button></div></div>
                </article>

                <div class="stats">
                  <div class="stat"><strong id="groupCount">0</strong><span>Groupes rejoints</span></div>
                  <div class="stat"><strong id="taskCount">0</strong><span>Tâches attribuées</span></div>
                  <div class="stat"><strong id="deadlineCount">0</strong><span>Échéances à venir</span></div>
                </div>

                <article class="card">
                  <div class="section-head"><h2>Mes tâches</h2><button class="icon-btn" id="viewAllTasks">Voir tout</button></div>
                  <div class="task-list" id="taskList"></div>
                </article>
                <article class="card"><div class="section-head"><h2>À traiter en priorité</h2></div><div id="priorityTasksList"></div></article>
              </div>

              <aside class="right dashboard-aside">
                <article class="card">
                  <div class="section-head"><h3>À venir</h3></div>
                  <div class="events" id="eventsList"></div>
                </article>
                <article class="card">
                  <div class="section-head"><h3>Mes groupes</h3></div>
                  <div id="recentGroups"></div>
                </article>
                <article class="card" id="notificationsCard">
                  <div class="section-head"><h3>Notifications récentes</h3></div>
                  <div id="notificationsList"></div>
                </article>
              </aside>
            </div>
          </section>

          <section id="groups" class="view">
            <article class="card"><div class="section-head"><h2>Mes groupes</h2><button class="primary" type="button" data-view-link="discoverGroups">Trouver un groupe</button></div><div id="groupsList"></div></article>
          </section>
          <section id="discoverGroups" class="view">
            <article class="card" id="groupDiscoveryPanel"><div class="section-head"><div><h2>Découvrir les groupes</h2><p class="muted">Des projets concrets qui recrutent des étudiants.</p></div><button class="primary" id="newGroupButton" type="button">Créer un groupe</button></div>
              <form id="groupSearchForm" class="discovery-filters"><input name="q" type="search" placeholder="Nom, objectif, projet"><input name="subject" placeholder="Matière ou domaine"><input name="filiere" placeholder="Filière"><input name="skill" placeholder="Compétence recherchée"><select name="level"><option value="">Tous les niveaux</option><option>L1</option><option>L2</option><option>L3</option><option>M1</option><option>M2</option><option>Doctorat</option><option>Autre</option></select><label><input name="recruiting" type="checkbox" checked> Recrutement ouvert</label><button class="icon-btn" type="submit">Filtrer</button></form>
              <div id="groupDiscoveryStatus" class="muted" role="status"></div><div id="groupDiscoveryList" class="discovery-grid"></div>
            </article>
            <form id="groupCreateForm" class="card profile-form" hidden>
              <input type="hidden" name="group_id" value="">
              <div class="section-head"><div><h2>Créer un groupe de travail</h2><p class="muted">Le créateur devient propriétaire et peut gérer l’équipe.</p></div></div>
              <div class="profile-form-grid">
                <div class="profile-control profile-control-wide"><label>Nom du groupe</label><input name="name" required maxlength="80" placeholder="Ex. Équipe projet biologie"></div>
                <div class="profile-control profile-control-wide"><label>Objectif du groupe</label><textarea name="objective" maxlength="2000" rows="3" placeholder="Que souhaitez-vous réaliser ensemble ?"></textarea></div>
                <details class="profile-control-wide group-advanced">
                  <summary>Options facultatives</summary>
                  <div class="profile-form-grid">
                    <div class="profile-control"><label>Nom du projet</label><input name="project_name" maxlength="120"></div>
                    <div class="profile-control"><label>Matière ou domaine</label><input name="subject" maxlength="80"></div>
                    <div class="profile-control"><label>Filière souhaitée</label><input name="filiere" maxlength="80"></div>
                    <div class="profile-control"><label>Niveau souhaité</label><select name="preferred_level"><option value="">Tous niveaux</option><option>L1</option><option>L2</option><option>L3</option><option>M1</option><option>M2</option><option>Doctorat</option><option>Autre</option></select></div>
                    <div class="profile-control"><label>Nombre maximal de membres</label><input name="max_members" type="number" min="2" max="40" value="8" required></div>
                    <div class="profile-control profile-control-wide"><label>Description</label><textarea name="description" maxlength="2000" rows="3"></textarea></div>
                    <div class="profile-control"><label>Compétences recherchées</label><input name="skills_wanted" placeholder="Python, design, rédaction"></div>
                    <div class="profile-control"><label>Échéance</label><input name="deadline" type="date"></div>
                    <div class="profile-control"><label>Visibilité</label><select name="visibility"><option value="public">Public</option><option value="private">Privé (sur invitation)</option></select></div>
                    <label class="profile-control"><span><input name="recruitment_open" type="checkbox" checked> Recrutement ouvert</span></label>
                  </div>
                </details>
              </div><p id="groupCreateError" class="form-error" role="alert"></p><div class="profile-form-actions"><button class="icon-btn" type="button" id="cancelGroupCreate">Annuler</button><button class="primary" type="submit">Créer le groupe</button></div>
            </form>
            <article id="groupDetail" class="card" hidden></article>
          </section>
          <section id="people" class="view">
            <article class="card"><div class="section-head"><div><h2>Trouver mon équipe</h2><p class="muted">Des profils publics et des recommandations fondées sur des critères renseignés.</p></div></div>
              <div class="people-tabs"><button class="primary" type="button" data-people-mode="recommendations">Pour vous</button><button class="icon-btn" type="button" data-people-mode="search">Tous les profils</button><button class="icon-btn" type="button" data-people-mode="connections">Mes demandes et connexions</button></div>
              <form id="peopleSearchForm" class="discovery-filters"><input name="q" type="search" placeholder="Nom, filière, compétence"><input name="school" placeholder="Établissement"><input name="faculty" placeholder="Faculté"><input name="filiere" placeholder="Filière"><input name="skill" placeholder="Compétence"><input name="interest" placeholder="Centre d’intérêt"><input name="project_type" placeholder="Type de projet"><select name="level"><option value="">Tous niveaux</option><option>L1</option><option>L2</option><option>L3</option><option>M1</option><option>M2</option><option>Doctorat</option><option>Autre</option></select><button class="icon-btn" type="submit">Rechercher</button></form>
              <div id="peopleStatus" class="muted" role="status"></div><div id="peopleList" class="discovery-grid"></div><div id="connectionLists" hidden></div>
            </article>
          </section>
          <section id="tasks" class="view"><article class="card"><div class="section-head"><div><h2>Mes tâches</h2><p class="muted">Tâches qui vous sont affectées dans vos groupes.</p></div><div class="task-filters"><select id="myTasksStatus"><option value="">Tous les statuts</option><option value="todo">À faire</option><option value="doing">En cours</option><option value="review">En révision</option><option value="done">Terminées</option></select><select id="myTasksPriority"><option value="">Toutes les priorités</option><option value="urgent">Urgente</option><option value="high">Élevée</option><option value="normal">Normale</option><option value="low">Faible</option></select><select id="myTasksSort"><option value="due_asc">Échéance proche</option><option value="created_desc">Récemment créée</option><option value="created_asc">Plus ancienne</option><option value="due_desc">Échéance lointaine</option></select></div></div><div class="task-list" id="taskListPage"></div></article></section>
          <section id="publications" class="view">
            <article class="card">
              <div class="section-head"><div><h2>Publications et vie étudiante</h2><p class="muted">Partage des informations utiles ou découvre les publications des autres étudiants.</p></div></div>
              <nav id="publicationTabs" class="section-tabs" aria-label="Publications et vie étudiante">
                <button class="section-tab active" type="button" data-publication-pane="browse" aria-pressed="true">Voir les publications</button>
                <button class="section-tab" type="button" data-publication-pane="compose" aria-pressed="false">Publier</button>
              </nav>
              <div id="publicationBrowsePane" class="publication-pane">
                <div id="publicationStatus" class="muted" role="status"></div>
                <div id="publicationFeed" class="publication-feed"></div>
              </div>
              <div id="publicationComposePane" class="publication-pane" hidden>
                <form id="publicationForm" class="publication-form">
                  <textarea name="body" rows="3" maxlength="4000" required minlength="3" placeholder="Partager une idée, une opportunité ou une ressource utile…"></textarea>
                  <input name="link_url" type="url" maxlength="500" placeholder="Lien facultatif https://...">
                  <p id="publicationError" class="form-error" role="alert"></p>
                  <div class="profile-form-actions"><button class="primary" type="submit">Publier</button></div>
                </form>
              </div>
            </article>
          </section>
          <section id="messages" class="view">
            <article class="card">
              <div class="section-head"><div><h2>Messages privés</h2><p class="muted">Conversations autorisées avec vos connexions ou membres de groupes partagés.</p></div></div>
              <div class="dm-layout">
                <aside class="dm-conversations"><h3>Contacts et conversations</h3><div id="dmConversationList"></div></aside>
                <div class="dm-thread"><h3 id="dmThreadTitle">Sélectionnez une conversation</h3><div id="dmMessages" class="dm-messages"></div><form id="dmForm" hidden><input name="body" maxlength="4000" required placeholder="Votre message"><button class="primary" type="submit">Envoyer</button></form></div>
              </div>
            </article>
          </section>
          <section id="help" class="view">
            <article class="card">
              <div class="section-head"><div><h2>Demander de l’aide</h2><p class="muted">Décrivez le blocage de votre groupe. Les étudiants extérieurs du niveau choisi recevront une notification.</p></div></div>
              <form id="helpRequestForm" class="profile-form">
                <div class="profile-form-grid">
                  <div class="profile-control"><label for="helpGroup">Groupe concerné</label><select id="helpGroup" name="group_id" required><option value="">Choisir un groupe</option></select></div>
                  <div class="profile-control"><label for="helpLevel">Niveau des étudiants recherchés</label><select id="helpLevel" name="target_level" required><option value="">Choisir un niveau</option><option>L1</option><option>L2</option><option>L3</option><option>M1</option><option>M2</option><option>Doctorat</option><option>Autre</option></select></div>
                  <div class="profile-control profile-control-wide"><label for="helpTitle">Sur quoi êtes-vous bloqués ?</label><input id="helpTitle" name="title" required minlength="4" maxlength="120" placeholder="Ex. Comprendre les résultats de notre enquête"></div>
                  <div class="profile-control profile-control-wide"><label for="helpDescription">Décrivez le problème</label><textarea id="helpDescription" name="description" required minlength="10" maxlength="2000" rows="4" placeholder="Expliquez ce que vous avez essayé et le type de conseil qui vous aiderait."></textarea></div>
                </div>
                <p id="helpError" class="form-error" role="alert"></p>
                <div class="profile-form-actions"><button class="primary" type="submit">Envoyer la demande</button></div>
              </form>
              <div id="helpStatus" class="muted" role="status"></div>
              <div id="helpRequestFeed" class="help-request-feed"></div>
            </article>
          </section>
          <section id="resources" class="view">
            <article class="card">
              <div class="section-head"><div><h2>Bibliothèque de ressources</h2><p class="muted">Documents, liens et supports pédagogiques publiés par les étudiants.</p></div><button class="primary" id="resourceFormToggle" type="button">Partager une ressource</button></div>
              <form id="resourceSearchForm" class="discovery-filters">
                <input name="q" type="search" placeholder="Titre, matière, mot-clé">
                <input name="subject" placeholder="Matière">
                <input name="filiere" placeholder="Filière">
                <select name="level"><option value="">Tous les niveaux</option><option>L1</option><option>L2</option><option>L3</option><option>M1</option><option>M2</option><option>Doctorat</option><option>Autre</option></select>
                <button class="icon-btn" type="submit">Rechercher</button>
              </form>
              <form id="resourceUploadForm" class="profile-form" hidden>
                <div class="profile-form-grid">
                  <div class="profile-control"><label>Titre</label><input name="title" required minlength="2" maxlength="140"></div>
                  <div class="profile-control"><label>Type</label><select name="kind" required><option>Cours</option><option>TD</option><option>TP</option><option>Résumé</option><option>Fiche de révision</option><option>Ancien examen</option><option>Corrigé</option><option>Document</option><option>Lien</option><option>Vidéo</option><option>Tutoriel</option></select></div>
                  <div class="profile-control"><label>Matière</label><input name="subject" maxlength="80"></div>
                  <div class="profile-control"><label>Filière</label><input name="filiere" maxlength="80"></div>
                  <div class="profile-control"><label>Niveau</label><input name="level" maxlength="40"></div>
                  <div class="profile-control"><label>Mots-clés</label><input name="tags" placeholder="Python, bases de données"></div>
                  <div class="profile-control profile-control-wide"><label>Description</label><textarea name="description" maxlength="4000" rows="3"></textarea></div>
                  <div class="profile-control profile-control-wide"><label>Fichier</label><input name="file" type="file" required><small>PDF, Office, texte, image ou ZIP, 8 Mo maximum.</small></div>
                </div>
                <p id="resourceUploadError" class="form-error" role="alert"></p>
                <div class="profile-form-actions"><button class="icon-btn" type="button" id="resourceFormCancel">Annuler</button><button class="primary" type="submit">Publier</button></div>
              </form>
              <div id="resourceLibraryStatus" class="muted" role="status"></div>
              <div id="resourceLibraryList" class="resource-list"></div>
            </article>
          </section>

          <section id="calendar" class="view">
            <article class="card">
              <div class="section-head"><div><h2>Calendrier collaboratif</h2><p class="muted">Vos événements personnels, réunions de groupe et échéances.</p></div><button class="primary" id="calendarFormToggle" type="button">Nouvel événement</button></div>
              <form id="calendarForm" class="profile-form" hidden>
                <div class="profile-form-grid">
                  <div class="profile-control"><label>Titre</label><input name="title" required minlength="2" maxlength="140"></div>
                  <div class="profile-control"><label>Type</label><select name="kind"><option value="reunion">Réunion</option><option value="travail">Travail</option><option value="echeance">Échéance</option><option value="autre">Autre</option></select></div>
                  <div class="profile-control"><label>Début</label><input name="starts_at" type="datetime-local" required></div>
                  <div class="profile-control"><label>Fin</label><input name="ends_at" type="datetime-local"></div>
                  <div class="profile-control"><label for="calendarReminderPreset">Rappel de l’événement</label><select id="calendarReminderPreset" name="reminder_preset"><option value="">Sans rappel</option><option value="2">2 jours avant</option><option value="3">3 jours avant</option><option value="custom">Choisir une date</option></select><small id="calendarReminderPreview"></small></div>
                  <div class="profile-control" id="calendarCustomReminder" hidden><label for="calendarReminderAt">Date et heure du rappel</label><input id="calendarReminderAt" name="reminder_at" type="datetime-local"></div>
                  <div class="profile-control profile-control-wide"><label>Description</label><textarea name="description" maxlength="1000" rows="3"></textarea></div>
                </div>
                <p id="calendarFormError" class="form-error" role="alert"></p>
                <div class="profile-form-actions"><button class="icon-btn" type="button" id="calendarFormCancel">Annuler</button><button class="primary" type="submit">Ajouter</button></div>
              </form>
              <div class="calendar-toolbar" aria-label="Affichage du calendrier">
                <button class="icon-btn" type="button" data-calendar-mode="day">Jour</button>
                <button class="icon-btn" type="button" data-calendar-mode="week">Semaine</button>
                <button class="icon-btn" type="button" data-calendar-mode="month">Mois</button>
              </div>
              <div id="calendarStatus" class="muted" role="status"></div>
              <div id="calendarList" class="calendar-list"></div>
            </article>
          </section>

          <section id="admin" class="view">
            <article class="card">
              <div class="section-head"><div><h2>Administration et modération</h2><p class="muted">Accès réservé aux comptes administrateurs.</p></div></div>
              <div id="adminStats" class="stats"></div>
              <div class="profile-form-grid">
                <article class="card"><h3>Utilisateurs</h3><form id="adminUserSearch" class="discovery-filters"><input name="q" placeholder="Nom ou e-mail"><button class="icon-btn" type="submit">Rechercher</button></form><div id="adminUsers"></div></article>
                <article class="card"><h3>Signalements</h3><div id="adminReports"></div></article>
              </div>
              <article class="card"><h3>Historique administrateur</h3><div id="adminAudit"></div></article>
            </article>
          </section>

          <section id="assistant" class="view">
            <article class="card">
              <div class="section-head"><div><h2>Apprendre à utiliser la plateforme</h2><p class="muted">Choisis une rubrique pour comprendre à quoi elle sert, comment l’utiliser et quand elle peut t’aider.</p></div></div>
              <nav id="siteGuideTabs" class="guide-tabs" aria-label="Rubriques du site"></nav>
              <div id="siteGuideContent" class="guide-content" aria-live="polite"></div>
            </article>
          </section>

          <section id="settings" class="view">
            <nav id="settingsMenu" class="section-tabs settings-menu" aria-label="Sections des paramètres">
              <button class="section-tab active" type="button" data-settings-tab="profile" aria-pressed="true">Mon profil</button>
              <button class="section-tab" type="button" data-settings-tab="preferences" aria-pressed="false">Préférences</button>
              <button class="section-tab" type="button" data-settings-guide>Apprendre à utiliser la plateforme</button>
            </nav>
          <section id="profile" class="settings-panel" data-settings-panel="profile">
            <article class="card profile-header-card">
              <div class="profile-header-row">
                <div class="profile-identity"><div class="avatar profile-avatar-large" id="profileAvatarLarge">?</div><div><p class="profile-kicker">PROFIL ÉTUDIANT</p><h2 id="profileDisplayName">Mon profil</h2><p id="profileSubtitle" class="muted">Complétez les informations qui vous aideront à trouver des coéquipiers.</p></div></div>
                <div class="profile-actions"><button class="icon-btn" id="avatarButton" type="button">Ajouter une photo</button><input id="avatarInput" type="file" accept="image/png,image/jpeg,image/webp,image/gif" hidden><button class="primary" id="editProfileButton" type="button">Modifier le profil</button></div>
              </div>
              <div class="profile-completion"><div class="completion-line"><span>Complétion du profil</span><strong id="profileCompletionText">0 %</strong></div><div class="progress"><span id="profileProgress"></span></div><small id="profileCompletionHint" class="muted"></small></div>
            </article>
              <article class="card" id="passwordCard">
                <div class="section-head"><div><h2>Sécurité du compte</h2><p class="muted">Modifier votre mot de passe ferme les sessions actives.</p></div></div>
                <form id="passwordForm" class="profile-form-grid">
                  <div class="profile-control"><label>Mot de passe actuel</label><input name="current_password" type="password" autocomplete="current-password" required maxlength="128"></div>
                  <div class="profile-control"><label>Nouveau mot de passe</label><input name="new_password" type="password" autocomplete="new-password" minlength="10" maxlength="128" required></div>
                  <p class="form-error profile-control-wide" id="passwordError" role="alert"></p>
                  <div class="profile-form-actions profile-control-wide"><button class="primary" type="submit">Modifier le mot de passe</button></div>
                </form>
              </article>
            <div id="profileDisplay" class="profile-grid"></div>
            <form id="profileForm" class="card profile-form" hidden>
              <div class="section-head"><div><h2>Modifier mon profil</h2><p class="muted">Les champs sont facultatifs, sauf votre nom.</p></div></div>
              <div class="profile-form-grid">
                <div class="profile-control"><label for="profileNameInput">Nom complet</label><input id="profileNameInput" name="name" maxlength="80" required><p class="field-error" data-profile-error="name"></p></div>
                <div class="profile-control"><label for="profileSchool">Établissement</label><input id="profileSchool" name="school" maxlength="120" placeholder="Université ou école"><p class="field-error" data-profile-error="school"></p></div>
                <div class="profile-control"><label for="profileFaculty">Faculté</label><input id="profileFaculty" name="faculty" maxlength="120"><p class="field-error" data-profile-error="faculty"></p></div>
                <div class="profile-control"><label for="profileFiliere">Filière</label><input id="profileFiliere" name="filiere" maxlength="80" placeholder="Ex. Informatique"><p class="field-error" data-profile-error="filiere"></p></div>
                <div class="profile-control"><label for="profileLevel">Niveau d’étude</label><select id="profileLevel" name="level"><option value="">À préciser</option><option>L1</option><option>L2</option><option>L3</option><option>M1</option><option>M2</option><option>Doctorat</option><option>Autre</option></select></div>
                <div class="profile-control"><label for="profileGoal">Objectif académique</label><input id="profileGoal" name="focus_goal" maxlength="220" placeholder="Ce que vous souhaitez accomplir"><p class="field-error" data-profile-error="focus_goal"></p></div>
                <div class="profile-control profile-control-wide"><label for="profileBio">Biographie</label><textarea id="profileBio" name="bio" maxlength="500" rows="3" placeholder="Présentez-vous en quelques phrases"></textarea><p class="field-error" data-profile-error="bio"></p></div>
                <div class="profile-control"><label for="profileSkills">Compétences</label><input id="profileSkills" name="skills" list="skillSuggestions" placeholder="Python, rédaction, design"><datalist id="skillSuggestions"><option value="Programmation"><option value="Analyse de données"><option value="Rédaction"><option value="Design"><option value="Présentation"></datalist><small>Séparez les compétences par des virgules.</small><p class="field-error" data-profile-error="skills"></p></div>
                <div class="profile-control"><label for="profileInterests">Centres d’intérêt</label><input id="profileInterests" name="interests" list="interestSuggestions" placeholder="IA, environnement, santé"><datalist id="interestSuggestions"><option value="Intelligence artificielle"><option value="Environnement"><option value="Santé"><option value="Entrepreneuriat"><option value="Sciences sociales"></datalist><small>Séparez les intérêts par des virgules.</small><p class="field-error" data-profile-error="interests"></p></div>
                <div class="profile-control"><label for="profileProjects">Types de projets recherchés</label><input id="profileProjects" name="project_types" placeholder="Projet de recherche, hackathon"><small>Séparez les types de projets par des virgules.</small><p class="field-error" data-profile-error="project_types"></p></div>
                <div class="profile-control"><label for="profileAvailability">Disponibilités</label><input id="profileAvailability" name="availability" maxlength="200" placeholder="Ex. soirs en semaine, samedi"><p class="field-error" data-profile-error="availability"></p></div>
                <fieldset class="profile-control profile-control-wide preference-fieldset"><legend>Préférences de collaboration</legend>
                  <label><input type="checkbox" name="collaboration_preferences" value="remote"> À distance</label>
                  <label><input type="checkbox" name="collaboration_preferences" value="in_person"> En présentiel</label>
                  <label><input type="checkbox" name="collaboration_preferences" value="hybrid"> Hybride</label>
                  <label><input type="checkbox" name="collaboration_preferences" value="structured"> Organisation structurée</label>
                  <label><input type="checkbox" name="collaboration_preferences" value="flexible"> Organisation flexible</label>
                  <label><input type="checkbox" name="collaboration_preferences" value="weekly"> Point hebdomadaire</label>
                  <label><input type="checkbox" name="collaboration_preferences" value="async"> Travail asynchrone</label>
                </fieldset>
                <label class="profile-control profile-control-wide discovery-optout"><input type="checkbox" name="discoverable"> Apparaître dans la découverte et les recommandations d’étudiants</label>
              </div>
              <div class="profile-form-actions"><button class="icon-btn" id="cancelProfileEdit" type="button">Annuler</button><button class="primary" type="submit">Enregistrer le profil</button></div>
            </form>
            <p class="form-error" id="profileError" role="alert"></p><p class="profile-success" id="profileSuccess" role="status"></p>
          </section>
          <section class="settings-panel" data-settings-panel="preferences" hidden>
            <article class="card settings-card">
              <div class="section-head"><div><h2>Apparence</h2><p class="muted">Personnalise les couleurs de ton espace. Ton choix est mémorisé sur cet appareil.</p></div></div>
              <section class="settings-group">
                <h3>Mode d’affichage</h3>
                <div class="theme-options" role="group" aria-label="Mode d’affichage">
                  <button class="theme-option active" type="button" data-theme-mode="light" aria-pressed="true"><span class="theme-preview theme-preview-light" aria-hidden="true"></span>Clair</button>
                  <button class="theme-option" type="button" data-theme-mode="dark" aria-pressed="false"><span class="theme-preview theme-preview-dark" aria-hidden="true"></span>Sombre</button>
                </div>
              </section>
              <section class="settings-group">
                <h3>Couleur de l’application</h3>
                <div class="theme-swatches" role="group" aria-label="Couleur de l’application">
                  <button class="theme-swatch active" type="button" data-theme-accent="blue" aria-label="Bleu" aria-pressed="true"><span style="--swatch:#3159c7"></span>Bleu</button>
                  <button class="theme-swatch" type="button" data-theme-accent="violet" aria-label="Violet" aria-pressed="false"><span style="--swatch:#7050c8"></span>Violet</button>
                  <button class="theme-swatch" type="button" data-theme-accent="green" aria-label="Vert" aria-pressed="false"><span style="--swatch:#267451"></span>Vert</button>
                  <button class="theme-swatch" type="button" data-theme-accent="yellow" aria-label="Jaune" aria-pressed="false"><span style="--swatch:#b87900"></span>Jaune</button>
                </div>
              </section>
              <p id="themeStatus" class="profile-success" role="status" aria-live="polite"></p>
            </article>
          </section>
          </section>
        </main>
      </div>

      <div class="toast" id="toast"></div>
      <script src="/static/app.js"></script>
    </body>
    </html>
    """


@app.get("/", response_class=HTMLResponse)
async def home():
    return page_html()


@app.get("/app", response_class=HTMLResponse)
async def workspace(request: Request):
    with session() as conn:
        user = auth.resolve_session(conn, request.cookies.get(SESSION_COOKIE))
    if not user:
        return RedirectResponse(url="/?next=%2Fapp", status_code=303)
    return page_html()


@app.get("/app/groupes/{group_id}", response_class=HTMLResponse)
async def group_workspace(group_id: int, request: Request):
    with session() as conn:
        user = auth.resolve_session(conn, request.cookies.get(SESSION_COOKIE))
    if not user:
        destination = str(request.url.path)
        if request.url.query:
            destination += "?" + request.url.query
        return RedirectResponse(url="/?next=" + quote(destination, safe=""), status_code=303)
    return page_html()


@app.get("/health")
async def health():
    with session() as conn:
        row = one(conn, "SELECT COUNT(*) AS count FROM users")
    return {"status": "ok", "users": row["count"]}
