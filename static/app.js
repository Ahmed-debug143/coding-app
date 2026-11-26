let csrfToken = null;
const authShell = document.querySelector('#authShell');
const appShell = document.querySelector('#appShell');
const authLoading = document.querySelector('#authLoading');
const authForms = document.querySelector('#authForms');

function authPanel(name) {
  document.querySelector('#loginPanel').hidden = name !== 'login';
  document.querySelector('#registerPanel').hidden = name !== 'register';
  document.querySelector('#forgotPanel').hidden = name !== 'forgot';
  document.querySelector('#resetPanel').hidden = name !== 'reset';
  document.querySelector('#authForms').hidden = !['login', 'register'].includes(name);
  clearAuthErrors();
}

function clearAuthErrors() {
  document.querySelectorAll('.field-error').forEach(node => { node.textContent = ''; });
  document.querySelectorAll('.form-error').forEach(node => { node.textContent = ''; });
}

function showAuth() {
  appShell.hidden = true;
  authShell.hidden = false;
  authLoading.hidden = true;
  authForms.hidden = false;
}

function showApp(user) {
  authShell.hidden = true;
  appShell.hidden = false;
  document.querySelector('#adminNav').hidden = user.role !== 'admin';
  document.querySelector('#profileName').textContent = user.name;
  document.querySelector('#profileEmail').textContent = user.email;
  document.querySelector('#profileAvatar').textContent = user.initials || '?';
  loadAccountData();
}

function showApiError(formName, payload) {
  const detail = payload && payload.detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail) && detail.field) {
    const target = document.querySelector(`#${formName}Form [data-error-for="${detail.field}"]`);
    if (target) target.textContent = detail.message || 'Vérifiez ce champ.';
    else document.querySelector(`#${formName}Error`).textContent = detail.message || 'La demande n’a pas abouti.';
    return;
  }
  if (Array.isArray(detail)) {
    detail.forEach(issue => {
      const field = issue.loc && issue.loc.at(-1);
      const target = document.querySelector(`#${formName}Form [data-error-for="${field}"]`);
      if (target && !target.textContent) target.textContent = 'Vérifiez ce champ.';
    });
    document.querySelector(`#${formName}Error`).textContent = 'Certaines informations sont invalides.';
    return;
  }
  document.querySelector(`#${formName}Error`).textContent =
    typeof detail === 'string' ? detail : 'Le service est momentanément indisponible. Réessayez.';
}

async function authRequest(path, body, csrf = false) {
  const headers = { 'Content-Type': 'application/json' };
  if (csrf && csrfToken) headers['X-CSRF-Token'] = csrfToken;
  const response = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers,
    body: JSON.stringify(body || {})
  });
  let payload = {};
  try { payload = await response.json(); } catch (_) { /* Réponse non JSON : l’erreur générique sera affichée. */ }
  if (!response.ok) {
    const error = new Error('Requête refusée');
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

function setSubmitting(form, submitting, label) {
  const button = form.querySelector('[type="submit"]');
  button.disabled = submitting;
  button.textContent = submitting ? 'Veuillez patienter…' : label;
  form.setAttribute('aria-busy', String(submitting));
}

function finishAuthentication(payload) {
  csrfToken = payload.csrf_token;
  showApp(payload.user);
  const requestedPath = new URLSearchParams(window.location.search).get('next');
  const destination = requestedPath && /^\/app(?:\/|$)/.test(requestedPath) && !requestedPath.startsWith('//') ? requestedPath : '/app';
  if (destination === '/app') window.history.replaceState({}, '', '/app');
  else window.location.assign(destination);
}

document.querySelectorAll('[data-show-register]').forEach(button => button.addEventListener('click', () => authPanel('register')));
document.querySelectorAll('[data-show-login]').forEach(button => button.addEventListener('click', () => authPanel('login')));
document.querySelectorAll('[data-show-forgot]').forEach(button => button.addEventListener('click', () => authPanel('forgot')));

document.querySelectorAll('[data-toggle-password]').forEach(button => {
  button.addEventListener('click', () => {
    const input = document.getElementById(button.dataset.togglePassword);
    const visible = input.type === 'password';
    input.type = visible ? 'text' : 'password';
    button.textContent = visible ? 'Masquer' : 'Afficher';
    button.setAttribute('aria-label', `${visible ? 'Masquer' : 'Afficher'} le mot de passe`);
  });
});

['loginForm', 'registerForm'].forEach(formId => {
  const form = document.querySelector(`#${formId}`);
  form.addEventListener('input', event => {
    const fieldError = form.querySelector(`[data-error-for="${event.target.name}"]`);
    if (fieldError) fieldError.textContent = '';
    const globalError = form.querySelector('.form-error');
    if (globalError) globalError.textContent = '';
  });
});

document.querySelector('#loginForm').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  clearAuthErrors();
  if (!form.reportValidity()) return;
  setSubmitting(form, true, 'Se connecter');
  try {
    const payload = await authRequest('/api/auth/login', {
      email: form.elements.email.value,
      password: form.elements.password.value
    });
    finishAuthentication(payload);
  } catch (error) {
    showApiError('login', error.payload);
  } finally {
    setSubmitting(form, false, 'Se connecter');
  }
});

document.querySelector('#registerForm').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  clearAuthErrors();
  if (!form.reportValidity()) return;
  if (form.elements.password.value !== form.elements.confirm.value) {
    form.querySelector('[data-error-for="confirm"]').textContent = 'Les mots de passe ne correspondent pas.';
    form.elements.confirm.focus();
    return;
  }
  setSubmitting(form, true, 'Créer mon compte');
  try {
    const payload = await authRequest('/api/auth/register', {
      name: form.elements.name.value,
      email: form.elements.email.value,
      password: form.elements.password.value
    });
    finishAuthentication(payload);
  } catch (error) {
    showApiError('register', error.payload);
  } finally {
    setSubmitting(form, false, 'Créer mon compte');
  }
});

document.querySelector('#forgotForm').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  document.querySelector('#forgotError').textContent = '';
  setSubmitting(form, true, 'Envoyer le lien');
  try {
    const result = await authRequest('/api/auth/forgot-password', { email: form.elements.email.value });
    document.querySelector('#forgotError').className = 'profile-success';
    document.querySelector('#forgotError').textContent = result.reset_link
      ? 'Mode développement: lien généré.'
      : 'Si ce compte existe, un lien de réinitialisation a été envoyé.';
  } catch (error) {
    document.querySelector('#forgotError').className = 'form-error';
    document.querySelector('#forgotError').textContent = error.payload?.detail || 'Impossible de traiter la demande.';
  } finally {
    setSubmitting(form, false, 'Envoyer le lien');
  }
});

document.querySelector('#resetForm').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  document.querySelector('#resetError').textContent = '';
  setSubmitting(form, true, 'Modifier le mot de passe');
  try {
    await authRequest('/api/auth/reset-password', {
      token: form.elements.token.value,
      new_password: form.elements.password.value
    });
    authPanel('login');
    document.querySelector('#loginError').textContent = 'Votre mot de passe a été modifié. Vous pouvez vous connecter.';
  } catch (error) {
    document.querySelector('#resetError').textContent = error.payload?.detail || 'Le lien est invalide ou expiré.';
  } finally {
    setSubmitting(form, false, 'Modifier le mot de passe');
  }
});

document.querySelector('#logoutButton').addEventListener('click', async event => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    await authRequest('/api/auth/logout', {}, true);
    csrfToken = null;
    window.location.assign('/');
  } catch (_) {
    toast('La déconnexion a échoué. Vérifiez votre connexion puis réessayez.');
    button.disabled = false;
  }
});

