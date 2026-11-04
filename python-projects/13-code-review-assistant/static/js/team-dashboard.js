/**
 * Teams page: switch between your teams, create one, answer invitations, manage members and roles,
 * share repositories, and see the team's analytics, leaderboard and activity.
 *
 * Everything that comes from the server (names, usernames, repository names ...) goes through
 * escapeHtml before it is put into the page.
 */

(() => {
'use strict';

const ROLES = ['admin', 'member', 'viewer'];
const ROLE_LABELS = { owner: 'Owner', admin: 'Admin', member: 'Member', viewer: 'Viewer' };

const state = { teams: [], team: null, me: null, charts: {}, myRepositories: [] };

function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value === null || value === undefined ? '' : String(value);
    return div.innerHTML.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function $(id) { return document.getElementById(id); }

function formatDate(value) {
    if (!value) return '';
    const date = new Date(value);
    return isNaN(date) ? '' : date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function remember(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* private window: the page works without it */ }
}
function recall(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
}

/** One request: answers {ok, status, data}; the server's reason is data.detail */
async function api(method, url, body) {
    const options = { method, credentials: 'include', headers: {} };
    if (body !== undefined) {
        options.headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(body);
    }
    try {
        const response = await fetch(url, options);
        let data = {};
        try { data = await response.json(); } catch (e) { /* no body */ }
        return { ok: response.ok, status: response.status, data };
    } catch (error) {
        return { ok: false, status: 0, data: { detail: 'Network error. Please check your connection.' } };
    }
}

function reason(result, fallback) {
    const detail = result.data && (result.data.detail || result.data.error);
    return typeof detail === 'string' && detail ? detail : fallback;
}

let toastTimer = null;
function toast(message, isError) {
    const box = $('toast');
    box.textContent = message;
    box.className = 'teams-toast' + (isError ? ' teams-toast--error' : '');
    box.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { box.hidden = true; }, 5000);
}

function can(permission) {
    return !!(state.team && state.team.permissions && state.team.permissions[permission]);
}
function myRole() { return state.team ? state.team.role : null; }

// ---------------------------------------------------------------------------------------------- start

document.addEventListener('DOMContentLoaded', async () => {
    wireEvents();
    await loadMe();
    await Promise.all([loadInvitations(), loadTeams()]);
});

async function loadMe() {
    const result = await api('GET', '/api/auth/me');
    state.me = result.ok ? result.data.user : null;
}

function wireEvents() {
    $('current-team').addEventListener('change', event => selectTeam(event.target.value));
    $('new-team-btn').addEventListener('click', openNewTeam);
    document.addEventListener('click', event => {
        const target = event.target.closest('[data-action]');
        if (!target) return;
        const action = target.dataset.action;
        if (action === 'new-team') openNewTeam();
        else if (action === 'close-modal') closeModals();
        else if (action === 'accept-invitation') answerInvitation(target.dataset.token, 'accept');
        else if (action === 'decline-invitation') answerInvitation(target.dataset.token, 'decline');
        else if (action === 'remove-member') removeMember(target.dataset.user, target.dataset.name);
        else if (action === 'cancel-invitation') cancelInvitation(target.dataset.id);
        else if (action === 'unshare') unshareRepository(target.dataset.id, target.dataset.name);
        else if (action === 'analyze') analyzeRepository(target.dataset.id);
    });
    document.addEventListener('keydown', event => { if (event.key === 'Escape') closeModals(); });
    document.querySelectorAll('.teams-modal').forEach(modal => {
        modal.addEventListener('mousedown', event => { if (event.target === modal) closeModals(); });
    });

    document.querySelectorAll('.teams-tab').forEach(tab => {
        tab.addEventListener('click', () => showTab(tab.dataset.tab));
    });

    $('team-settings-btn').addEventListener('click', openSettings);
    $('team-leave-btn').addEventListener('click', leaveTeam);
    $('team-delete-btn').addEventListener('click', deleteTeam);
    $('share-repo-btn').addEventListener('click', shareRepository);
    $('invite-form').addEventListener('submit', sendInvitation);
    $('new-team-form').addEventListener('submit', createTeam);
    $('settings-form').addEventListener('submit', saveSettings);

    // The short name follows the name until it is edited by hand
    let slugTouched = false;
    $('nt-slug').addEventListener('input', () => { slugTouched = true; });
    $('nt-name').addEventListener('input', event => {
        if (!slugTouched) $('nt-slug').value = slugify(event.target.value);
    });
    $('new-team-modal').resetSlug = () => { slugTouched = false; };
}

function slugify(text) {
    return text.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 50);
}

