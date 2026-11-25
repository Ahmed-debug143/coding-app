from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from aula.db import init_db, session, one


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Campusia", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <!doctype html>
    <html lang="fr">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Campusia — Tableau de bord</title>
      <link rel="stylesheet" href="/static/styles.css">
    </head>
    <body>
      <div class="app">
        <aside class="sidebar">
          <div class="brand"><span class="brand-mark">C</span> Campusia</div>
          <nav class="nav" aria-label="Navigation principale">
            <button class="active" data-view="dashboard">⌂ &nbsp; Tableau de bord</button>
            <button data-view="groups">◫ &nbsp; Mes groupes</button>
            <button data-view="tasks">✓ &nbsp; Mes tâches</button>
            <button data-view="resources">▧ &nbsp; Ressources</button>
          </nav>
          <div class="profile-mini"><div class="avatar">AM</div><div><strong>Ahmed Martin</strong><small>Étudiant · L3</small></div></div>
        </aside>

        <main class="main">
          <header class="topbar">
            <h1 id="pageTitle">Tableau de bord</h1>
            <div class="top-actions">
              <div class="search-wrap"><input type="search" id="search" placeholder="Rechercher"></div>
              <button class="icon-btn" id="notifications" aria-label="Notifications">♢ <span id="notifBadge">3</span></button>
              <button class="primary" id="openTask">＋ Nouvelle tâche</button>
            </div>
          </header>

          <section id="dashboard" class="view active">
            <div class="grid">
              <div>
                <article class="card hero">
                  <small>PROJET EN COURS</small>
                  <h2>Data Science appliquée à l’éducation</h2>
                  <p>Votre équipe avance sur les résultats de l’analyse.</p>
                  <div class="progress"><span></span></div>
                </article>

                <div class="stats">
                  <div class="stat"><strong>68%</strong><span>Progression du projet</span></div>
                  <div class="stat"><strong>12</strong><span>Tâches terminées</span></div>
                  <div class="stat"><strong>5</strong><span>Collaborateurs</span></div>
                </div>

                <article class="card">
                  <div class="section-head"><h2>À faire cette semaine</h2><button class="icon-btn" id="viewAllTasks">Voir tout</button></div>
                  <div class="task-list" id="taskList"></div>
                </article>
              </div>

              <aside class="right">
                <article class="card">
                  <div class="section-head"><h3>Calendrier</h3><span>Novembre</span></div>
                  <div class="events">
                    <div class="event"><div class="date">25<span>NOV</span></div><div><strong>Réunion de groupe</strong><small>14:30 · Salle virtuelle</small></div></div>
                    <div class="event"><div class="date">27<span>NOV</span></div><div><strong>Rendu intermédiaire</strong><small>Avant 18:00</small></div></div>
                    <div class="event"><div class="date">02<span>DÉC</span></div><div><strong>Révision de statistiques</strong><small>10:00 · Amphi B</small></div></div>
                  </div>
                </article>
                <article class="card">
                  <div class="section-head"><h3>Mes groupes</h3><button class="icon-btn" id="openGroup">＋</button></div>
                  <div class="group"><div class="group-icon">DS</div><div><strong>Data Science</strong><small style="color:#829189">5 membres</small></div></div>
                  <div class="group"><div class="group-icon">ST</div><div><strong>Statistiques L3</strong><small style="color:#829189">8 membres</small></div></div>
                </article>
              </aside>
            </div>
          </section>

          <section id="groups" class="view">
            <article class="card"><div class="section-head"><h2>Mes groupes</h2><button class="primary" id="openGroupPage">＋ Créer un groupe</button></div><div id="groupsList"><div class="group"><div class="group-icon">DS</div><div><strong>Data Science</strong><small style="color:#829189">5 membres · Projet en cours</small></div></div><div class="group"><div class="group-icon">ST</div><div><strong>Statistiques L3</strong><small style="color:#829189">8 membres · Groupe actif</small></div></div></div></article>
          </section>
          <section id="tasks" class="view"><article class="card"><div class="section-head"><h2>Mes tâches</h2><button class="primary" id="openTaskPage">＋ Nouvelle tâche</button></div><div class="task-list" id="taskListPage"></div></article></section>
          <section id="resources" class="view"><article class="card"><div class="section-head"><h2>Bibliothèque de ressources</h2><button class="primary" id="addResource">＋ Ajouter</button></div><div id="resourcesList" class="resource-list"><article class="resource"><strong>Formulaire de régression</strong><small>PDF · Statistiques</small></article><article class="resource"><strong>Notes du cours Data Science</strong><small>Document · Data Science</small></article></div></article></section>
        </main>
      </div>

      <div class="modal-backdrop" id="taskModal">
        <div class="modal"><h2>Créer une tâche</h2>
          <form id="taskForm">
            <input name="title" required placeholder="Titre de la tâche">
            <textarea name="description" placeholder="Description"></textarea>
            <input name="date" type="date">
            <div class="modal-actions"><button type="button" class="icon-btn close-modal">Annuler</button><button class="primary">Ajouter</button></div>
          </form>
        </div>
      </div>

      <div class="modal-backdrop" id="groupModal">
        <div class="modal"><h2>Créer un groupe</h2>
          <form id="groupForm">
            <input name="name" required placeholder="Nom du groupe">
            <textarea name="description" placeholder="Objectif du groupe"></textarea>
            <div class="modal-actions"><button type="button" class="icon-btn close-modal">Annuler</button><button class="primary">Créer</button></div>
          </form>
        </div>
      </div>

      <div class="modal-backdrop" id="resourceModal">
        <div class="modal"><h2>Ajouter une ressource</h2>
          <form id="resourceForm">
            <input name="title" required placeholder="Titre de la ressource">
            <input name="category" required placeholder="Cours ou catégorie">
            <div class="modal-actions"><button type="button" class="icon-btn close-modal">Annuler</button><button class="primary">Ajouter</button></div>
          </form>
        </div>
      </div>

      <div class="toast" id="toast"></div>
      <script src="/static/app.js"></script>
    </body>
    </html>
    """


@app.get("/health")
async def health():
    with session() as conn:
        row = one(conn, "SELECT COUNT(*) AS count FROM users")
    return {"status": "ok", "users": row["count"]}