async function restoreSession() {
  authShell.hidden = false;
  const resetToken = new URLSearchParams(window.location.search).get('reset');
  if (resetToken) {
    authLoading.hidden = true;
    authForms.hidden = true;
    document.querySelector('#resetToken').value = resetToken;
    authPanel('reset');
    return;
  }
  try {
    const response = await fetch('/api/auth/session', { credentials: 'same-origin' });
    const payload = await response.json();
    if (!response.ok) throw new Error('Session indisponible');
    if (payload.authenticated) {
      csrfToken = payload.csrf_token;
      showApp(payload.user);
      const groupRoute = window.location.pathname.match(/^\/app\/groupes\/(\d+)$/);
      if (groupRoute) {
        showView('discoverGroups', 'Découvrir des groupes');
        const query = new URLSearchParams(window.location.search);
        openGroup(Number(groupRoute[1])).then(() => {
          const target = query.get('tache') ? document.querySelector(`[data-task-card="${Number(query.get('tache'))}"]`) : null;
          const section = query.get('onglet') === 'taches' ? (target || document.querySelector('.project-tasks')) : document.querySelector('.collab-workspace');
          section?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
      } else if (window.location.pathname !== '/app') {
        window.history.replaceState({}, '', '/app');
      }
    } else {
      showAuth();
      authPanel('login');
    }
  } catch (_) {
    showAuth();
    authPanel('login');
    document.querySelector('#loginError').textContent = 'Impossible de vérifier votre session. Vérifiez votre connexion et réessayez.';
  }
}

restoreSession();

let currentProfile = null;
let dashboardData = null;

function renderTasks() {
  const tasks = dashboardData?.all_tasks || [];
  const template = items => items.length ? items.map(task => `
    <div class="task ${task.status === 'done' ? 'done' : ''}">
      <div><div class="task-name">${escapeHtml(task.title)}</div><small>${escapeHtml(task.group_name || 'Groupe')} · ${task.due_at ? `Échéance ${escapeHtml(dateLabel(task.due_at))}` : 'Sans échéance'}${task.overdue ? ' · En retard' : ''}</small></div>
      <span class="tag priority-${task.priority}">${escapeHtml(taskPriorities[task.priority] || task.priority)} · ${escapeHtml(statusLabel(task.status))}</span>
      <button class="icon-btn" data-open-task-group="${task.group_id}">Ouvrir le projet</button>
    </div>`).join('') : '<div class="empty-state"><strong>Aucune tâche attribuée pour le moment</strong><span>Les tâches de vos groupes apparaîtront ici.</span></div>';
  const status = document.querySelector('#myTasksStatus')?.value || '';
  const priority = document.querySelector('#myTasksPriority')?.value || '';
  const sort = document.querySelector('#myTasksSort')?.value || 'due_asc';
  let filtered = tasks.filter(task => (!status || task.status === status) && (!priority || task.priority === priority));
  const compare = { due_asc: (a,b) => (a.due_at || '9999').localeCompare(b.due_at || '9999'), due_desc: (a,b) => (b.due_at || '').localeCompare(a.due_at || ''), created_asc: (a,b) => a.created_at.localeCompare(b.created_at), created_desc: (a,b) => b.created_at.localeCompare(a.created_at) }[sort];
  filtered.sort(compare);
  document.querySelector('#taskList').innerHTML = template(tasks.slice(0, 8));
  document.querySelector('#taskListPage').innerHTML = template(filtered);
}

function escapeHtml(value) {
  const element = document.createElement('div');
  element.textContent = value;
  return element.innerHTML;
}

async function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const method = (options.method || 'GET').toUpperCase();
  if (method !== 'GET' && csrfToken) headers.set('X-CSRF-Token', csrfToken);
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await fetch(path, { ...options, method, headers, credentials: 'same-origin' });
  let payload = {};
  try { payload = await response.json(); } catch (_) { /* La réponse sera présentée comme une erreur générique. */ }
  if (!response.ok) {
    const error = new Error('La demande n’a pas abouti.');
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function statusLabel(status) {
  return ({ todo: 'À faire', doing: 'En cours', review: 'En révision', done: 'Terminée' })[status] || 'À suivre';
}
const taskPriorities = { low: 'Faible', normal: 'Normale', high: 'Élevée', urgent: 'Urgente' };

function dateLabel(value) {
  if (!value) return '';
  const date = new Date(value.length === 10 ? `${value}T12:00:00` : value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short' }).format(date);
}

async function loadAccountData() {
  try {
    const [profile, dashboard] = await Promise.all([
      apiFetch('/api/profile/me'),
      apiFetch('/api/dashboard')
    ]);
    currentProfile = profile;
    dashboardData = dashboard;
    renderProfile();
    renderDashboard();
  } catch (error) {
    if (error.status === 401) {
      window.location.assign('/');
      return;
    }
    document.querySelector('#greetingText').textContent = 'Impossible de charger vos informations. Réessayez dans un instant.';
    document.querySelector('#profileError').textContent = 'Le profil n’a pas pu être chargé.';
  }
}

function setAvatar(element, profile) {
  element.replaceChildren();
  if (profile?.avatar_url) {
    const image = document.createElement('img');
    image.src = profile.avatar_url;
    image.alt = `Photo de ${profile.name}`;
    element.appendChild(image);
  } else {
    element.textContent = profile?.initials || '?';
  }
}

function renderProfile() {
  if (!currentProfile) return;
  const profile = currentProfile;
  document.querySelector('#profileDisplayName').textContent = profile.name;
  document.querySelector('#profileName').textContent = profile.name;
  document.querySelector('#profileAvatar').textContent = profile.initials || '?';
  document.querySelector('#avatarButton').textContent = profile.avatar_url ? 'Changer la photo' : 'Ajouter une photo';
  const subtitle = [profile.school, profile.faculty, profile.filiere, profile.level].filter(Boolean).join(' · ');
  document.querySelector('#profileSubtitle').textContent = subtitle || 'Ajoutez votre établissement et votre parcours pour aider les étudiants à vous trouver.';
  setAvatar(document.querySelector('#profileAvatar'), profile);
  setAvatar(document.querySelector('#profileAvatarLarge'), profile);

  const completion = profile.completion || { percent: 0, completed: 0, total: 13, missing: [] };
  document.querySelector('#profileCompletionText').textContent = `${completion.percent} %`;
  document.querySelector('#profileProgress').style.width = `${completion.percent}%`;
  document.querySelector('#profileCompletionHint').textContent = completion.missing.length
    ? `À compléter ensuite : ${completion.missing.slice(0, 3).join(', ')}.`
    : 'Votre profil est complet.';

  const values = [
    ['Biographie', profile.bio], ['Établissement', profile.school], ['Faculté', profile.faculty],
    ['Filière', profile.filiere], ['Niveau', profile.level], ['Objectif académique', profile.focus_goal],
    ['Compétences', profile.skills], ['Centres d’intérêt', profile.interests],
    ['Projets recherchés', profile.project_types], ['Disponibilités', profile.availability],
    ['Préférences de collaboration', profile.collaboration_preferences]
  ];
  document.querySelector('#profileDisplay').innerHTML = values.map(([label, value]) => {
    const text = Array.isArray(value) ? value.join(' · ') : (value || 'À compléter');
    return `<article class="profile-detail"><span>${escapeHtml(label)}</span><strong class="${value && value.length ? '' : 'muted'}">${escapeHtml(text)}</strong></article>`;
  }).join('');
  fillProfileForm(profile);
}

function fillProfileForm(profile) {
  const form = document.querySelector('#profileForm');
  ['name', 'school', 'faculty', 'filiere', 'level', 'bio', 'focus_goal', 'availability'].forEach(name => {
    form.elements[name].value = profile[name] || '';
  });
  form.elements.skills.value = (profile.skills || []).join(', ');
  form.elements.interests.value = (profile.interests || []).join(', ');
  form.elements.project_types.value = (profile.project_types || []).join(', ');
  const selected = new Set(profile.collaboration_preferences || []);
  form.querySelectorAll('[name="collaboration_preferences"]').forEach(input => { input.checked = selected.has(input.value); });
  form.elements.discoverable.checked = profile.discoverable !== false;
}

function renderDashboard() {
  if (!dashboardData) return;
  const groups = dashboardData.groups || [];
  const tasks = dashboardData.all_tasks || [];
  const deadlines = dashboardData.deadlines || [];
  const completion = dashboardData.profile_completion || { percent: 0, missing: [] };
  const user = dashboardData.user;
  document.querySelector('#greetingName').textContent = user.name.split(' ')[0];
  document.querySelector('#dashboardCompletion').textContent = `${completion.percent} %`;
  document.querySelector('#dashboardProgress').style.width = `${completion.percent}%`;
  document.querySelector('#greetingText').textContent = groups.length || tasks.length
    ? 'Voici les informations récentes de vos groupes et de votre travail.'
    : 'Complétez votre profil pour préparer vos prochaines collaborations.';
  document.querySelector('#groupCount').textContent = groups.length;
  document.querySelector('#taskCount').textContent = tasks.length;
  document.querySelector('#deadlineCount').textContent = deadlines.length;

  const groupMarkup = groups.length ? groups.slice(0, 4).map(group => {
    const progress = group.progress || { done: 0, total: 0 };
    const initials = (group.name || 'G').split(/\s+/).slice(0, 2).map(part => part[0]).join('').toUpperCase();
    return `<div class="group"><div class="group-icon">${escapeHtml(initials)}</div><div><strong>${escapeHtml(group.name)}</strong><small>${progress.done || 0}/${progress.total || 0} tâches terminées · ${group.member_count || 1} membres</small></div></div>`;
  }).join('') : '<div class="empty-state compact"><strong>Pas encore de groupe</strong><span>Les groupes que vous rejoindrez seront affichés ici.</span></div>';
  document.querySelector('#recentGroups').innerHTML = groupMarkup;
  document.querySelector('#groupsList').innerHTML = groups.length ? groupMarkup : '<div class="empty-state"><strong>Vous n’avez pas encore rejoint de groupe</strong><span>Vos projets d’équipe apparaîtront ici dès que vous participerez à un groupe.</span></div>';

  const items = [
    ...(dashboardData.events || []).map(item => ({ ...item, date: item.starts_at, kind: item.kind || 'Événement' })),
    ...deadlines.map(item => ({ ...item, date: item.due_at, kind: 'Échéance' }))
  ].sort((a, b) => (a.date || '').localeCompare(b.date || '')).slice(0, 5);
  document.querySelector('#eventsList').innerHTML = items.length ? items.map(item => `
    <div class="event"><div class="date">${escapeHtml(dateLabel(item.date))}</div><div><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.group_name || item.kind)}</small></div></div>`).join('')
    : '<div class="empty-state compact"><strong>Rien de planifié</strong><span>Vos prochaines échéances et réunions apparaîtront ici.</span></div>';

  const resources = dashboardData.resources || [];
  const resourcesList = document.querySelector('#resourcesList');
  if (resourcesList) resourcesList.innerHTML = resources.length ? resources.map(item =>
    `<article class="resource"><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.kind)} · partagé par ${escapeHtml(item.author_name)}</small></article>`
  ).join('') : '<div class="empty-state"><strong>Aucune ressource récente</strong><span>Les ressources partagées sur le campus apparaîtront ici.</span></div>';

  const unread = dashboardData.unread_notifications || 0;
  const badge = document.querySelector('#notifBadge');
  badge.textContent = unread;
  badge.hidden = unread === 0;
  const notifications = dashboardData.notifications || [];
  document.querySelector('#notificationsList').innerHTML = notifications.length ? notifications.map(item => {
    const localGroupHref = /^\/app\/groupes\/\d+(?:\?[^#]*)?$/.test(item.href || '') ? item.href : null;
    const content = `<strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.body || dateLabel(item.created_at))}</small>`;
    return `<div class="notification-item ${item.read_at ? '' : 'unread'}">${localGroupHref ? `<a href="${escapeHtml(localGroupHref)}">${content}</a>` : content}<button class="icon-btn" type="button" data-notification-delete="${item.id}">Supprimer</button></div>`;
  }).join('') : '<div class="empty-state compact"><strong>Vous êtes à jour</strong><span>Vos notifications s’afficheront ici.</span></div>';
  const lateIds = new Set((dashboardData.late || []).map(task => task.id));
  const urgent = new Map([...(dashboardData.urgent_tasks || []), ...(dashboardData.late || [])].map(task => [task.id, { ...task, overdue: lateIds.has(task.id) }]));
  const priorities = [...urgent.values()].sort((a, b) => Number(Boolean(b.overdue)) - Number(Boolean(a.overdue)) || (a.due_at || '9999').localeCompare(b.due_at || '')).slice(0, 6);
  document.querySelector('#priorityTasksList').innerHTML = priorities.length ? priorities.map(task => `<div class="priority-task ${task.overdue ? 'is-overdue' : ''}"><div><strong>${escapeHtml(task.title)}</strong><small>${escapeHtml(task.group_name)} · ${task.overdue ? 'En retard' : `Priorité ${escapeHtml(taskPriorities[task.priority])}`}</small></div><span class="tag">${escapeHtml(task.due_at ? dateLabel(task.due_at) : statusLabel(task.status))}</span></div>`).join('') : '<div class="empty-state compact"><strong>Rien d’urgent</strong><span>Les tâches à priorité élevée et les échéances dépassées apparaîtront ici.</span></div>';
  renderTasks();
}

function openProfileEditor() {
  if (!currentProfile) return;
  document.querySelector('#profileError').textContent = '';
  document.querySelector('#profileSuccess').textContent = '';
  fillProfileForm(currentProfile);
  document.querySelector('#profileDisplay').hidden = true;
  document.querySelector('#profileForm').hidden = false;
  document.querySelector('#profileForm').elements.name.focus();
}

function closeProfileEditor() {
  document.querySelector('#profileForm').hidden = true;
  document.querySelector('#profileDisplay').hidden = false;
  document.querySelector('#profileError').textContent = '';
  if (currentProfile) fillProfileForm(currentProfile);
}

function parseTagInput(value) {
  return value.split(',').map(item => item.trim()).filter(Boolean);
}

function showProfileApiError(error) {
  const detail = error.payload?.detail;
  if (Array.isArray(detail)) {
    detail.forEach(issue => {
      const field = issue.loc?.at(-1);
      const node = document.querySelector(`[data-profile-error="${field}"]`);
      if (node) node.textContent = 'Vérifiez la valeur saisie.';
    });
    document.querySelector('#profileError').textContent = 'Certains champs doivent être corrigés.';
  } else {
    document.querySelector('#profileError').textContent = typeof detail === 'string'
      ? detail : 'La sauvegarde a échoué. Vérifiez votre connexion puis réessayez.';
  }
}

document.querySelector('#editProfileButton').addEventListener('click', openProfileEditor);
document.querySelectorAll('[data-open-profile]').forEach(button => button.addEventListener('click', () => {
  showView('profile', 'Mon profil');
  openProfileEditor();
}));
document.querySelector('#cancelProfileEdit').addEventListener('click', closeProfileEditor);

document.querySelector('#profileForm').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  document.querySelector('#profileError').textContent = '';
  document.querySelector('#profileSuccess').textContent = '';
  const body = {
    name: form.elements.name.value.trim(),
    school: form.elements.school.value.trim(),
    faculty: form.elements.faculty.value.trim(),
    filiere: form.elements.filiere.value.trim(),
    level: form.elements.level.value,
    bio: form.elements.bio.value.trim(),
    focus_goal: form.elements.focus_goal.value.trim(),
    skills: parseTagInput(form.elements.skills.value),
    interests: parseTagInput(form.elements.interests.value),
    project_types: parseTagInput(form.elements.project_types.value),
    availability: form.elements.availability.value.trim(),
    collaboration_preferences: [...form.querySelectorAll('[name="collaboration_preferences"]:checked')].map(input => input.value),
    discoverable: form.elements.discoverable.checked
  };
  setSubmitting(form, true, 'Enregistrer le profil');
  try {
    currentProfile = await apiFetch('/api/profile/me', { method: 'PUT', body: JSON.stringify(body) });
    if (dashboardData) {
      dashboardData.user = currentProfile;
      dashboardData.profile_completion = currentProfile.completion;
    }
    renderProfile();
    renderDashboard();
    closeProfileEditor();
    document.querySelector('#profileSuccess').textContent = 'Votre profil a été enregistré.';
  } catch (error) {
    showProfileApiError(error);
  } finally {
    setSubmitting(form, false, 'Enregistrer le profil');
  }
});

document.querySelector('#avatarButton').addEventListener('click', () => document.querySelector('#avatarInput').click());
document.querySelector('#avatarInput').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  const button = document.querySelector('#avatarButton');
  button.disabled = true;
  button.textContent = 'Téléversement…';
  document.querySelector('#profileError').textContent = '';
  try {
    const body = new FormData();
    body.append('file', file);
    currentProfile = await apiFetch('/api/profile/me/avatar', { method: 'POST', body });
    if (dashboardData) dashboardData.user = currentProfile;
    renderProfile();
    renderDashboard();
    document.querySelector('#profileSuccess').textContent = 'Votre photo de profil a été mise à jour.';
  } catch (error) {
    document.querySelector('#profileError').textContent = error.payload?.detail || 'La photo n’a pas pu être téléversée.';
  } finally {
    button.disabled = false;
    button.textContent = currentProfile?.avatar_url ? 'Changer la photo' : 'Ajouter une photo';
    event.target.value = '';
  }
});

document.querySelector('#passwordForm').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  document.querySelector('#passwordError').textContent = '';
  const button = form.querySelector('[type="submit"]');
  button.disabled = true;
  try {
    await apiFetch('/api/auth/password', {
      method: 'POST',
      body: JSON.stringify({
        current_password: form.elements.current_password.value,
        new_password: form.elements.new_password.value
      })
    });
    form.reset();
    toast('Mot de passe modifié. Vous allez être reconnecté.');
    setTimeout(() => window.location.assign('/'), 700);
  } catch (error) {
    document.querySelector('#passwordError').textContent =
      error.payload?.detail || 'Le mot de passe n’a pas pu être modifié.';
  } finally {
    button.disabled = false;
  }
});

document.querySelector('#viewAllTasks').addEventListener('click', () => showView('tasks', 'Mes tâches'));
['myTasksStatus', 'myTasksPriority', 'myTasksSort'].forEach(id => document.querySelector(`#${id}`).addEventListener('change', renderTasks));
document.querySelectorAll('#taskList, #taskListPage').forEach(container => container.addEventListener('click', event => {
  const button = event.target.closest('[data-open-task-group]'); if (!button) return;
  showView('discoverGroups', 'Découvrir les groupes');
  document.querySelector('#groupDetail').hidden = false;
  openGroup(Number(button.dataset.openTaskGroup));
}));
document.querySelector('#notifications').addEventListener('click', () => {
  showView('dashboard', 'Tableau de bord');
  document.querySelector('#notificationsCard').scrollIntoView({ behavior: 'smooth', block: 'center' });
});
document.querySelector('#notificationsCard').addEventListener('click', async event => {
  const button = event.target.closest('[data-notification-delete]');
  if (!button) return;
  try {
    await apiFetch(`/api/notifications/${button.dataset.notificationDelete}`, { method: 'DELETE' });
    await loadAccountData();
  } catch (error) {
    toast(error.payload?.detail || 'La notification n’a pas pu être supprimée.');
  }
});

document.querySelector('#search').addEventListener('input', event => {
  const query = event.target.value.toLowerCase().trim();
  document.querySelectorAll('#taskList .task, #taskListPage .task').forEach(task => {
    task.style.display = task.textContent.toLowerCase().includes(query) ? '' : 'none';
  });
});

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
  if (viewId === 'resources') loadResources();
  if (viewId === 'calendar') loadCalendar();
  if (viewId === 'messages') loadDmConversations();
  if (viewId === 'publications') loadPublications();
}