function showTab(name) {
    document.querySelectorAll('.teams-tab').forEach(tab => {
        const active = tab.dataset.tab === name;
        tab.classList.toggle('is-active', active);
        tab.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    document.querySelectorAll('.teams-panel').forEach(panel => {
        panel.hidden = panel.id !== 'panel-' + name;
    });
    remember('teams.tab', name);
}

function closeModals() {
    document.querySelectorAll('.teams-modal').forEach(modal => { modal.hidden = true; });
}

// ------------------------------------------------------------------------------------------ invitations

async function loadInvitations() {
    const result = await api('GET', '/api/me/invitations');
    const invitations = result.ok ? (result.data.invitations || []) : [];
    $('invitations-banner').hidden = invitations.length === 0;
    $('invitations-list').innerHTML = invitations.map(invitation => `
        <li class="teams-list__item">
            <div>
                <strong>${escapeHtml(invitation.team_name)}</strong>
                <span class="teams-muted"> invites you as ${escapeHtml(ROLE_LABELS[invitation.role] || invitation.role)}
                (until ${escapeHtml(formatDate(invitation.expires_at))})</span>
            </div>
            <div class="teams-inline">
                <button type="button" class="btn btn-primary btn-sm" data-action="accept-invitation" data-token="${escapeHtml(invitation.token)}">Accept</button>
                <button type="button" class="btn btn-secondary btn-sm" data-action="decline-invitation" data-token="${escapeHtml(invitation.token)}">Decline</button>
            </div>
        </li>`).join('');
}

async function answerInvitation(token, answer) {
    const result = await api('POST', `/api/invitations/${encodeURIComponent(token)}/${answer}`);
    if (!result.ok) {
        toast(reason(result, `Could not ${answer} the invitation`), true);
    } else if (answer === 'accept') {
        toast('You joined the team');
        const joined = result.data.team ? result.data.team.id : null;
        await loadTeams(joined);
    } else {
        toast('Invitation declined');
    }
    await loadInvitations();
}

// ------------------------------------------------------------------------------------------------ teams

async function loadTeams(preferredId) {
    const result = await api('GET', '/api/teams');
    if (!result.ok) {
        toast(reason(result, 'Could not load your teams'), true);
        return;
    }
    state.teams = result.data.teams || [];
    const select = $('current-team');
    select.innerHTML = state.teams.map(team =>
        `<option value="${escapeHtml(team.id)}">${escapeHtml(team.name)}</option>`).join('');

    const hasTeams = state.teams.length > 0;
    $('no-teams').hidden = hasTeams;
    select.disabled = !hasTeams;
    $('team-content').hidden = !hasTeams;
    if (!hasTeams) {
        state.team = null;
        return;
    }

    const wanted = preferredId || new URLSearchParams(location.search).get('team') || recall('teams.current');
    const chosen = state.teams.find(team => team.id === wanted) || state.teams[0];
    select.value = chosen.id;
    await selectTeam(chosen.id);
}

async function selectTeam(teamId) {
    const team = state.teams.find(t => t.id === teamId);
    if (!team) return;
    remember('teams.current', teamId);
    state.team = team;
    renderHeader();
    showTab(recall('teams.tab') || 'overview');
    await Promise.all([
        loadOverview(), loadRepositories(), loadMembers(), loadPending(), loadLeaderboard(), loadActivity()
    ]);
}

function renderHeader() {
    const team = state.team;
    $('team-name').textContent = team.name;
    $('team-description').textContent = team.description || 'No description';
    $('team-visibility').textContent = team.visibility === 'public' ? 'Public' : 'Private';
    $('team-role').textContent = 'You are ' + (ROLE_LABELS[team.role] || team.role);
    $('team-slug').textContent = team.slug;
    $('team-settings-btn').hidden = !can('can_manage_settings');
    $('team-delete-btn').hidden = myRole() !== 'owner';
    $('team-leave-btn').hidden = myRole() === 'owner';
    $('member-count').textContent = team.member_count;
    $('repo-count').textContent = team.repository_count;
    $('invite-card').hidden = !(can('can_manage_members') || team.allow_member_invites);

    const roles = can('can_manage_members') && myRole() === 'owner' ? ROLES : ['member', 'viewer'];
    $('invite-role').innerHTML = roles.map(role =>
        `<option value="${role}"${role === 'member' ? ' selected' : ''}>${ROLE_LABELS[role]}</option>`).join('');
}

async function refreshTeam() {
    const keep = state.team.id;
    const result = await api('GET', '/api/teams');
    if (result.ok) state.teams = result.data.teams || [];
    const fresh = state.teams.find(team => team.id === keep);
    if (!fresh) return loadTeams();
    state.team = fresh;
    $('current-team').innerHTML = state.teams.map(team =>
        `<option value="${escapeHtml(team.id)}">${escapeHtml(team.name)}</option>`).join('');
    $('current-team').value = keep;
    renderHeader();
}

// -------------------------------------------------------------------------------------------- new team

function openNewTeam() {
    $('new-team-form').reset();
    $('nt-error').hidden = true;
    $('new-team-modal').resetSlug();
    $('new-team-modal').hidden = false;
    $('nt-name').focus();
}

async function createTeam(event) {
    event.preventDefault();
    const result = await api('POST', '/api/teams', {
        name: $('nt-name').value.trim(),
        slug: $('nt-slug').value.trim(),
        description: $('nt-description').value.trim() || null,
        visibility: $('nt-visibility').value,
    });
    if (!result.ok) {
        $('nt-error').textContent = reason(result, 'Could not create the team');
        $('nt-error').hidden = false;
        return;
    }
    closeModals();
    toast('Team created');
    await loadTeams(result.data.team.id);
}

// ------------------------------------------------------------------------------------------- settings

function openSettings() {
    const team = state.team;
    $('ts-name').value = team.name;
    $('ts-description').value = team.description || '';
    $('ts-visibility').value = team.visibility;
    $('ts-invites').checked = !!team.allow_member_invites;
    $('ts-error').hidden = true;
    $('settings-modal').hidden = false;
    $('ts-name').focus();
}

async function saveSettings(event) {
    event.preventDefault();
    const result = await api('PUT', `/api/teams/${state.team.id}`, {
        name: $('ts-name').value.trim(),
        description: $('ts-description').value.trim(),
        visibility: $('ts-visibility').value,
        allow_member_invites: $('ts-invites').checked,
    });
    if (!result.ok) {
        $('ts-error').textContent = reason(result, 'Could not save the settings');
        $('ts-error').hidden = false;
        return;
    }
    closeModals();
    toast('Settings saved');
    await refreshTeam();
}

async function deleteTeam() {
    const team = state.team;
    if (!confirm(`Delete the team "${team.name}"? Its repositories go back to their owners. This cannot be undone.`)) return;
    const result = await api('DELETE', `/api/teams/${team.id}`);
    if (!result.ok) return toast(reason(result, 'Could not delete the team'), true);
    toast('Team deleted');
    await loadTeams();
}

async function leaveTeam() {
    const team = state.team;
    if (!confirm(`Leave the team "${team.name}"?`)) return;
    const result = await api('DELETE', `/api/teams/${team.id}/members/${state.me.id}`);
    if (!result.ok) return toast(reason(result, 'Could not leave the team'), true);
    toast('You left the team');
    await loadTeams();
}

// --------------------------------------------------------------------------------------------- overview

function destroyCharts() {
    Object.values(state.charts).forEach(chart => chart && chart.destroy());
    state.charts = {};
}

async function loadOverview() {
    const teamId = state.team.id;
    const result = await api('GET', `/api/teams/${teamId}/analytics`);
    destroyCharts();
    if (!result.ok || teamId !== state.team.id) return;
    const analytics = result.data;

    $('issue-count').textContent = analytics.total_issues || 0;
    const empty = !analytics.total_repositories;
    $('overview-empty').hidden = !empty;
    $('overview-charts').hidden = empty;
    if (empty || typeof Chart === 'undefined') return;

    const severity = analytics.issues_by_severity || {};
    state.charts.severity = new Chart($('severity-chart').getContext('2d'), {
        type: 'doughnut',
        data: {
            labels: ['Critical', 'Error', 'Warning', 'Info'],
            datasets: [{
                data: [severity.critical || 0, severity.error || 0, severity.warning || 0, severity.info || 0],
                backgroundColor: ['#be123c', '#dc2626', '#f59e0b', '#0ea5e9']
            }]
        },
        options: { responsive: true, maintainAspectRatio: false }
    });

    const categories = analytics.issues_by_category || {};
    state.charts.category = new Chart($('category-chart').getContext('2d'), {
        type: 'bar',
        data: {
            labels: Object.keys(categories),
            datasets: [{ label: 'Issues', data: Object.values(categories), backgroundColor: '#2563eb' }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
                   scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } }
    });

    const health = analytics.health_trend || [];
    state.charts.health = new Chart($('health-trend-chart').getContext('2d'), {
        type: 'line',
        data: {
            labels: health.map(point => point.date),
            datasets: [{ label: 'Health score', data: health.map(point => point.score),
                         borderColor: '#16a34a', backgroundColor: 'rgba(22, 163, 74, 0.1)', tension: 0.3, fill: true }]
        },
        options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true, max: 100 } } }
    });

    const activity = analytics.activity_trend || [];
    state.charts.activity = new Chart($('activity-chart').getContext('2d'), {
        type: 'bar',
        data: {
            labels: activity.map(point => point.date),
            datasets: [{ label: 'Analyses', data: activity.map(point => point.analyses), backgroundColor: '#2563eb' }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
                   scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } }
    });
}

