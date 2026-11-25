const state = {
  tasks: [
    { name: 'Revoir les statistiques descriptives', meta: 'Échéance · demain', tag: 'Urgent', done: false },
    { name: 'Partager les notes du cours', meta: 'Groupe · Data Science', tag: 'Ressource', done: true },
    { name: 'Préparer la réunion de projet', meta: 'Aujourd’hui · 14:30', tag: 'Réunion', done: false }
  ],
  groups: [],
  resources: []
};

function renderTasks() {
  const template = state.tasks.map((task, index) => `
    <div class="task ${task.done ? 'done' : ''}">
      <button class="check" type="button" aria-label="Changer l’état de la tâche" data-task="${index}"></button>
      <div><div class="task-name">${escapeHtml(task.name)}</div><small>${escapeHtml(task.meta)}</small></div>
      <span class="tag">${escapeHtml(task.tag)}</span>
    </div>`).join('');
  document.querySelectorAll('#taskList, #taskListPage').forEach(list => list.innerHTML = template);
}

function escapeHtml(value) {
  const element = document.createElement('div');
  element.textContent = value;
  return element.innerHTML;
}

function openModal(modalId) {
  document.querySelector(modalId).classList.add('open');
}

function closeModal(modal) {
  modal.classList.remove('open');
}

function toast(text) {
  const element = document.querySelector('#toast');
  element.textContent = text;
  element.classList.add('show');
  clearTimeout(window._toast);
  window._toast = setTimeout(() => element.classList.remove('show'), 2300);
}

function showView(viewId, title) {
  document.querySelectorAll('.nav button').forEach(button => button.classList.toggle('active', button.dataset.view === viewId));
  document.querySelectorAll('.view').forEach(view => view.classList.remove('active'));
  document.querySelector('#' + viewId).classList.add('active');
  document.querySelector('#pageTitle').textContent = title;
}

renderTasks();

document.querySelectorAll('.nav button').forEach(button => {
  button.addEventListener('click', () => showView(button.dataset.view, button.textContent.replace(/^\s*[⌂◫✓▧]\s*/, '').trim()));
});

document.addEventListener('click', event => {
  const check = event.target.closest('[data-task]');
  if (!check) return;
  const index = Number(check.dataset.task);
  state.tasks[index].done = !state.tasks[index].done;
  renderTasks();
  toast(state.tasks[index].done ? 'Tâche terminée' : 'Tâche remise à faire');
});

['openTask', 'openTaskPage'].forEach(id => {
  const button = document.querySelector('#' + id);
  if (button) button.addEventListener('click', () => openModal('#taskModal'));
});

['openGroup', 'openGroupPage'].forEach(id => {
  const button = document.querySelector('#' + id);
  if (button) button.addEventListener('click', () => openModal('#groupModal'));
});

const addResource = document.querySelector('#addResource');
if (addResource) addResource.addEventListener('click', () => openModal('#resourceModal'));

document.querySelectorAll('.close-modal').forEach(button => {
  button.addEventListener('click', () => closeModal(button.closest('.modal-backdrop')));
});

document.querySelectorAll('.modal-backdrop').forEach(modal => {
  modal.addEventListener('click', event => {
    if (event.target === modal) closeModal(modal);
  });
});

document.addEventListener('keydown', event => {
  if (event.key === 'Escape') document.querySelectorAll('.modal-backdrop.open').forEach(closeModal);
});

document.querySelector('#taskForm').addEventListener('submit', event => {
  event.preventDefault();
  const data = new FormData(event.target);
  state.tasks.unshift({
    name: data.get('title'),
    meta: data.get('date') ? 'Échéance · ' + data.get('date') : 'À planifier',
    tag: 'Nouvelle',
    done: false
  });
  renderTasks();
  event.target.reset();
  closeModal(document.querySelector('#taskModal'));
  toast('Tâche ajoutée');
});

document.querySelector('#groupForm').addEventListener('submit', event => {
  event.preventDefault();
  const data = new FormData(event.target);
  const name = data.get('name').trim();
  const item = document.createElement('div');
  item.className = 'group';
  item.innerHTML = `<div class="group-icon">${escapeHtml(name.slice(0, 2).toUpperCase())}</div><div><strong>${escapeHtml(name)}</strong><small style="color:#829189">Nouveau groupe · 1 membre</small></div>`;
  document.querySelector('#groupsList').appendChild(item);
  event.target.reset();
  closeModal(document.querySelector('#groupModal'));
  toast('Groupe créé');
});

document.querySelector('#resourceForm').addEventListener('submit', event => {
  event.preventDefault();
  const data = new FormData(event.target);
  const item = document.createElement('article');
  item.className = 'resource';
  item.innerHTML = `<strong>${escapeHtml(data.get('title'))}</strong><small>Document · ${escapeHtml(data.get('category'))}</small>`;
  document.querySelector('#resourcesList').appendChild(item);
  event.target.reset();
  closeModal(document.querySelector('#resourceModal'));
  toast('Ressource ajoutée');
});

document.querySelector('#viewAllTasks').addEventListener('click', () => showView('tasks', 'Mes tâches'));

document.querySelector('#notifications').addEventListener('click', () => {
  document.querySelector('#notifications').innerHTML = '♢';
  toast('Toutes les notifications sont marquées comme lues');
});

document.querySelector('#search').addEventListener('input', event => {
  const query = event.target.value.toLowerCase().trim();
  document.querySelectorAll('#taskList .task').forEach(task => {
    task.style.display = task.textContent.toLowerCase().includes(query) ? '' : 'none';
  });
});