async function loadPublications() {
  const status = document.querySelector('#publicationStatus');
  status.textContent = 'Chargement…';
  try {
    const publications = await apiFetch('/api/publications');
    status.textContent = `${publications.length} publication${publications.length === 1 ? '' : 's'}`;
    document.querySelector('#publicationFeed').innerHTML = publications.length ? publications.map(post => {
      const deleteAction = post.mine || currentProfile?.role === 'admin'
        ? `<button class="icon-btn" type="button" data-post-delete="${post.id}">Supprimer</button>` : '';
      const link = post.link_url ? `<a class="primary" href="${escapeHtml(post.link_url)}" target="_blank" rel="noopener noreferrer">Ouvrir le lien</a>` : '';
      const reactions = (post.reactions || []).map(reaction =>
        `<button class="tag ${reaction.mine ? 'active' : ''}" type="button" data-post-reaction="${post.id}" data-emoji="${escapeHtml(reaction.emoji)}">${escapeHtml(reaction.emoji)} ${reaction.count}</button>`
      ).join('');
      const comments = (post.comments || []).map(comment =>
        `<div class="publication-comment"><strong>${escapeHtml(comment.author_name)}</strong><p>${escapeHtml(comment.deleted_at ? 'Commentaire supprimé' : comment.body)}</p></div>`
      ).join('');
      return `<article class="publication-card" data-publication="${post.id}">
        <div class="section-head"><strong>${escapeHtml(post.author_name)}</strong><small>${escapeHtml(dateLabel(post.created_at))}</small></div>
        <p>${escapeHtml(post.body)}</p>
        <div class="publication-actions">${link}<button class="icon-btn" type="button" data-post-reaction="${post.id}" data-emoji="👍">👍</button><button class="icon-btn" type="button" data-post-report="${post.id}">Signaler</button>${deleteAction}</div>
        <div class="publication-reactions">${reactions}</div>
        <div class="publication-comments">${comments}</div>
        <form class="publication-comment-form" data-comment-publication="${post.id}">
          <input name="body" maxlength="2000" required placeholder="Ajouter un commentaire">
          <button class="icon-btn" type="submit">Commenter</button>
        </form>
      </article>`;
    }).join('') : '<div class="empty-state"><strong>Aucune publication</strong><span>Partagez une information utile à la communauté étudiante.</span></div>';
  } catch (_) {
    status.textContent = 'Le fil d’actualité ne peut pas être chargé.';
  }
}

document.querySelector('#publicationForm').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  document.querySelector('#publicationError').textContent = '';
  try {
    await apiFetch('/api/publications', {
      method: 'POST',
      body: JSON.stringify({
        body: form.elements.body.value.trim(),
        link_url: form.elements.link_url.value.trim() || null
      })
    });
    form.reset();
    toast('Publication publiée.');
    await loadPublications();
  } catch (error) {
    document.querySelector('#publicationError').textContent =
      error.payload?.detail || 'La publication n’a pas pu être créée.';
  }
});

document.querySelector('#publicationFeed').addEventListener('submit', async event => {
  const form = event.target.closest('[data-comment-publication]');
  if (!form) return;
  event.preventDefault();
  try {
    await apiFetch(`/api/publications/${form.dataset.commentPublication}/comments`, {
      method: 'POST',
      body: JSON.stringify({ body: form.elements.body.value.trim() })
    });
    form.reset();
    await loadPublications();
  } catch (error) {
    toast(error.payload?.detail || 'Commentaire impossible.');
  }
});

document.querySelector('#publicationFeed').addEventListener('click', async event => {
  const button = event.target.closest('button');
  if (!button) return;
  try {
    if (button.dataset.postReaction) {
      await apiFetch(`/api/publications/${button.dataset.postReaction}/reactions`, {
        method: 'POST',
        body: JSON.stringify({ emoji: button.dataset.emoji })
      });
      await loadPublications();
    } else if (button.dataset.postReport) {
      const reason = prompt('Expliquez brièvement le problème :');
      if (!reason) return;
      await apiFetch(`/api/publications/${button.dataset.postReport}/report`, {
        method: 'POST',
        body: JSON.stringify({ reason })
      });
      toast('Publication signalée.');
    } else if (button.dataset.postDelete) {
      if (!confirm('Supprimer cette publication ?')) return;
      await apiFetch(`/api/publications/${button.dataset.postDelete}`, { method: 'DELETE' });
      toast('Publication supprimée.');
      await loadPublications();
    }
  } catch (error) {
    toast(error.payload?.detail || 'Cette action a échoué.');
  }
});

document.querySelector('#assistantForm').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const body = {
    action: form.elements.action.value,
    question: form.elements.question.value.trim(),
  };
  if (form.elements.group_id.value) body.group_id = Number(form.elements.group_id.value);
  document.querySelector('#assistantStatus').textContent = 'Analyse locale…';
  try {
    const result = await apiFetch('/api/assistant/answer', { method: 'POST', body: JSON.stringify(body) });
    document.querySelector('#assistantStatus').textContent = result.mode === 'model' ? 'Réponse du modèle configuré' : 'Réponse locale, sans modèle génératif';
    const sections = (result.sections || []).map(section => `<section><h3>${escapeHtml(section.heading)}</h3><ul>${section.items.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul></section>`).join('');
    document.querySelector('#assistantOutput').innerHTML = `<h3>${escapeHtml(result.title)}</h3><p>${escapeHtml(result.intro)}</p>${sections}`;
  } catch (error) {
    document.querySelector('#assistantStatus').textContent = error.payload?.detail || 'L’assistant ne peut pas répondre.';
  }
});

let activeDmUserId = null;

async function loadDmConversations() {
  try {
    const conversations = await apiFetch('/api/dm/conversations');
    const dms = conversations.filter(item => item.kind === 'dm');
    document.querySelector('#dmConversationList').innerHTML = dms.length ? dms.map(item => `
      <button class="dm-conversation ${activeDmUserId === item.id ? 'active' : ''}" type="button" data-dm-user="${item.id}">
        <strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.last_body || 'Aucun message')}</small>${item.unread ? `<span class="tag">${item.unread}</span>` : ''}
      </button>`).join('') : '<div class="empty-state compact"><strong>Aucune conversation privée</strong><span>Les discussions autorisées avec vos connexions apparaîtront ici.</span></div>';
  } catch (_) {
    document.querySelector('#dmConversationList').innerHTML = '<div class="empty-state compact"><strong>Impossible de charger les conversations</strong></div>';
  }
}

async function openDm(userId) {
  activeDmUserId = Number(userId);
  const thread = await apiFetch(`/api/dm/${activeDmUserId}/messages`);
  document.querySelector('#dmThreadTitle').textContent = 'Conversation privée';
  document.querySelector('#dmForm').hidden = false;
  document.querySelector('#dmMessages').innerHTML = thread.messages.length ? thread.messages.map(message => `
    <article class="dm-message ${message.mine ? 'mine' : ''}"><strong>${escapeHtml(message.author.name)}</strong><p>${escapeHtml(message.deleted ? 'Message supprimé' : message.body)}</p><small>${escapeHtml(dateLabel(message.created_at))}</small></article>
  `).join('') : '<div class="empty-state compact"><strong>Aucun message</strong><span>Commencez la conversation.</span></div>';
  await loadDmConversations();
  const latest = thread.messages.at(-1)?.id;
  if (latest) await apiFetch(`/api/dm/${activeDmUserId}/read`, { method: 'POST', body: JSON.stringify({ last_message_id: latest }) }).catch(() => {});
}

document.querySelector('#dmConversationList').addEventListener('click', async event => {
  const button = event.target.closest('[data-dm-user]');
  if (!button) return;
  try { await openDm(button.dataset.dmUser); } catch (error) {
    toast(error.payload?.detail || 'Cette conversation est indisponible.');
  }
});

document.querySelector('#dmForm').addEventListener('submit', async event => {
  event.preventEvent?.();
  event.preventDefault();
  if (!activeDmUserId) return;
  const form = event.currentTarget;
  try {
    await apiFetch(`/api/dm/${activeDmUserId}/messages`, { method: 'POST', body: JSON.stringify({ body: form.elements.body.value.trim() }) });
    form.reset();
    await openDm(activeDmUserId);
  } catch (error) {
    toast(error.payload?.detail || 'Le message n’a pas pu être envoyé.');
  }
});