// ---------------------------------------------------------------------------------------- repositories

async function loadRepositories() {
    const teamId = state.team.id;
    const [shared, mine] = await Promise.all([
        api('GET', `/api/teams/${teamId}/repositories`),
        api('GET', '/api/repositories'),
    ]);
    if (teamId !== state.team.id) return;

    const repositories = shared.ok ? (shared.data.repositories || []) : [];
    const scores = repositories.filter(repo => typeof repo.health_score === 'number');
    $('health-score').textContent = scores.length
        ? Math.round(scores.reduce((sum, repo) => sum + repo.health_score, 0) / scores.length) : '-';
    $('repo-count').textContent = repositories.length;

    $('repositories-grid').innerHTML = repositories.length ? repositories.map(repo => {
        const mineToo = state.me && repo.owner === state.me.username;
        const canUnshare = mineToo || can('can_manage_members');
        const counts = repo.severity_counts || {};
        return `
        <article class="teams-card teams-repo">
            <div class="teams-repo__head">
                <h3>${escapeHtml(repo.name)}</h3>
                <span class="teams-grade teams-grade--${escapeHtml(String(repo.health_grade || '').charAt(0).toLowerCase())}"
                      title="Health score ${escapeHtml(repo.health_score)}">${escapeHtml(repo.health_grade || '-')}</span>
            </div>
            <p class="teams-muted">Shared by ${escapeHtml(repo.owner || 'unknown')} &middot; ${escapeHtml(repo.status)}</p>
            <p class="teams-repo__issues">
                <strong>${escapeHtml(repo.total_issues)}</strong> open issues
                <span class="teams-muted">(${escapeHtml(counts.critical || 0)} critical, ${escapeHtml(counts.error || 0)} error,
                ${escapeHtml(counts.warning || 0)} warning)</span>
            </p>
            <div class="teams-inline">
                ${canUnshare ? `<button type="button" class="btn btn-secondary btn-sm" data-action="unshare"
                    data-id="${escapeHtml(repo.id)}" data-name="${escapeHtml(repo.name)}">Stop sharing</button>` : ''}
                ${mineToo ? `<button type="button" class="btn btn-secondary btn-sm" data-action="analyze"
                    data-id="${escapeHtml(repo.id)}">Analyze</button>` : ''}
            </div>
        </article>`;
    }).join('') : '<div class="teams-card teams-muted">Nothing is shared with this team yet.</div>';

    // What can still be shared: the user's own repositories that no team has
    state.myRepositories = mine.ok ? (mine.data.repositories || []) : [];
    const shareable = state.myRepositories.filter(repo => !repo.team_id);
    const select = $('share-repo-select');
    select.innerHTML = shareable.length
        ? shareable.map(repo => `<option value="${escapeHtml(repo.id)}">${escapeHtml(repo.name)}</option>`).join('')
        : '<option value="">No repository left to share</option>';
    select.disabled = !shareable.length || myRole() === 'viewer';
    $('share-repo-btn').disabled = select.disabled;
}