async function loadAdmin() {
  try {
    const [stats, users, reports, publicationReports, audit] = await Promise.all([
      apiFetch('/api/admin/stats'),
      apiFetch('/api/admin/users'),
      apiFetch('/api/admin/reports?status=pending'),
      apiFetch('/api/admin/publication-reports'),
      apiFetch('/api/admin/audit'),
    ]);
    document.querySelector('#adminStats').innerHTML = Object.entries(stats).map(([key, value]) => `<div class="stat"><strong>${value}</strong><span>${({ users: 'Étudiants', active: 'Actifs', groups: 'Groupes', tasks: 'Tâches', resources: 'Ressources', messages: 'Messages', reports: 'Signalements' })[key] || key}</span></div>`).join('');
    document.querySelector('#adminUsers').innerHTML = users.length ? users.map(user => `
      <div class="admin-row"><div><strong>${escapeHtml(user.name)}</strong><small>${escapeHtml(user.email)} · ${user.suspended ? 'Suspendu' : 'Actif'}</small></div>${user.role !== 'admin' ? `<button class="icon-btn" type="button" data-admin-suspend="${user.id}" data-suspended="${user.suspended ? 'true' : 'false'}">${user.suspended ? 'Réactiver' : 'Suspendre'}</button>` : '<span class="tag">Administrateur</span>'}</div>
    `).join('') : '<div class="empty-state compact"><span>Aucun utilisateur.</span></div>';
    const standardReports = reports.length ? reports.map(report => `
      <div class="admin-row"><div><strong>${escapeHtml(report.target_type)} #${report.target_id}</strong><small>${escapeHtml(report.reason)} · ${escapeHtml(report.reporter_name)}</small></div><button class="icon-btn" type="button" data-report-resolve="${report.id}" data-status="resolved">Résoudre</button><button class="icon-btn" type="button" data-report-resolve="${report.id}" data-status="dismissed">Ignorer</button></div>
    `).join('') : '';
    const studentReports = publicationReports.length ? publicationReports.map(report => `
      <div class="admin-row"><div><strong>Publication #${report.publication_id}</strong><small>${escapeHtml(report.publication_body)} · ${escapeHtml(report.reason)} · ${escapeHtml(report.reporter_name)}</small></div><button class="icon-btn" type="button" data-publication-report-resolve="${report.id}" data-status="resolved">Résoudre</button><button class="icon-btn" type="button" data-publication-report-resolve="${report.id}" data-status="dismissed">Ignorer</button></div>
    `).join('') : '';
    document.querySelector('#adminReports').innerHTML = (standardReports + studentReports) || '<div class="empty-state compact"><span>Aucun signalement en attente.</span></div>';
    document.querySelector('#adminAudit').innerHTML = audit.length ? audit.map(item => `
      <div class="admin-row"><div><strong>${escapeHtml(item.actor_name)} · ${escapeHtml(item.action)}</strong><small>${escapeHtml(item.target_type)} ${item.target_id ? `#${item.target_id}` : ''} · ${escapeHtml(item.detail)} · ${escapeHtml(dateLabel(item.created_at))}</small></div></div>
    `).join('') : '<div class="empty-state compact"><span>Aucune action enregistrée.</span></div>';
  } catch (error) {
    if (error.status === 403) {
      toast('Cette zone est réservée aux administrateurs.');
      showView('dashboard', 'Tableau de bord');
    }
  }
}

document.querySelector('#adminUserSearch').addEventListener('submit', async event => {
  event.preventEvent?.();
  event.preventDefault();
  try {
    const users = await apiFetch(`/api/admin/users?q=${encodeURIComponent(event.currentTarget.elements.q.value)}`);
    document.querySelector('#adminUsers').innerHTML = users.length ? users.map(user => `<div class="admin-row"><div><strong>${escapeHtml(user.name)}</strong><small>${escapeHtml(user.email)} · ${user.suspended ? 'Suspendu' : 'Actif'}</small></div>${user.role !== 'admin' ? `<button class="icon-btn" type="button" data-admin-suspend="${user.id}" data-suspended="${user.suspended ? 'true' : 'false'}">${user.suspended ? 'Réactiver' : 'Suspendre'}</button>` : '<span class="tag">Administrateur</span>'}</div>`).join('') : '<div class="empty-state compact"><span>Aucun utilisateur.</span></div>';
  } catch (_) { toast('Recherche impossible.'); }
});

document.querySelector('#adminUsers').addEventListener('click', async event => {
  const button = event.target.closest('[data-admin-suspend]');
  if (!button) return;
  const suspended = button.dataset.suspended !== 'true';
  if (!confirm(suspended ? 'Suspendre ce compte ?' : 'Réactiver ce compte ?')) return;
  try {
    await apiFetch(`/api/admin/users/${button.dataset.adminSuspend}/suspension`, { method: 'POST', body: JSON.stringify({ suspended }) });
    toast(suspended ? 'Compte suspendu.' : 'Compte réactivé.');
    await loadAdmin();
  } catch (error) { toast(error.payload?.detail || 'Action impossible.'); }
});

document.querySelector('#adminReports').addEventListener('click', async event => {
  const button = event.target.closest('[data-report-resolve], [data-publication-report-resolve]');
  if (!button) return;
  try {
    if (button.dataset.reportResolve) {
      await apiFetch(`/api/admin/reports/${button.dataset.reportResolve}/resolve`, { method: 'POST', body: JSON.stringify({ status: button.dataset.status, note: '' }) });
    } else {
      await apiFetch(`/api/admin/publication-reports/${button.dataset.publicationReportResolve}/resolve`, { method: 'POST', body: JSON.stringify({ status: button.dataset.status, note: '' }) });
    }
    toast('Signalement traité.');
    await loadAdmin();
  } catch (error) { toast(error.payload?.detail || 'Traitement impossible.'); }
});

async function loadResources() {
  const form = document.querySelector('#resourceSearchForm');
  const params = new URLSearchParams(new FormData(form)).toString();
  const status = document.querySelector('#resourceLibraryStatus');
  const target = document.querySelector('#resourceLibraryList');
  status.textContent = 'Chargement…';
  try {
    const resources = await apiFetch(`/api/resources?${params}`);
    status.textContent = `${resources.length} ressource${resources.length === 1 ? '' : 's'}`;
    target.innerHTML = resources.length ? resources.map(resource => {
      const action = resource.link_url
        ? `<a class="primary" href="${escapeHtml(resource.link_url)}" target="_blank" rel="noopener noreferrer">Ouvrir</a>`
        : `<a class="primary" href="/api/resources/${resource.id}/download">Télécharger</a>`;
      const deleteAction = currentProfile && (currentProfile.id === resource.author_id || currentProfile.role === 'admin')
        ? `<button class="icon-btn danger" type="button" data-resource-delete="${resource.id}">Supprimer</button>` : '';
      return `<article class="resource-card"><div class="resource-card-head"><span class="tag">${escapeHtml(resource.kind)}</span><small>${escapeHtml(resource.subject || 'Sans matière')} · ${escapeHtml(resource.level || 'Tous niveaux')}</small></div><h3>${escapeHtml(resource.title)}</h3><p>${escapeHtml(resource.description || 'Aucune description.')}</p><small>Partagé par ${escapeHtml(resource.author_name)} · ${resource.downloads || 0} téléchargement(s)</small><div class="resource-actions">${action}<button class="icon-btn" type="button" data-resource-favorite="${resource.id}">Favori</button><button class="icon-btn" type="button" data-resource-report="${resource.id}">Signaler</button>${deleteAction}</div></article>`;
    }).join('') : '<div class="empty-state"><strong>Aucune ressource publiée</strong><span>Partagez le premier document ou support du campus.</span></div>';
  } catch (_) {
  status.textContent = 'Les ressources ne peuvent pas être chargées.';
  }
}

let calendarMode = 'month';

async function loadCalendar() {
  const now = new Date();
  let start;
  let end;
  if (calendarMode === 'day') {
    start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    end = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  } else if (calendarMode === 'week') {
    const mondayOffset = (now.getDay() + 6) % 7;
    start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - mondayOffset);
    end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 7);
  } else {
    start = new Date(now.getFullYear(), now.getMonth(), 1);
    end = new Date(now.getFullYear(), now.getMonth() + 1, 1);
  }
  const status = document.querySelector('#calendarStatus');
  try {
    const data = await apiFetch(`/api/calendar?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`);
    const items = [
      ...data.events.map(item => ({ ...item, date: item.starts_at, type: item.kind })),
      ...data.deadlines.map(item => ({ ...item, date: item.due_at, type: 'echeance' }))
    ].sort((a, b) => (a.date || '').localeCompare(b.date || ''));
    const periodLabel = calendarMode === 'day' ? 'aujourd’hui' : calendarMode === 'week' ? 'cette semaine' : 'ce mois-ci';
    status.textContent = `${items.length} élément${items.length === 1 ? '' : 's'} ${periodLabel}`;
    document.querySelector('#calendarList').innerHTML = items.length ? items.map(item => `
      <article class="calendar-item"><div class="date"><span>${escapeHtml(dateLabel(item.date))}</span></div><div><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.group_name || ({ reunion: 'Réunion', travail: 'Travail', echeance: 'Échéance', autre: 'Événement' }[item.type] || 'Événement'))}</small></div>${item.created_by ? `<button class="icon-btn" type="button" data-calendar-edit="${item.id}" ${item.kind ? '' : 'hidden'}>Modifier</button><button class="icon-btn" type="button" data-calendar-delete="${item.id}" ${item.kind ? '' : 'hidden'}>Supprimer</button>` : ''}</article>
    `).join('') : '<div class="empty-state"><strong>Aucun événement ce mois-ci</strong><span>Ajoutez une réunion, une session de travail ou une échéance.</span></div>';
  } catch (_) {
    status.textContent = 'Le calendrier ne peut pas être chargé.';
  }
}

document.querySelectorAll('[data-calendar-mode]').forEach(button => {
  button.addEventListener('click', () => {
    calendarMode = button.dataset.calendarMode;
    document.querySelectorAll('[data-calendar-mode]').forEach(item =>
      item.classList.toggle('primary', item === button)
    );
    loadCalendar();
  });
});

document.querySelector('#resourceSearchForm').addEventListener('submit', event => {
  event.preventDefault();
  loadResources();
});
document.querySelector('#resourceFormToggle').addEventListener('click', () => {
  document.querySelector('#resourceUploadForm').hidden = false;
});
document.querySelector('#resourceFormCancel').addEventListener('click', () => {
  document.querySelector('#resourceUploadForm').hidden = true;
  document.querySelector('#resourceUploadError').textContent = '';
});
document.querySelector('#resourceUploadForm').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  const body = new FormData(form);
  document.querySelector('#resourceUploadError').textContent = '';
  try {
    await apiFetch('/api/resources/upload', { method: 'POST', body });
    form.reset();
    form.hidden = true;
    toast('La ressource a été publiée.');
    await loadResources();
  } catch (error) {
    document.querySelector('#resourceUploadError').textContent = error.payload?.detail || 'La ressource n’a pas pu être publiée.';
  }
});
document.querySelector('#resourceLibraryList').addEventListener('click', async event => {
  const button = event.target.closest('button');
  if (!button) return;
  try {
    if (button.dataset.resourceFavorite) {
      const result = await apiFetch(`/api/resources/${button.dataset.resourceFavorite}/favorite`, { method: 'POST' });
      toast(result.favorited ? 'Ajouté aux favoris.' : 'Retiré des favoris.');
    }
    if (button.dataset.resourceReport) {
      const reason = prompt('Expliquez brièvement le problème constaté :');
      if (!reason) return;
      await apiFetch(`/api/resources/${button.dataset.resourceReport}/report`, { method: 'POST', body: JSON.stringify({ reason }) });
      toast('Votre signalement a été transmis.');
      await loadResources();
    }
    if (button.dataset.resourceDelete) {
      if (!confirm('Supprimer définitivement cette ressource ?')) return;
      await apiFetch(`/api/resources/${button.dataset.resourceDelete}`, { method: 'DELETE' });
      toast('Ressource supprimée.');
      await loadResources();
    }
  } catch (error) {
    toast(error.payload?.detail || 'Cette action a échoué.');
  }
});

document.querySelector('#calendarFormToggle').addEventListener('click', () => {
  document.querySelector('#calendarForm').hidden = false;
});
document.querySelector('#calendarFormCancel').addEventListener('click', () => {
  document.querySelector('#calendarForm').hidden = true;
  document.querySelector('#calendarFormError').textContent = '';
});
document.querySelector('#calendarForm').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  const body = {
    title: form.elements.title.value.trim(),
    kind: form.elements.kind.value,
    starts_at: form.elements.starts_at.value,
    ends_at: form.elements.ends_at.value || null,
    description: form.elements.description.value.trim()
  };
  try {
    await apiFetch('/api/calendar/events', { method: 'POST', body: JSON.stringify(body) });
    form.reset();
    form.hidden = true;
    toast('Événement ajouté.');
    await loadCalendar();
  } catch (error) {
    document.querySelector('#calendarFormError').textContent = error.payload?.detail || 'L’événement n’a pas pu être ajouté.';
  }
});
document.querySelector('#calendarList').addEventListener('click', async event => {
  const editButton = event.target.closest('[data-calendar-edit]');
  if (editButton) {
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), 1);
    const end = new Date(now.getFullYear(), now.getMonth() + 1, 1);
    try {
      const data = await apiFetch(`/api/calendar?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`);
      const item = data.events.find(eventItem => eventItem.id === Number(editButton.dataset.calendarEdit));
      if (!item) return;
      const title = prompt('Nouveau titre de l’événement', item.title);
      if (!title || title.trim().length < 2) return;
      await apiFetch(`/api/calendar/events/${item.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          title: title.trim(),
          kind: item.kind,
          description: item.description || '',
          starts_at: item.starts_at,
          ends_at: item.ends_at,
          group_id: item.group_id || null
        })
      });
      toast('Événement modifié.');
      await loadCalendar();
    } catch (error) {
      toast(error.payload?.detail || 'Modification impossible.');
    }
    return;
  }
  const button = event.target.closest('[data-calendar-delete]');
  if (!button) return;
  if (!confirm('Supprimer cet événement ?')) return;
  try {
    await apiFetch(`/api/calendar/events/${button.dataset.calendarDelete}`, { method: 'DELETE' });
    toast('Événement supprimé.');
    await loadCalendar();
  } catch (error) {
    toast(error.payload?.detail || 'Suppression impossible.');
  }
});

renderTasks();

document.querySelectorAll('.nav button').forEach(button => {
  button.addEventListener('click', () => showView(
    button.dataset.view,
    button.textContent.replace(/^\s*[⌂◫✓▧◉⌕◎◌◈□✦⚙]\s*/, '').trim()
  ));
});

document.querySelectorAll('[data-view-link]').forEach(button => button.addEventListener('click', () => showView(button.dataset.viewLink, 'Découvrir les groupes')));

function renderGroupCards(groups) {
  const target = document.querySelector('#groupDiscoveryList');
  target.innerHTML = groups.length ? groups.map(group => `
    <article class="discovery-card"><div class="group-card-top"><div class="group-icon">${escapeHtml((group.name || 'G').slice(0, 2).toUpperCase())}</div><span class="tag">${group.recruitment_open ? 'Recrutement ouvert' : 'Recrutement fermé'}</span></div>
      <h3>${escapeHtml(group.name)}</h3><p class="muted">${escapeHtml([group.subject, group.filiere, group.preferred_level].filter(Boolean).join(' · ') || 'Projet étudiant')}</p>
      <p>${escapeHtml(group.objective || group.description || 'Aucun objectif détaillé pour le moment.')}</p>
      <div class="skill-tags">${(group.skills_wanted || []).map(skill => `<span class="tag">${escapeHtml(skill)}</span>`).join('')}</div>
      <small>${group.member_count} / ${group.max_members} membres · ${group.visibility === 'private' ? 'Privé' : 'Public'}</small>
      <div class="group-card-actions"><button class="icon-btn" data-group-open="${group.id}">Voir le projet</button>${group.joined ? `<span class="tag">Membre</span>${group.unread_count ? `<span class="tag chat-unread-badge">${group.unread_count} non lu${group.unread_count > 1 ? 's' : ''}</span>` : ''}` : group.visibility === 'public' && group.recruitment_open ? `<button class="primary" data-group-join="${group.id}">Rejoindre</button>` : ''}</div></article>`).join('') : '<div class="empty-state"><strong>Aucun groupe trouvé</strong><span>Modifiez les filtres ou créez un groupe pour lancer votre projet.</span></div>';
}

async function loadGroupDiscovery() {
  const form = document.querySelector('#groupSearchForm');
  const params = new URLSearchParams(new FormData(form));
  const checked = form.elements.recruiting.checked;
  params.delete('recruiting');
  if (checked) params.set('recruiting', 'true');
  document.querySelector('#groupDiscoveryStatus').textContent = 'Chargement des groupes…';
  try {
    const groups = await apiFetch(`/api/groups?${params.toString()}`);
    renderGroupCards(groups);
    document.querySelector('#groupDiscoveryStatus').textContent = `${groups.length} groupe${groups.length === 1 ? '' : 's'} trouvé${groups.length === 1 ? '' : 's'}`;
  } catch (_) { document.querySelector('#groupDiscoveryStatus').textContent = 'Les groupes ne peuvent pas être chargés. Réessayez.'; }
}

function groupDetailMarkup(group) {
  const members = (group.members || []).map(member => `<div class="group-member"><div class="avatar">${escapeHtml(member.initials)}</div><div><strong>${escapeHtml(member.name)}</strong><small>${escapeHtml([member.filiere, member.level].filter(Boolean).join(' · '))}</small></div><span class="tag">${member.role === 'owner' ? 'Propriétaire' : member.role === 'admin' ? 'Responsable' : 'Membre'}</span>${['owner', 'admin'].includes(group.member_role) && member.role !== 'owner' ? `${group.member_role === 'owner' ? `<button class="icon-btn" data-member-role="${member.id}" data-role="${member.role === 'admin' ? 'member' : 'admin'}" data-group-id="${group.id}">${member.role === 'admin' ? 'Rétrograder' : 'Nommer responsable'}</button><button class="icon-btn" data-transfer-owner="${member.id}" data-group-id="${group.id}">Transférer la propriété</button>` : ''}<button class="icon-btn" data-remove-member="${member.id}" data-group-id="${group.id}">Retirer</button>` : ''}</div>`).join('');
  const requests = (group.join_requests || []).map(item => `<div class="group-member"><div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.message || 'Souhaite rejoindre le groupe')}</small></div><button class="primary" data-request-accept="${item.id}" data-group-id="${group.id}">Accepter</button><button class="icon-btn" data-request-decline="${item.id}" data-group-id="${group.id}">Refuser</button></div>`).join('');
  const activity = (group.activity || []).map(item => `<div class="activity-item"><strong>${escapeHtml(item.summary)}</strong><small>${escapeHtml(dateLabel(item.created_at))}</small></div>`).join('');
  const ownerActions = ['owner', 'admin'].includes(group.member_role) ? `<button class="icon-btn" data-toggle-recruitment="${group.id}" data-open="${group.recruitment_open ? 'false' : 'true'}">${group.recruitment_open ? 'Fermer le recrutement' : 'Rouvrir le recrutement'}</button><button class="icon-btn" data-edit-group="${group.id}">Modifier les paramètres</button>${group.member_role === 'owner' ? `<button class="icon-btn danger" data-delete-group="${group.id}">Supprimer le groupe</button>` : ''}` : '';
  const invitePicker = ['owner', 'admin'].includes(group.member_role) ? `<section class="invite-picker"><h3>Inviter un étudiant</h3><input type="search" data-invite-search="${group.id}" placeholder="Rechercher un nom, une filière ou une compétence" autocomplete="off"><div data-invite-results="${group.id}"></div>${group.invitations?.length ? `<small>Invitations en attente : ${group.invitations.map(item => escapeHtml(item.name)).join(', ')}</small>` : ''}</section>` : '';
  const joinAction = !group.joined && group.visibility === 'public' && group.recruitment_open ? `<button class="primary" data-group-join="${group.id}">Rejoindre le groupe</button><button class="icon-btn" data-group-request="${group.id}">Envoyer une demande</button>` : '';
  const taskWorkspace = group.joined ? `<section class="project-tasks"><div class="section-head"><div><h3>Tâches du projet</h3><p class="muted"><span data-task-progress>${group.progress?.done || 0} / ${group.progress?.total || 0} tâches terminées</span></p></div><button class="primary" type="button" data-task-new="${group.id}">Nouvelle tâche</button></div>
    <div class="task-progress"><span data-task-progress-bar style="width:${group.progress?.pct || 0}%"></span></div>
    <form class="task-filters" data-task-filters="${group.id}"><input name="q" type="search" placeholder="Rechercher un titre"><select name="status"><option value="">Tous les statuts</option><option value="todo">À faire</option><option value="doing">En cours</option><option value="review">En révision</option><option value="done">Terminées</option></select><select name="priority"><option value="">Toutes les priorités</option><option value="urgent">Urgente</option><option value="high">Élevée</option><option value="normal">Normale</option><option value="low">Faible</option></select><select name="assignee"><option value="">Tous les responsables</option>${group.members.map(member => `<option value="${member.id}">${escapeHtml(member.name)}</option>`).join('')}</select><select name="sort"><option value="due_asc">Échéance proche</option><option value="created_desc">Récemment créée</option><option value="created_asc">Plus ancienne</option><option value="due_desc">Échéance lointaine</option></select><label><input name="late" type="checkbox"> En retard</label><button class="icon-btn" type="submit">Filtrer</button><button class="icon-btn" type="button" data-task-view-toggle>Vue liste</button></form>
    <div data-task-board="${group.id}" class="task-kanban" role="region" aria-label="Tableau des tâches"><p class="muted" role="status">Chargement des tâches…</p></div>
    <form class="task-editor card" data-task-editor="${group.id}" hidden><div class="section-head"><h3 data-task-editor-heading>Nouvelle tâche</h3></div><div class="profile-form-grid"><div class="profile-control"><label>Titre</label><input name="title" required minlength="2" maxlength="140"></div><div class="profile-control"><label>Priorité</label><select name="priority"><option value="low">Faible</option><option value="normal" selected>Normale</option><option value="high">Élevée</option><option value="urgent">Urgente</option></select></div><div class="profile-control profile-control-wide"><label>Description</label><textarea name="description" rows="3" maxlength="4000"></textarea></div><div class="profile-control"><label>Début</label><input type="date" name="starts_at"></div><div class="profile-control"><label>Échéance</label><input type="date" name="due_at"></div><div class="profile-control"><label>Charge estimée (heures)</label><input type="number" name="estimate_hours" min="0" max="1000" step="0.25"></div><div class="profile-control"><label>Responsables</label><select name="assignee_ids" multiple size="4">${group.members.map(member => `<option value="${member.id}">${escapeHtml(member.name)}</option>`).join('')}</select><small>Ctrl/Cmd permet plusieurs choix.</small></div></div><p class="form-error" data-task-error role="alert"></p><div class="profile-form-actions"><button type="button" class="icon-btn" data-task-cancel>Annuler</button><button type="submit" class="primary">Enregistrer</button></div></form>
    </section>` : '<p class="empty-state"><strong>Les tâches sont réservées aux membres</strong><span>Rejoignez le groupe pour consulter son tableau de travail.</span></p>';
  return `<button class="icon-btn" data-back-groups>← Retour aux groupes</button><div class="section-head"><div><p class="profile-kicker">PROJET COLLABORATIF</p><h2>${escapeHtml(group.name)}</h2><p class="muted">${escapeHtml([group.subject, group.filiere, group.preferred_level].filter(Boolean).join(' · '))}</p></div><span class="tag">${group.recruitment_open ? 'Recrutement ouvert' : 'Recrutement fermé'}</span></div>
    <p>${escapeHtml(group.description || 'Aucune description.')}</p><h3>Objectif</h3><p>${escapeHtml(group.objective || 'À définir par l’équipe.')}</p><div class="skill-tags">${(group.skills_wanted || []).map(skill => `<span class="tag">${escapeHtml(skill)}</span>`).join('')}</div>
    <p class="muted">${group.member_count} / ${group.max_members} membres · ${group.deadline ? `Échéance : ${escapeHtml(dateLabel(group.deadline))}` : 'Sans échéance'} · ${group.visibility === 'private' ? 'Groupe privé' : 'Groupe public'}</p>
    <div class="group-detail-actions">${joinAction}${ownerActions}${group.joined && group.member_role !== 'owner' ? `<button class="icon-btn" data-group-leave="${group.id}">Quitter le groupe</button>` : ''}</div>
    <h3>Membres</h3><div class="group-members">${members || '<div class="empty-state">Aucun membre pour le moment.</div>'}</div>
    ${group.join_requests?.length ? `<h3>Demandes d’adhésion</h3><div class="group-members">${requests}</div>` : ''}${invitePicker}
    ${activity ? `<h3>Activité récente</h3><div class="group-activity">${activity}</div>` : ''}${group.joined ? `<section class="collab-workspace"><div class="section-head"><div><h3>Discussion de l’équipe</h3><p class="muted" data-chat-status role="status">Connexion en cours…</p></div><button class="icon-btn" type="button" data-collab-tab="files">Fichiers partagés</button></div><form class="chat-search" data-chat-search><input name="q" type="search" maxlength="200" placeholder="Rechercher dans la discussion"><button class="icon-btn">Rechercher</button><button class="icon-btn" type="button" data-chat-clear-search>Effacer</button></form><div class="chat-layout"><div class="chat-panel"><div class="chat-messages" data-chat-messages aria-live="polite"><p class="muted">Chargement des messages…</p></div><button class="icon-btn chat-older" type="button" data-chat-older hidden>Charger les messages précédents</button><div data-chat-reply class="chat-reply" hidden></div><form class="chat-compose" data-chat-compose><textarea name="body" rows="2" maxlength="4000" placeholder="Écrire un message…" aria-label="Message" ></textarea><div class="chat-compose-actions"><label class="icon-btn chat-attach">Joindre un fichier<input type="file" name="file" hidden></label><small data-chat-file-name>Aucun fichier sélectionné</small><button class="primary" type="submit">Envoyer</button></div><p class="form-error" data-chat-error role="alert"></p></form></div><aside class="chat-side"><h4>Membres en ligne</h4><div data-chat-presence class="chat-presence"><small>Connexion en cours…</small></div><h4>Fichiers récents</h4><div data-chat-files-preview class="chat-files-preview"><small>Chargement…</small></div><button class="icon-btn" type="button" data-collab-tab="files">Voir tous les fichiers</button></aside></div><section class="chat-files" data-chat-files-panel hidden><div class="section-head"><h3>Fichiers du groupe</h3><button type="button" class="icon-btn" data-collab-tab="chat">Retour à la discussion</button></div><form class="chat-file-search" data-file-search><input name="q" type="search" placeholder="Filtrer par nom ou auteur"><select name="kind"><option value="">Tous les types</option><option value="document">Documents</option><option value="image">Images</option><option value="archive">Archives</option></select><button class="icon-btn">Filtrer</button></form><form class="chat-file-upload" data-file-upload><label>Ajouter un fichier<input type="file" name="file" required></label><button class="primary">Téléverser</button><small data-file-status role="status"></small></form><div data-chat-files-list class="chat-files-list"><p class="muted">Chargement des fichiers…</p></div></section></section>` : '<p class="empty-state"><strong>La collaboration est réservée aux membres</strong><span>Rejoignez ce groupe pour accéder aux discussions et fichiers.</span></p>'}${taskWorkspace}`;
}

let currentGroupData = null;
let currentGroupTasks = new Map();
const taskStatuses = [['todo', 'À faire'], ['doing', 'En cours'], ['review', 'En révision'], ['done', 'Terminées']];
const taskViewModes = new Map();

function taskCardMarkup(task) {
  const assignees = task.assignees?.length ? task.assignees.map(person => escapeHtml(person.name)).join(', ') : 'Non affectée';
  const statusControl = task.can_change_status ? `<label class="task-status-control"><span class="sr-only">Statut de ${escapeHtml(task.title)}</span><select data-task-status="${task.id}">${taskStatuses.map(([key, label]) => `<option value="${key}" ${task.status === key ? 'selected' : ''}>${label}</option>`).join('')}</select></label>` : `<span class="tag">${escapeHtml(statusLabel(task.status))}</span>`;
  const controls = `${task.can_edit ? `<button class="icon-btn" data-task-edit="${task.id}">Modifier</button>` : ''}${task.can_delete ? `<button class="icon-btn danger" data-task-delete="${task.id}">Supprimer</button>` : ''}`;
  const comments = `<div data-task-extras="${task.id}" class="task-extras"><small>Chargement des commentaires et de l’historique à l’ouverture.</small></div><form class="task-comment-form" data-task-comment="${task.id}"><input name="body" maxlength="2000" placeholder="Ajouter un commentaire…" required><button class="icon-btn" type="submit">Commenter</button></form>`;
  return `<article class="task-card ${task.overdue ? 'is-overdue' : ''}" data-task-card="${task.id}" data-status="${task.status}"><div class="task-card-head"><span class="tag priority-${task.priority}">${escapeHtml(taskPriorities[task.priority] || task.priority)}</span>${statusControl}</div><h4>${escapeHtml(task.title)}</h4><p>${escapeHtml(task.description || 'Aucune description.')}</p><small>Responsable${task.assignees?.length === 1 ? '' : 's'} : ${assignees}</small><small>${task.due_at ? `Échéance ${escapeHtml(dateLabel(task.due_at))}` : 'Sans échéance'}${task.overdue ? ' · En retard' : ''}${task.estimate_hours != null ? ` · ${task.estimate_hours} h estimées` : ''}</small>${task.source_message_id ? `<button type="button" class="icon-btn" data-task-source="${task.source_message_id}">Voir le message source</button>` : ''}<div class="task-card-actions">${controls}</div><details data-task-details="${task.id}"><summary>Commentaires et historique</summary>${comments}</details></article>`;
}

function renderTaskBoard(payload, groupId) {
  const board = document.querySelector(`[data-task-board="${groupId}"]`); if (!board) return;
  currentGroupTasks = new Map((payload.tasks || []).map(task => [task.id, task]));
  const progress = payload.progress || { total: 0, done: 0, pct: 0 };
  document.querySelector('[data-task-progress]').textContent = `${progress.done} / ${progress.total} tâches terminées · ${progress.pct}%`;
  document.querySelector('[data-task-progress-bar]').style.width = `${progress.pct}%`;
  const columns = taskStatuses.map(([status, title]) => {
    const tasks = (payload.tasks || []).filter(task => task.status === status);
    return `<section class="kanban-column" aria-label="${title}"><div class="kanban-column-head"><h4>${title}</h4><span class="tag">${tasks.length}</span></div><div class="kanban-cards">${tasks.length ? tasks.map(taskCardMarkup).join('') : '<div class="empty-state compact"><span>Aucune tâche</span></div>'}</div></section>`;
  }).join('');
  board.innerHTML = columns || '<div class="empty-state">Aucune tâche.</div>';
  board.classList.toggle('is-list', taskViewModes.get(groupId) === 'list');
  board.querySelectorAll('[data-task-details]').forEach(details => details.addEventListener('toggle', async () => {
    if (!details.open || details.dataset.loaded) return;
    details.dataset.loaded = 'true';
    const target = details.querySelector(`[data-task-extras="${details.dataset.taskDetails}"]`);
    try {
      const item = await apiFetch(`/api/tasks/${details.dataset.taskDetails}`);
      target.innerHTML = `<div class="task-comments">${item.comments.length ? item.comments.map(comment => `<p><strong>${escapeHtml(comment.author_name)}</strong> · ${escapeHtml(dateLabel(comment.created_at))}<br>${escapeHtml(comment.body)}</p>`).join('') : '<small>Aucun commentaire.</small>'}</div><div class="task-history">${item.history.map(entry => `<small>${escapeHtml(entry.actor_name)} · ${escapeHtml(entry.detail)} · ${escapeHtml(dateLabel(entry.created_at))}</small>`).join('')}</div>`;
    } catch (error) { target.textContent = error.payload?.detail || 'Impossible de charger le détail.'; }
  }));
}