async function shareRepository() {
    const repositoryId = $('share-repo-select').value;
    if (!repositoryId) return;
    const result = await api('POST', `/api/teams/${state.team.id}/repositories`, { repository_id: repositoryId });
    if (!result.ok) return toast(reason(result, 'Could not share the repository'), true);
    toast('Repository shared');
    await refreshTeam();
    await Promise.all([loadRepositories(), loadOverview(), loadActivity()]);
}

async function unshareRepository(repositoryId, name) {
    if (!confirm(`Stop sharing "${name}" with this team?`)) return;
    const result = await api('DELETE', `/api/teams/${state.team.id}/repositories/${encodeURIComponent(repositoryId)}`);
    if (!result.ok) return toast(reason(result, 'Could not stop sharing the repository'), true);
    toast('Repository is no longer shared');
    await refreshTeam();
    await Promise.all([loadRepositories(), loadOverview(), loadActivity()]);
}

async function analyzeRepository(repositoryId) {
    const result = await api('POST', `/api/repositories/${encodeURIComponent(repositoryId)}/analyze`);
    toast(result.ok ? 'Analysis started' : reason(result, 'Could not start the analysis'), !result.ok);
}

// ------------------------------------------------------------------------------------------------ members

async function loadMembers() {
    const teamId = state.team.id;
    const result = await api('GET', `/api/teams/${teamId}/members`);
    if (!result.ok || teamId !== state.team.id) return;
    const members = result.data.members || [];
    $('member-count').textContent = members.length;

    const iAmOwner = myRole() === 'owner';
    const canManage = can('can_manage_members');
    $('members-body').innerHTML = members.map(member => {
        const isMe = state.me && member.user_id === state.me.id;
        // Only the owner changes or removes an admin; nobody changes the owner
        const roleEditable = canManage && member.role !== 'owner' && (iAmOwner || member.role !== 'admin') && !isMe;
        const roleCell = roleEditable
            ? `<select class="teams-select teams-select--small" data-member="${escapeHtml(member.user_id)}" aria-label="Role of ${escapeHtml(member.username)}">
                 ${(iAmOwner ? ROLES : ['member', 'viewer']).map(role =>
                    `<option value="${role}"${role === member.role ? ' selected' : ''}>${ROLE_LABELS[role]}</option>`).join('')}
               </select>`
            : `<span class="teams-badge teams-badge--role">${escapeHtml(ROLE_LABELS[member.role] || member.role)}</span>`;
        const removable = canManage && member.role !== 'owner' && (iAmOwner || member.role !== 'admin') && !isMe;
        return `
        <tr>
            <td><strong>${escapeHtml(member.username)}</strong>${isMe ? ' <span class="teams-muted">(you)</span>' : ''}</td>
            <td>${roleCell}</td>
            <td>${escapeHtml(formatDate(member.joined_at))}</td>
            <td>${removable ? `<button type="button" class="btn btn-secondary btn-sm" data-action="remove-member"
                data-user="${escapeHtml(member.user_id)}" data-name="${escapeHtml(member.username)}">Remove</button>` : ''}</td>
        </tr>`;
    }).join('');

    $('members-body').querySelectorAll('select[data-member]').forEach(select => {
        select.addEventListener('change', () => changeRole(select.dataset.member, select.value, select));
    });
}