async function loadTaskBoard(groupId) {
  const form = document.querySelector(`[data-task-filters="${groupId}"]`); if (!form) return;
  const params = new URLSearchParams();
  for (const [key, value] of new FormData(form)) if (value) params.set(key, value);
  if (form.elements.late.checked) params.set('late', 'true');
  const board = document.querySelector(`[data-task-board="${groupId}"]`); board.innerHTML = '<p class="muted" role="status">Chargement des tâches…</p>';
  try { renderTaskBoard(await apiFetch(`/api/groups/${groupId}/tasks?${params}`), groupId); }
  catch (error) { board.innerHTML = `<p class="form-error" role="alert">${escapeHtml(error.payload?.detail || 'Les tâches ne peuvent pas être chargées.')}</p>`; }
}

function editGroupForm(group) {
  const form = document.querySelector('#groupCreateForm');
  form.elements.group_id.value = group.id;
  ['name', 'project_name', 'subject', 'filiere', 'preferred_level', 'max_members', 'description', 'objective', 'deadline', 'visibility'].forEach(key => { form.elements[key].value = group[key] ?? ''; });
  form.elements.skills_wanted.value = (group.skills_wanted || []).join(', ');
  form.elements.recruitment_open.checked = group.recruitment_open;
  form.querySelector('h2').textContent = 'Modifier les paramètres du groupe';
  form.querySelector('[type="submit"]').textContent = 'Enregistrer';
  form.hidden = false;
  document.querySelector('#groupDetail').hidden = true;
  document.querySelector('#groupSearchForm').hidden = true;
  document.querySelector('#groupDiscoveryList').hidden = true;
}

async function openGroup(groupId) {
  stopGroupCollab();
  const detail = document.querySelector('#groupDetail');
  detail.hidden = false; detail.innerHTML = '<p role="status">Chargement du projet…</p>';
  document.querySelector('#groupCreateForm').hidden = true;
  document.querySelector('#groupSearchForm').hidden = true;
  document.querySelector('#groupDiscoveryList').hidden = true;
  try { const group = await apiFetch(`/api/groups/${groupId}`); currentGroupData = group; detail.innerHTML = groupDetailMarkup(group); if (group.joined) { await loadTaskBoard(groupId); await startGroupCollab(group); } }
  catch (error) { detail.innerHTML = `<p class="form-error" role="alert">${escapeHtml(error.payload?.detail || 'Impossible de charger ce groupe.')}</p><button class="icon-btn" data-back-groups>Retour</button>`; }
}

let chatSocket = null;
let chatReconnectTimer = null;
let chatPollTimer = null;
let chatGroupId = null;
let chatBefore = null;
let chatHasMore = false;
let chatQuery = '';
let chatReplyTo = null;
let chatMessages = [];
let chatOnline = new Set();
let chatSequence = 0;

function stopGroupCollab() {
  chatGroupId = null; chatSequence++;
  if (chatSocket) { chatSocket.onclose = null; chatSocket.close(); chatSocket = null; }
  clearTimeout(chatReconnectTimer); clearInterval(chatPollTimer);
}

function chatMessageMarkup(message) {
  const canModerate = ['owner', 'admin'].includes(currentGroupData?.member_role);
  const reactions = (message.reactions || []).map(reaction => `<button class="chat-reaction ${reaction.mine ? 'is-mine' : ''}" data-chat-react="${message.id}" data-emoji="${escapeHtml(reaction.emoji)}" aria-pressed="${reaction.mine ? 'true' : 'false'}">${escapeHtml(reaction.emoji)} ${reaction.count}</button>`).join('');
  const file = message.file ? `<a class="chat-attachment" href="${escapeHtml(message.file.url || `/api/group-files/${message.file.id}`)}" target="_blank" rel="noopener">▧ ${escapeHtml(message.file.name)} · ${formatBytes(message.file.size)}</a>` : '';
  const reply = message.reply ? `<button class="chat-reply-quote" data-chat-jump="${message.reply.id}">↳ ${escapeHtml(message.reply.author)} : ${escapeHtml(message.reply.excerpt)}</button>` : '';
  const task = message.task_id ? `<a class="chat-task-link" href="#" data-chat-task="${message.task_id}">✓ Tâche liée</a>` : '';
  return `<article class="chat-message ${message.mine ? 'mine' : ''} ${message.deleted ? 'is-deleted' : ''}" data-chat-message="${message.id}"><div class="chat-message-head"><strong>${escapeHtml(message.author.name)}</strong><small>${escapeHtml(dateLabel(message.created_at))}${message.edited ? ' · modifié' : ''}</small></div>${reply}<p>${message.deleted ? '<em>Message supprimé</em>' : escapeHtml(message.body).replace(/\n/g, '<br>')}</p>${file}${task}<div class="chat-message-actions">${!message.deleted ? `<button class="icon-btn" data-chat-reply-to="${message.id}">Répondre</button>${message.mine ? `<button class="icon-btn" data-chat-edit="${message.id}">Modifier</button>` : ''}<button class="icon-btn" data-chat-convert="${message.id}" ${message.task_id ? 'disabled title="Déjà converti en tâche"' : ''}>Transformer en tâche</button>${message.mine || canModerate ? `<button class="icon-btn" data-chat-delete="${message.id}">Supprimer</button>` : ''}<button class="icon-btn" data-chat-react="${message.id}" data-emoji="👍">👍</button><button class="icon-btn" data-chat-react="${message.id}" data-emoji="✅">✅</button><button class="icon-btn" data-chat-react="${message.id}" data-emoji="❓">❓</button><button class="icon-btn" data-chat-react="${message.id}" data-emoji="👀">👀</button>` : ''}</div><div class="chat-reactions">${reactions}</div><div data-chat-convert-form="${message.id}" class="chat-convert-form" hidden></div></article>`;
}

function renderChatMessages(items, append = false) {
  const box = document.querySelector('[data-chat-messages]'); if (!box) return;
  chatMessages = append ? [...items, ...chatMessages] : items;
  box.innerHTML = chatMessages.length ? chatMessages.map(chatMessageMarkup).join('') : `<div class="empty-state compact"><strong>${chatQuery ? 'Aucun résultat' : 'La discussion démarre ici'}</strong><span>${chatQuery ? 'Essayez un autre terme.' : 'Soyez le premier à partager une idée avec l’équipe.'}</span></div>`;
  if (!append) box.scrollTop = box.scrollHeight;
  const last = chatMessages.at(-1)?.id || 0;
  const older = document.querySelector('[data-chat-older]'); if (older) older.hidden = !chatHasMore;
  if (last) apiFetch(`/api/groups/${chatGroupId}/messages/read`, { method: 'POST', body: JSON.stringify({ last_message_id: last }) }).catch(() => {});
}

async function loadChatMessages({ append = false } = {}) {
  if (!chatGroupId) return;
  const params = new URLSearchParams({ limit: '40' }); if (chatQuery) params.set('q', chatQuery); if (append && chatBefore) params.set('before', chatBefore);
  const payload = await apiFetch(`/api/groups/${chatGroupId}/messages?${params}`);
  chatHasMore = payload.has_more; chatBefore = payload.next_before;
  renderChatMessages(payload.messages, append);
}

async function loadGroupFiles(groupId, query = '', kind = '') {
  const params = new URLSearchParams(); if (query) params.set('q', query); if (kind) params.set('kind', kind);
  const files = await apiFetch(`/api/groups/${groupId}/files?${params}`);
  const canManageFiles = ['owner', 'admin'].includes(currentGroupData?.member_role);
  const markup = files.length ? files.map(file => `<div class="chat-file-row"><span class="file-type-icon">${file.kind === 'image' ? '▧' : file.kind === 'archive' ? '▤' : '▱'}</span><div><strong>${escapeHtml(file.name)}</strong><small>${escapeHtml(file.uploader_name || 'Membre')} · ${formatBytes(file.size)} · ${escapeHtml(dateLabel(file.created_at))}</small></div><a class="icon-btn" href="${escapeHtml(file.url)}" target="_blank" rel="noopener">Télécharger</a>${file.uploader_id === currentProfile?.id || canManageFiles ? `<button class="icon-btn danger" data-file-delete="${file.id}" data-uploader="${file.uploader_id}">Supprimer</button>` : ''}</div>`).join('') : '<div class="empty-state compact"><span>Aucun fichier partagé pour le moment.</span></div>';
  const list = document.querySelector('[data-chat-files-list]'); if (list) list.innerHTML = markup;
  const preview = document.querySelector('[data-chat-files-preview]'); if (preview) preview.innerHTML = files.slice(0, 5).map(file => `<a href="${escapeHtml(file.url)}" target="_blank" rel="noopener">${escapeHtml(file.name)} <small>${formatBytes(file.size)}</small></a>`).join('') || '<small>Aucun fichier récent.</small>';
}

function connectGroupSocket(groupId, sequence) {
  if (!chatGroupId || chatGroupId !== groupId || sequence !== chatSequence) return;
  const status = document.querySelector('[data-chat-status]');
  try {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    chatSocket = new WebSocket(`${protocol}//${location.host}/ws/groups/${groupId}`);
    chatSocket.onopen = () => {
      if (status) status.textContent = 'Connecté · temps réel actif';
      chatSocket.send('ping');
      // Recharger depuis SQLite à chaque ouverture pour rattraper les événements manqués.
      chatBefore = null;
      loadChatMessages().catch(() => {});
      loadGroupFiles(groupId).catch(() => {});
    };
    chatSocket.onmessage = event => {
      let data; try { data = JSON.parse(event.data); } catch (_) { return; }
      if (data.type === 'presence_snapshot') { chatOnline = new Set(data.user_ids || []); }
      else if (data.type === 'presence') { data.online ? chatOnline.add(data.user_id) : chatOnline.delete(data.user_id); }
      else if (data.type?.startsWith('message_')) { loadChatMessages().catch(() => {}); }
      else if (data.type === 'task_created_from_message') { loadChatMessages().catch(() => {}); loadTaskBoard(groupId).catch(() => {}); }
      else if (data.type === 'file_uploaded' || data.type === 'file_deleted') { loadGroupFiles(groupId).catch(() => {}); }
      const presence = document.querySelector('[data-chat-presence]');
      if (presence && currentGroupData) presence.innerHTML = currentGroupData.members.map(member => `<span class="presence-member"><i class="presence-dot ${chatOnline.has(member.id) ? 'online' : ''}"></i>${escapeHtml(member.name)}</span>`).join('');
    };
    chatSocket.onclose = () => { if (status) status.textContent = 'Reconnexion en cours… · actualisation de secours active'; chatReconnectTimer = setTimeout(() => connectGroupSocket(groupId, sequence), 2500); };
    chatSocket.onerror = () => chatSocket?.close();
  } catch (_) { if (status) status.textContent = 'Temps réel indisponible · actualisation de secours active'; }
}

async function startGroupCollab(group) {
  stopGroupCollab(); if (!group.joined) return;
  chatGroupId = Number(group.id); chatBefore = null; chatHasMore = false; chatQuery = ''; chatReplyTo = null; chatMessages = []; chatOnline.clear();
  const sequence = chatSequence;
  try { await Promise.all([loadChatMessages(), loadGroupFiles(group.id)]); }
  catch (error) { const box = document.querySelector('[data-chat-messages]'); if (box) box.innerHTML = `<p class="form-error" role="alert">${escapeHtml(error.payload?.detail || 'Impossible de charger la discussion.')}</p>`; }
  connectGroupSocket(Number(group.id), sequence);
  chatPollTimer = setInterval(() => { if (typeof WebSocket === 'undefined' || chatSocket?.readyState !== WebSocket.OPEN) { loadChatMessages().catch(() => {}); loadGroupFiles(group.id).catch(() => {}); } }, 6000);
}

function convertFormMarkup(message) {
  const members = currentGroupData.members.map(member => `<option value="${member.id}">${escapeHtml(member.name)}</option>`).join('');
  return `<form class="profile-form-grid" data-chat-convert-form-submit="${message.id}"><label>Titre<input name="title" maxlength="140" required value="${escapeHtml((message.body.split('\n')[0] || '').slice(0, 140))}"></label><label>Priorité<select name="priority"><option value="low">Faible</option><option value="normal" selected>Normale</option><option value="high">Élevée</option><option value="urgent">Urgente</option></select></label><label>Échéance<input name="due_at" type="date"></label><label class="profile-control-wide">Description<textarea name="description" rows="3" maxlength="4000">${escapeHtml(message.body)}</textarea></label><label>Responsables<select name="assignee_ids" multiple size="3">${members}</select></label><div><button class="primary">Créer la tâche</button><button type="button" class="icon-btn" data-chat-convert-cancel="${message.id}">Annuler</button></div><p class="form-error" data-convert-error role="alert"></p></form>`;
}

document.querySelector('#groupDetail').addEventListener('submit', async event => {
  const form = event.target;
  if (form.matches('[data-chat-search]')) { event.preventDefault(); chatQuery = form.elements.q.value.trim(); chatBefore = null; loadChatMessages().catch(error => toast(error.payload?.detail || 'Recherche impossible.')); return; }
  if (form.matches('[data-file-search]')) { event.preventDefault(); loadGroupFiles(chatGroupId, form.elements.q.value.trim(), form.elements.kind.value).catch(error => toast(error.payload?.detail || 'Filtrage impossible.')); return; }
  if (form.matches('[data-chat-compose]')) {
    event.preventDefault(); const body = form.elements.body.value.trim(); const selected = form.elements.file.files[0]; const errorNode = form.querySelector('[data-chat-error]'); errorNode.textContent = '';
    if (!body && !selected) { errorNode.textContent = 'Écrivez un message ou joignez un fichier.'; return; }
    const submit = form.querySelector('[type="submit"]'); submit.disabled = true;
    try { let file_id = null; if (selected) { const data = new FormData(); data.append('file', selected); const file = await apiFetch(`/api/groups/${chatGroupId}/files`, { method: 'POST', body: data }); file_id = file.id; } await apiFetch(`/api/groups/${chatGroupId}/messages`, { method: 'POST', body: JSON.stringify({ body, reply_to: chatReplyTo, file_id }) }); form.reset(); chatReplyTo = null; document.querySelector('[data-chat-reply]').hidden = true; document.querySelector('[data-chat-file-name]').textContent = 'Aucun fichier sélectionné'; chatQuery = ''; chatBefore = null; await loadChatMessages(); }
    catch (error) { errorNode.textContent = error.payload?.detail || 'Le message n’a pas pu être envoyé.'; }
    finally { submit.disabled = false; }
    return;
  }
  if (form.matches('[data-file-upload]')) { event.preventDefault(); const file = form.elements.file.files[0]; const status = form.querySelector('[data-file-status]'); if (!file) return; const button = form.querySelector('button'); button.disabled = true; status.textContent = 'Téléversement…'; try { const data = new FormData(); data.append('file', file); await apiFetch(`/api/groups/${chatGroupId}/files`, { method: 'POST', body: data }); form.reset(); status.textContent = 'Fichier partagé.'; await loadGroupFiles(chatGroupId); } catch (error) { status.textContent = error.payload?.detail || 'Échec du téléversement.'; } finally { button.disabled = false; } return; }
  if (form.matches('[data-chat-convert-form-submit]')) { event.preventDefault(); const id = Number(form.dataset.chatConvertFormSubmit); const assignee_ids = [...form.elements.assignee_ids.selectedOptions].map(option => Number(option.value)); const data = { title: form.elements.title.value, description: form.elements.description.value, priority: form.elements.priority.value, due_at: form.elements.due_at.value || null, assignee_ids }; const errorNode = form.querySelector('[data-convert-error]'); try { await apiFetch(`/api/messages/${id}/convert-to-task`, { method: 'POST', body: JSON.stringify(data) }); toast('Tâche créée à partir du message.'); await Promise.all([loadChatMessages(), loadTaskBoard(chatGroupId)]); } catch (error) { errorNode.textContent = error.payload?.detail?.message || error.payload?.detail || 'La tâche n’a pas pu être créée.'; } }
});