async function changeRole(userId, role, select) {
    const result = await api('PUT', `/api/teams/${state.team.id}/members/${encodeURIComponent(userId)}/role`, { role });
    if (!result.ok) {
        toast(reason(result, 'Could not change the role'), true);
        return loadMembers();
    }
    toast('Role changed');
}

async function removeMember(userId, name) {
    if (!confirm(`Remove ${name} from the team?`)) return;
    const result = await api('DELETE', `/api/teams/${state.team.id}/members/${encodeURIComponent(userId)}`);
    if (!result.ok) return toast(reason(result, 'Could not remove the member'), true);
    toast(`${name} was removed`);
    await refreshTeam();
    await Promise.all([loadMembers(), loadLeaderboard()]);
}

async function sendInvitation(event) {
    event.preventDefault();
    const who = $('invite-who').value.trim();
    const body = { role: $('invite-role').value };
    if (who.includes('@')) body.email = who; else body.username = who;
    const result = await api('POST', `/api/teams/${state.team.id}/invitations`, body);
    if (!result.ok) return toast(reason(result, 'Could not send the invitation'), true);
    $('invite-who').value = '';
    toast('Invitation sent');
    await loadPending();
}

async function loadPending() {
    const teamId = state.team.id;
    const result = await api('GET', `/api/teams/${teamId}/invitations?status=pending`);
    if (!result.ok || teamId !== state.team.id) return;
    const invitations = result.data.invitations || [];
    $('pending-card').hidden = invitations.length === 0;
    $('pending-list').innerHTML = invitations.map(invitation => `
        <li class="teams-list__item">
            <div>
                <strong>${escapeHtml(invitation.username || invitation.email || 'Unknown')}</strong>
                <span class="teams-muted"> as ${escapeHtml(ROLE_LABELS[invitation.role] || invitation.role)},
                expires ${escapeHtml(formatDate(invitation.expires_at))}</span>
            </div>
            <button type="button" class="btn btn-secondary btn-sm" data-action="cancel-invitation"
                    data-id="${escapeHtml(invitation.id)}">Cancel</button>
        </li>`).join('');
}