document.querySelector('#groupDetail').addEventListener('change', event => { if (event.target.matches('[data-chat-compose] input[type=file]')) document.querySelector('[data-chat-file-name]').textContent = event.target.files[0]?.name || 'Aucun fichier sélectionné'; });
document.querySelector('#groupDetail').addEventListener('click', async event => {
  const button = event.target.closest('button, a[data-chat-task]'); if (!button) return;
  if (button.dataset.collabTab) { const files = button.dataset.collabTab === 'files'; document.querySelector('.chat-layout').hidden = files; document.querySelector('.chat-search').hidden = files; document.querySelector('.chat-files').hidden = !files; if (files) loadGroupFiles(chatGroupId).catch(error => toast(error.payload?.detail || 'Fichiers indisponibles.')); return; }
  if (button.hasAttribute('data-chat-older')) { try { await loadChatMessages({ append: true }); } catch (_) { toast('Les anciens messages sont indisponibles.'); } return; }
  if (button.hasAttribute('data-chat-clear-search')) { const form = document.querySelector('[data-chat-search]'); form.reset(); chatQuery = ''; chatBefore = null; loadChatMessages().catch(() => {}); return; }
  if (button.dataset.chatReplyTo) { const message = chatMessages.find(item => item.id === Number(button.dataset.chatReplyTo)); if (!message) return; chatReplyTo = message.id; const reply = document.querySelector('[data-chat-reply]'); reply.hidden = false; reply.innerHTML = `Réponse à ${escapeHtml(message.author.name)} : ${escapeHtml(message.body.slice(0, 100))} <button type="button" class="icon-btn" data-chat-reply-cancel>Annuler</button>`; document.querySelector('[data-chat-compose] textarea').focus(); return; }
  if (button.hasAttribute('data-chat-reply-cancel')) { chatReplyTo = null; document.querySelector('[data-chat-reply]').hidden = true; return; }
  if (button.dataset.chatEdit) { const message = chatMessages.find(item => item.id === Number(button.dataset.chatEdit)); const body = prompt('Modifier le message', message?.body || ''); if (body == null) return; try { await apiFetch(`/api/messages/${button.dataset.chatEdit}`, { method: 'PUT', body: JSON.stringify({ body }) }); await loadChatMessages(); } catch (error) { toast(error.payload?.detail || 'Modification refusée.'); } return; }
  if (button.dataset.chatDelete && confirm('Supprimer ce message ?')) { try { await apiFetch(`/api/messages/${button.dataset.chatDelete}`, { method: 'DELETE' }); await loadChatMessages(); } catch (error) { toast(error.payload?.detail || 'Suppression refusée.'); } return; }
  if (button.dataset.chatReact) { try { await apiFetch(`/api/messages/${button.dataset.chatReact}/reactions`, { method: 'POST', body: JSON.stringify({ emoji: button.dataset.emoji }) }); await loadChatMessages(); } catch (error) { toast(error.payload?.detail || 'Réaction impossible.'); } return; }
  if (button.dataset.chatConvert) { const message = chatMessages.find(item => item.id === Number(button.dataset.chatConvert)); const target = document.querySelector(`[data-chat-convert-form="${button.dataset.chatConvert}"]`); if (message && target) { target.innerHTML = convertFormMarkup(message); target.hidden = false; } return; }
  if (button.dataset.chatConvertCancel) { const target = document.querySelector(`[data-chat-convert-form="${button.dataset.chatConvertCancel}"]`); if (target) target.hidden = true; return; }
  if (button.dataset.chatJump) { document.querySelector(`[data-chat-message="${button.dataset.chatJump}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }); return; }
  if (button.dataset.chatTask) { event.preventDefault(); const card = document.querySelector(`[data-task-card="${button.dataset.chatTask}"]`); if (card) { card.scrollIntoView({ behavior: 'smooth', block: 'center' }); card.querySelector('details')?.setAttribute('open', ''); } else toast('La tâche liée ne figure pas dans le tableau chargé.'); return; }
  if (button.dataset.taskSource) { const sourceId = Number(button.dataset.taskSource); const layout = document.querySelector('.chat-layout'); if (layout) { layout.hidden = false; document.querySelector('.chat-files').hidden = true; document.querySelector('.chat-search').hidden = false; document.querySelector('[data-chat-search]').reset(); chatQuery = ''; const payload = await apiFetch(`/api/groups/${chatGroupId}/messages?before=${sourceId + 1}&limit=40`); chatHasMore = payload.has_more; chatBefore = payload.next_before; renderChatMessages(payload.messages); document.querySelector(`[data-chat-message="${sourceId}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }); } return; }
  if (button.dataset.fileDelete && confirm('Supprimer ce fichier partagé ?')) { try { await apiFetch(`/api/group-files/${button.dataset.fileDelete}`, { method: 'DELETE' }); await loadGroupFiles(chatGroupId); } catch (error) { toast(error.payload?.detail || 'Suppression refusée.'); } }
});

function formatBytes(size) { if (!Number.isFinite(size)) return ''; if (size < 1024) return `${size} o`; if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} Ko`; return `${(size / (1024 * 1024)).toFixed(1)} Mo`; }

document.querySelector('#groupSearchForm').addEventListener('submit', event => { event.preventDefault(); loadGroupDiscovery(); });
document.querySelector('#newGroupButton').addEventListener('click', () => { const form = document.querySelector('#groupCreateForm'); form.reset(); form.elements.group_id.value = ''; form.querySelector('h2').textContent = 'Créer un groupe de travail'; form.querySelector('[type="submit"]').textContent = 'Créer le groupe'; form.hidden = false; document.querySelector('#groupDetail').hidden = true; });
document.querySelector('#cancelGroupCreate').addEventListener('click', () => { const form = document.querySelector('#groupCreateForm'); const groupId = form.elements.group_id.value; form.hidden = true; form.reset(); form.elements.group_id.value = ''; if (groupId) openGroup(groupId); else { document.querySelector('#groupSearchForm').hidden = false; document.querySelector('#groupDiscoveryList').hidden = false; } });
document.querySelector('#groupCreateForm').addEventListener('submit', async event => {
  event.preventDefault(); const form = event.currentTarget; const data = Object.fromEntries(new FormData(form));
  const groupId = data.group_id; delete data.group_id;
  data.max_members = Number(data.max_members); data.skills_wanted = (data.skills_wanted || '').split(',').map(value => value.trim()).filter(Boolean); data.recruitment_open = form.elements.recruitment_open.checked;
  try { const group = groupId ? await apiFetch(`/api/groups/${groupId}`, { method: 'PUT', body: JSON.stringify(data) }) : await apiFetch('/api/groups', { method: 'POST', body: JSON.stringify(data) }); form.reset(); form.hidden = true; form.elements.group_id.value = ''; toast(groupId ? 'Les paramètres ont été enregistrés.' : 'Votre groupe a été créé.'); await loadGroupDiscovery(); await openGroup(group.id); }
  catch (error) { document.querySelector('#groupCreateError').textContent = error.payload?.detail || 'Le groupe n’a pas pu être créé.'; }
});

document.querySelector('#groupDiscoveryList').addEventListener('click', async event => {
  const join = event.target.closest('[data-group-join]'); const open = event.target.closest('[data-group-open]');
  if (open) { await openGroup(open.dataset.groupOpen); return; }
  if (join) { try { await apiFetch(`/api/groups/${join.dataset.groupJoin}/join`, { method: 'POST' }); toast('Vous avez rejoint le groupe.'); await loadGroupDiscovery(); await openGroup(join.dataset.groupJoin); } catch (error) { toast(error.payload?.detail || 'Impossible de rejoindre ce groupe.'); } }
});

let inviteSearchSequence = 0;
document.querySelector('#groupDetail').addEventListener('input', async event => {
  const input = event.target.closest('[data-invite-search]'); if (!input) return;
  const sequence = ++inviteSearchSequence; const groupId = input.dataset.inviteSearch; const result = document.querySelector(`[data-invite-results="${groupId}"]`); const q = input.value.trim();
  if (q.length < 2) { result.innerHTML = '<small>Saisissez au moins deux caractères.</small>'; return; }
  result.innerHTML = '<small>Recherche…</small>';
  await new Promise(resolve => setTimeout(resolve, 220));
  if (sequence !== inviteSearchSequence) return;
  try {
    const people = await apiFetch(`/api/students?q=${encodeURIComponent(q)}`);
    if (sequence !== inviteSearchSequence) return;
    result.innerHTML = people.slice(0, 6).map(person => `<div class="invite-result"><span>${escapeHtml(person.name)} · ${escapeHtml([person.filiere, person.level].filter(Boolean).join(' · '))}</span><button type="button" class="icon-btn" data-invite-student="${person.id}" data-invite-group="${groupId}">Inviter</button></div>`).join('') || '<small>Aucun étudiant visible ne correspond.</small>';
  } catch (_) { result.innerHTML = '<small>Recherche momentanément indisponible.</small>'; }
});

document.querySelector('#groupDetail').addEventListener('click', async event => {
  const target = event.target.closest('button'); if (!target) return;
  if (target.hasAttribute('data-back-groups')) { document.querySelector('#groupDetail').hidden = true; document.querySelector('#groupSearchForm').hidden = false; document.querySelector('#groupDiscoveryList').hidden = false; return; }
  try {
    if (target.dataset.groupJoin) { await apiFetch(`/api/groups/${target.dataset.groupJoin}/join`, { method: 'POST' }); toast('Vous avez rejoint le groupe.'); await openGroup(target.dataset.groupJoin); }
    else if (target.dataset.groupRequest) { await apiFetch(`/api/groups/${target.dataset.groupRequest}/requests`, { method: 'POST', body: JSON.stringify({ message: '' }) }); toast('Votre demande a été envoyée.'); target.disabled = true; }
    else if (target.dataset.groupLeave && confirm('Quitter ce groupe ?')) { await apiFetch(`/api/groups/${target.dataset.groupLeave}/membership`, { method: 'DELETE' }); toast('Vous avez quitté le groupe.'); await loadGroupDiscovery(); await openGroup(target.dataset.groupLeave); }
    else if (target.dataset.inviteStudent) { await apiFetch(`/api/groups/${target.dataset.inviteGroup}/invitations`, { method: 'POST', body: JSON.stringify({ user_id: Number(target.dataset.inviteStudent) }) }); toast('Invitation envoyée.'); await openGroup(target.dataset.inviteGroup); }
    else if (target.dataset.transferOwner && confirm('Transférer la propriété à ce membre ? Vous deviendrez administrateur.')) { await apiFetch(`/api/groups/${target.dataset.groupId}/owner`, { method: 'POST', body: JSON.stringify({ user_id: Number(target.dataset.transferOwner) }) }); toast('La propriété a été transférée.'); await openGroup(target.dataset.groupId); }
    else if (target.dataset.editGroup && currentGroupData) editGroupForm(currentGroupData);
    else if (target.dataset.memberRole) { await apiFetch(`/api/groups/${target.dataset.groupId}/members/${target.dataset.memberRole}/role`, { method: 'PUT', body: JSON.stringify({ role: target.dataset.role }) }); toast('Le rôle a été modifié.'); await openGroup(target.dataset.groupId); }
    else if (target.dataset.removeMember && confirm('Retirer ce membre du groupe ?')) { await apiFetch(`/api/groups/${target.dataset.groupId}/members/${target.dataset.removeMember}`, { method: 'DELETE' }); toast('Le membre a été retiré.'); await openGroup(target.dataset.groupId); }
    else if (target.dataset.deleteGroup && confirm('Supprimer définitivement ce groupe et ses données collaboratives ?')) { await apiFetch(`/api/groups/${target.dataset.deleteGroup}`, { method: 'DELETE' }); toast('Groupe supprimé.'); await loadGroupDiscovery(); document.querySelector('#groupDetail').hidden = true; }
    else if (target.dataset.toggleRecruitment) { const group = await apiFetch(`/api/groups/${target.dataset.toggleRecruitment}`); const body = { name: group.name, description: group.description, filiere: group.filiere, subject: group.subject, project_name: group.project_name, objective: group.objective, max_members: group.max_members, skills_wanted: group.skills_wanted, visibility: group.visibility, preferred_level: group.preferred_level, deadline: group.deadline, recruitment_open: target.dataset.open === 'true' }; await apiFetch(`/api/groups/${group.id}`, { method: 'PUT', body: JSON.stringify(body) }); await openGroup(group.id); }
    else if (target.dataset.requestAccept || target.dataset.requestDecline) { const accept = Boolean(target.dataset.requestAccept); const id = target.dataset.groupId; await apiFetch(`/api/groups/${id}/requests/${target.dataset.requestAccept || target.dataset.requestDecline}/respond?accept=${accept}`, { method: 'POST' }); await openGroup(id); }
  } catch (error) { toast(error.payload?.detail || 'Cette action n’a pas abouti.'); }
});

let editingTaskId = null;
function showTaskEditor(groupId, task = null) {
  const form = document.querySelector(`[data-task-editor="${groupId}"]`); if (!form) return;
  editingTaskId = task?.id || null;
  form.reset();
  form.querySelector('[data-task-editor-heading]').textContent = task ? 'Modifier la tâche' : 'Nouvelle tâche';
  form.elements.title.value = task?.title || '';
  form.elements.description.value = task?.description || '';
  form.elements.priority.value = task?.priority || 'normal';
  form.elements.starts_at.value = task?.starts_at?.slice(0, 10) || '';
  form.elements.due_at.value = task?.due_at?.slice(0, 10) || '';
  form.elements.estimate_hours.value = task?.estimate_hours ?? '';
  const selected = new Set((task?.assignees || []).map(item => String(item.id)));
  [...form.elements.assignee_ids.options].forEach(option => { option.selected = selected.has(option.value); });
  form.querySelector('[data-task-error]').textContent = '';
  form.hidden = false;
  form.elements.title.focus();
}

document.querySelector('#groupDetail').addEventListener('submit', async event => {
  const form = event.target;
  if (form.matches('[data-task-filters]')) { event.preventDefault(); loadTaskBoard(form.dataset.taskFilters); return; }
  if (form.matches('[data-task-comment]')) {
    event.preventDefault();
    try { await apiFetch(`/api/tasks/${form.dataset.taskComment}/comments`, { method: 'POST', body: JSON.stringify({ body: form.elements.body.value }) }); toast('Commentaire ajouté.'); await loadTaskBoard(currentGroupData.id); }
    catch (error) { toast(error.payload?.detail || 'Le commentaire n’a pas été enregistré.'); }
    return;
  }
  if (!form.matches('[data-task-editor]')) return;
  event.preventDefault();
  if (!form.reportValidity()) return;
  const groupId = Number(form.dataset.taskEditor);
  const assigneeIds = [...form.elements.assignee_ids.selectedOptions].map(option => Number(option.value));
  const body = {
    title: form.elements.title.value.trim(), description: form.elements.description.value.trim(), priority: form.elements.priority.value,
    starts_at: form.elements.starts_at.value || null, due_at: form.elements.due_at.value || null,
    estimate_hours: form.elements.estimate_hours.value === '' ? null : Number(form.elements.estimate_hours.value),
  };
  const errorNode = form.querySelector('[data-task-error]'); errorNode.textContent = '';
  try {
    if (editingTaskId) {
      await apiFetch(`/api/tasks/${editingTaskId}`, { method: 'PUT', body: JSON.stringify(body) });
      await apiFetch(`/api/tasks/${editingTaskId}/assign`, { method: 'POST', body: JSON.stringify({ user_ids: assigneeIds }) });
      toast('La tâche a été mise à jour.');
    } else {
      body.assignee_ids = assigneeIds;
      await apiFetch(`/api/groups/${groupId}/tasks`, { method: 'POST', body: JSON.stringify(body) });
      toast('La tâche a été créée.');
    }
    form.hidden = true; editingTaskId = null; await loadTaskBoard(groupId); await loadAccountData();
  } catch (error) { errorNode.textContent = error.payload?.detail || 'La tâche n’a pas pu être enregistrée.'; }
});

document.querySelector('#groupDetail').addEventListener('change', async event => {
  const select = event.target.closest('[data-task-status]'); if (!select) return;
  select.disabled = true;
  try { await apiFetch(`/api/tasks/${select.dataset.taskStatus}/status`, { method: 'POST', body: JSON.stringify({ status: select.value }) }); toast('Statut enregistré.'); await loadTaskBoard(currentGroupData.id); await loadAccountData(); }
  catch (error) { toast(error.payload?.detail || 'Le statut n’a pas été modifié.'); await loadTaskBoard(currentGroupData.id); }
});

document.querySelector('#groupDetail').addEventListener('click', async event => {
  const button = event.target.closest('button'); if (!button) return;
  const groupId = currentGroupData?.id;
  if (button.dataset.taskNew) { showTaskEditor(groupId); return; }
  if (button.hasAttribute('data-task-cancel')) { button.closest('form').hidden = true; editingTaskId = null; return; }
  if (button.hasAttribute('data-task-view-toggle')) { const mode = taskViewModes.get(groupId) === 'list' ? 'kanban' : 'list'; taskViewModes.set(groupId, mode); button.textContent = mode === 'list' ? 'Vue Kanban' : 'Vue liste'; document.querySelector(`[data-task-board="${groupId}"]`).classList.toggle('is-list', mode === 'list'); return; }
  if (button.dataset.taskEdit) { showTaskEditor(groupId, currentGroupTasks.get(Number(button.dataset.taskEdit))); return; }
  if (button.dataset.taskDelete && confirm('Supprimer cette tâche et son historique ?')) {
    try { await apiFetch(`/api/tasks/${button.dataset.taskDelete}`, { method: 'DELETE' }); toast('Tâche supprimée.'); await loadTaskBoard(groupId); await loadAccountData(); }
    catch (error) { toast(error.payload?.detail || 'La tâche n’a pas été supprimée.'); }
  }
});

document.querySelectorAll('.nav button').forEach(button => button.addEventListener('click', () => {
  if (button.dataset.view === 'discoverGroups') { document.querySelector('#groupDetail').hidden = true; document.querySelector('#groupCreateForm').hidden = true; document.querySelector('#groupSearchForm').hidden = false; document.querySelector('#groupDiscoveryList').hidden = false; loadGroupDiscovery(); }
}));

function studentCardMarkup(person) {
  const profile = `<div class="person-identity"><div class="avatar">${person.avatar_url ? `<img src="${escapeHtml(person.avatar_url)}" alt="">` : escapeHtml(person.initials || '?')}</div><div><h3>${escapeHtml(person.name)}</h3><small>${escapeHtml([person.school, person.faculty, person.filiere, person.level].filter(Boolean).join(' · '))}</small></div></div>`;
  const tags = [...(person.skills || []).map(tag => `Compétence · ${tag}`), ...(person.interests || []).map(tag => `Intérêt · ${tag}`), ...(person.project_types || []).map(tag => `Projet · ${tag}`)].slice(0, 8);
  let action = '<span class="tag">En attente</span>';
  if (person.connection_status === 'accepted') action = '<span class="tag">Connecté</span>';
  else if (person.connection_status === 'pending_sent') action = '<span class="tag">Demande envoyée</span>';
  else if (person.connection_status === 'pending_received') action = `<button class="primary" data-connection-accept="${person.id}">Accepter</button><button class="icon-btn" data-connection-decline="${person.id}">Refuser</button>`;
  else if (!person.connection_status) action = `<button class="primary" data-connect="${person.id}">Se connecter</button>`;
  return `<article class="discovery-card person-card">${profile}<p>${escapeHtml(person.bio || 'Aucune biographie renseignée.')}</p><p class="muted">Objectif : ${escapeHtml(person.focus_goal || 'Non renseigné')}</p><div class="skill-tags">${tags.map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join('')}</div>${person.recommendation?.explanation ? `<p class="recommendation-explanation">${escapeHtml(person.recommendation.explanation)}</p>` : ''}<div class="group-card-actions">${action}</div></article>`;
}

async function loadStudents(mode = 'recommendations') {
  const form = document.querySelector('#peopleSearchForm'); const list = document.querySelector('#peopleList'); const connections = document.querySelector('#connectionLists');
  form.hidden = mode !== 'search'; list.hidden = mode === 'connections'; connections.hidden = mode !== 'connections';
  document.querySelectorAll('[data-people-mode]').forEach(button => button.classList.toggle('primary', button.dataset.peopleMode === mode));
  document.querySelector('#peopleStatus').textContent = 'Chargement…';
  try {
    if (mode === 'connections') {
      const [data, invitations] = await Promise.all([apiFetch('/api/connections'), apiFetch('/api/group-invitations')]);
      const bucket = (items, label, responses = false, removable = false) => `<section class="connection-group"><h3>${label}</h3>${items.length ? items.map(item => `<div class="group-member"><div class="avatar">${escapeHtml(item.initials)}</div><div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml([item.filiere, item.school].filter(Boolean).join(' · '))}</small></div>${responses ? `<button class="primary" data-connection-accept="${item.id}">Accepter</button><button class="icon-btn" data-connection-decline="${item.id}">Refuser</button>` : ''}${removable ? `<button class="icon-btn" data-connection-remove="${item.id}">Supprimer</button>` : ''}</div>`).join('') : '<div class="empty-state compact"><span>Aucun élément pour le moment.</span></div>'}</section>`;
      const inviteMarkup = invitations.length ? `<section class="connection-group"><h3>Invitations à rejoindre un groupe</h3>${invitations.map(item => `<div class="group-member"><div><strong>${escapeHtml(item.group_name)}</strong><small>Invité par ${escapeHtml(item.inviter_name)}</small></div><button class="primary" data-group-invite-accept="${item.id}">Accepter</button><button class="icon-btn" data-group-invite-decline="${item.id}">Refuser</button></div>`).join('')}</section>` : '';
      connections.innerHTML = inviteMarkup + bucket(data.received, 'Demandes reçues', true) + bucket(data.sent, 'Demandes envoyées') + bucket(data.accepted, 'Connexions', false, true);
      document.querySelector('#peopleStatus').textContent = 'Gérez vos mises en relation et invitations.';
      return;
    }
    let people;
    if (mode === 'search') people = await apiFetch(`/api/students?${new URLSearchParams(new FormData(form)).toString()}`);
    else people = await apiFetch('/api/students/recommendations');
    list.innerHTML = people.length ? people.map(studentCardMarkup).join('') : '<div class="empty-state"><strong>Aucun profil à afficher</strong><span>Complétez vos critères de profil ou ajustez les filtres de recherche.</span></div>';
    document.querySelector('#peopleStatus').textContent = mode === 'recommendations' ? `${people.length} suggestion${people.length === 1 ? '' : 's'} basée${people.length === 1 ? '' : 's'} sur les informations de profil` : `${people.length} profil${people.length === 1 ? '' : 's'} trouvé${people.length === 1 ? '' : 's'}`;
  } catch (_) { document.querySelector('#peopleStatus').textContent = 'Les profils ne peuvent pas être chargés. Réessayez.'; }
}

let peopleMode = 'recommendations';
document.querySelectorAll('[data-people-mode]').forEach(button => button.addEventListener('click', () => { peopleMode = button.dataset.peopleMode; loadStudents(peopleMode); }));
document.querySelector('#peopleSearchForm').addEventListener('submit', event => { event.preventDefault(); peopleMode = 'search'; loadStudents('search'); });
document.querySelector('#peopleList').addEventListener('click', async event => {
  const button = event.target.closest('button'); if (!button) return;
  try {
    if (button.dataset.connect) await apiFetch('/api/connections', { method: 'POST', body: JSON.stringify({ user_id: Number(button.dataset.connect) }) });
    else if (button.dataset.connectionAccept || button.dataset.connectionDecline) { const accept = Boolean(button.dataset.connectionAccept); const other = button.dataset.connectionAccept || button.dataset.connectionDecline; await apiFetch(`/api/connections/${other}/respond?accept=${accept}`, { method: 'POST' }); }
    else return;
    toast('Votre mise en relation a été mise à jour.'); await loadStudents(peopleMode);
  } catch (error) { toast(error.payload?.detail || 'La mise en relation a échoué.'); }
});
document.querySelector('#connectionLists').addEventListener('click', async event => {
  const button = event.target.closest('button'); if (!button) return;
  try {
    if (button.dataset.connectionAccept || button.dataset.connectionDecline) { const accept = Boolean(button.dataset.connectionAccept); const id = button.dataset.connectionAccept || button.dataset.connectionDecline; await apiFetch(`/api/connections/${id}/respond?accept=${accept}`, { method: 'POST' }); }
    else if (button.dataset.groupInviteAccept || button.dataset.groupInviteDecline) { const accept = Boolean(button.dataset.groupInviteAccept); const id = button.dataset.groupInviteAccept || button.dataset.groupInviteDecline; await apiFetch(`/api/group-invitations/${id}/respond?accept=${accept}`, { method: 'POST' }); }
    else if (button.dataset.connectionRemove) { if (!confirm('Supprimer cette connexion ?')) return; await apiFetch(`/api/connections/${button.dataset.connectionRemove}`, { method: 'DELETE' }); }
    await loadStudents('connections');
  } catch (error) { toast(error.payload?.detail || 'Cette action a échoué.'); }
});
document.querySelectorAll('.nav button').forEach(button => button.addEventListener('click', () => { if (button.dataset.view === 'people') loadStudents(peopleMode); }));