async function cancelInvitation(invitationId) {
    const result = await api('DELETE', `/api/invitations/${encodeURIComponent(invitationId)}`);
    if (!result.ok) return toast(reason(result, 'Could not cancel the invitation'), true);
    toast('Invitation canceled');
    await loadPending();
}

// ------------------------------------------------------------------------------------ leaderboard, activity

async function loadLeaderboard() {
    const teamId = state.team.id;
    const result = await api('GET', `/api/teams/${teamId}/leaderboard`);
    if (teamId !== state.team.id) return;
    const rows = result.ok ? (result.data.leaderboard || []) : [];
    $('leaderboard-body').innerHTML = rows.length ? rows.map(row => `
        <tr>
            <td>${escapeHtml(row.rank)}</td>
            <td><strong>${escapeHtml(row.username)}</strong></td>
            <td>${escapeHtml(ROLE_LABELS[row.role] || row.role)}</td>
            <td>${escapeHtml(row.reviews_count)}</td>
            <td>${escapeHtml(row.issues_found)}</td>
            <td>${escapeHtml(row.contribution_score)}</td>
        </tr>`).join('') : '<tr><td colspan="6" class="teams-muted">No members yet</td></tr>';
}

async function loadActivity() {
    const teamId = state.team.id;
    const result = await api('GET', `/api/teams/${teamId}/activity?limit=30`);
    if (teamId !== state.team.id) return;
    const items = result.ok ? (result.data.activity || []) : [];
    $('activity-list').innerHTML = items.length ? items.map(item => `
        <li class="teams-list__item">
            <div>${escapeHtml(item.icon || '')} ${escapeHtml(item.text)}</div>
            <span class="teams-muted">${escapeHtml(formatDate(item.timestamp))}</span>
        </li>`).join('') : '<li class="teams-muted">No activity yet. Analyses and reviews of the shared repositories show up here.</li>';
}

// Not global names (app.js has its own `api`, `formatDate` ...); only this, for debugging
window.TeamsPage = { state };
})();
