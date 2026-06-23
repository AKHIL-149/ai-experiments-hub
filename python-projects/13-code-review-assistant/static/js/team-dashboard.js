/**
 * Team Dashboard JavaScript
 */

let currentTeam = null;
let charts = {};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadUserTeams();
    setupEventListeners();
});

function setupEventListeners() {
    document.getElementById('current-team').addEventListener('change', (e) => {
        const teamId = e.target.value;
        if (teamId) {
            loadTeamDashboard(teamId);
        } else {
            document.getElementById('team-content').style.display = 'none';
        }
    });

    document.getElementById('add-repo-btn')?.addEventListener('click', () => {
        window.location.href = '/repositories/new';
    });
}

async function loadUserTeams() {
    try {
        const response = await fetch('/api/teams');
        const data = await response.json();
        const teams = data.teams || [];

        const selector = document.getElementById('current-team');
        selector.innerHTML = '<option value="">Select a team...</option>';

        teams.forEach(team => {
            const option = document.createElement('option');
            option.value = team.id;
            option.textContent = team.name;
            selector.appendChild(option);
        });

        // Auto-select first team if only one
        if (teams.length === 1) {
            selector.value = teams[0].id;
            loadTeamDashboard(teams[0].id);
        }
    } catch (error) {
        console.error('Error loading teams:', error);
        showError('Failed to load teams');
    }
}

async function loadTeamDashboard(teamId) {
    currentTeam = teamId;
    document.getElementById('team-content').style.display = 'block';

    // Load all dashboard components in parallel
    await Promise.all([
        loadTeamOverview(teamId),
        loadSharedRepositories(teamId),
        loadTeamAnalytics(teamId),
        loadTeamLeaderboard(teamId),
        loadActivityFeed(teamId)
    ]);
}

async function loadTeamOverview(teamId) {
    try {
        const [teamResponse, analyticsResponse] = await Promise.all([
            fetch(`/api/teams/${teamId}`),
            fetch(`/api/teams/${teamId}/analytics`)
        ]);

        const team = await teamResponse.json();
        const analytics = await analyticsResponse.json();

        // Update overview stats
        document.getElementById('member-count').textContent = team.member_count || 0;
        document.getElementById('repo-count').textContent = team.repository_count || 0;
        document.getElementById('issue-count').textContent = analytics.total_issues || 0;
        document.getElementById('health-score').textContent =
            analytics.average_health_score ? analytics.average_health_score.toFixed(1) : 'N/A';
    } catch (error) {
        console.error('Error loading team overview:', error);
    }
}

async function loadSharedRepositories(teamId) {
    try {
        const response = await fetch(`/api/teams/${teamId}/repositories`);
        const data = await response.json();
        const repositories = data.repositories || [];

        const grid = document.getElementById('repositories-grid');

        if (repositories.length === 0) {
            grid.innerHTML = '<p class="empty-state">No shared repositories yet. Add one to get started!</p>';
            return;
        }

        grid.innerHTML = repositories.map(repo => `
            <div class="repo-card">
                <div class="repo-header">
                    <h3>${escapeHtml(repo.name)}</h3>
                    <span class="badge badge-${getStatusBadge(repo.status)}">${repo.status}</span>
                </div>
                <div class="repo-info">
                    <p><strong>Health Score:</strong> <span class="health-score ${getHealthClass(repo.health_score)}">${repo.health_score || 'N/A'}</span></p>
                    <p><strong>Open Issues:</strong> ${repo.issue_count || 0}</p>
                    <p><strong>Last Analysis:</strong> ${repo.last_analyzed_at ? formatDate(repo.last_analyzed_at) : 'Never'}</p>
                </div>
                <div class="repo-actions">
                    <a href="/repositories/${repo.id}" class="btn btn-sm">View Details</a>
                    <button onclick="analyzeRepository('${repo.id}')" class="btn btn-sm btn-primary">Analyze</button>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading repositories:', error);
    }
}

async function loadTeamAnalytics(teamId) {
    try {
        const response = await fetch(`/api/teams/${teamId}/analytics`);
        const analytics = await response.json();

        // Destroy existing charts
        Object.values(charts).forEach(chart => chart?.destroy());
        charts = {};

        // Issues by Severity
        if (analytics.issues_by_severity) {
            const ctx = document.getElementById('severity-chart').getContext('2d');
            charts.severity = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['Critical', 'Error', 'Warning', 'Info'],
                    datasets: [{
                        data: [
                            analytics.issues_by_severity.critical || 0,
                            analytics.issues_by_severity.error || 0,
                            analytics.issues_by_severity.warning || 0,
                            analytics.issues_by_severity.info || 0
                        ],
                        backgroundColor: ['#e83e8c', '#dc3545', '#ffc107', '#17a2b8']
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true
                }
            });
        }

        // Issues by Category
        if (analytics.issues_by_category) {
            const ctx = document.getElementById('category-chart').getContext('2d');
            const categories = Object.keys(analytics.issues_by_category);
            const counts = Object.values(analytics.issues_by_category);

            charts.category = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: categories,
                    datasets: [{
                        label: 'Issues',
                        data: counts,
                        backgroundColor: '#007bff'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {
                        legend: {
                            display: false
                        }
                    }
                }
            });
        }

        // Health Trend
        if (analytics.health_trend) {
            const ctx = document.getElementById('health-trend-chart').getContext('2d');
            charts.healthTrend = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: analytics.health_trend.dates || [],
                    datasets: [{
                        label: 'Average Health Score',
                        data: analytics.health_trend.scores || [],
                        borderColor: '#28a745',
                        backgroundColor: 'rgba(40, 167, 69, 0.1)',
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    scales: {
                        y: {
                            beginAtZero: true,
                            max: 100
                        }
                    }
                }
            });
        }

        // Activity Overview
        if (analytics.activity_summary) {
            const ctx = document.getElementById('activity-chart').getContext('2d');
            charts.activity = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: ['Analyses', 'PRs Reviewed', 'Issues Fixed', 'Refactorings'],
                    datasets: [{
                        data: [
                            analytics.activity_summary.analyses || 0,
                            analytics.activity_summary.prs_reviewed || 0,
                            analytics.activity_summary.issues_fixed || 0,
                            analytics.activity_summary.refactorings || 0
                        ],
                        backgroundColor: ['#007bff', '#28a745', '#ffc107', '#17a2b8']
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {
                        legend: {
                            display: false
                        }
                    }
                }
            });
        }
    } catch (error) {
        console.error('Error loading analytics:', error);
    }
}

async function loadTeamLeaderboard(teamId) {
    try {
        const response = await fetch(`/api/teams/${teamId}/leaderboard`);
        const data = await response.json();
        const members = data.members || [];

        const tbody = document.getElementById('leaderboard-body');

        if (members.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No activity yet</td></tr>';
            return;
        }

        tbody.innerHTML = members.map((member, index) => `
            <tr>
                <td>${index + 1}</td>
                <td>
                    <div class="member-info">
                        <strong>${escapeHtml(member.username)}</strong>
                    </div>
                </td>
                <td><span class="badge badge-role">${member.role}</span></td>
                <td>${member.prs_reviewed || 0}</td>
                <td>${member.issues_found || 0}</td>
                <td>${member.total_contributions || 0}</td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Error loading leaderboard:', error);
    }
}

async function loadActivityFeed(teamId) {
    try {
        const response = await fetch(`/api/teams/${teamId}/activity`);
        const data = await response.json();
        const activities = data.activities || [];

        const list = document.getElementById('activity-list');

        if (activities.length === 0) {
            list.innerHTML = '<p class="empty-state">No recent activity</p>';
            return;
        }

        list.innerHTML = activities.map(activity => `
            <div class="activity-item">
                <div class="activity-icon ${getActivityIconClass(activity.type)}">${getActivityIcon(activity.type)}</div>
                <div class="activity-content">
                    <div class="activity-text">
                        <strong>${escapeHtml(activity.user_name)}</strong> ${activity.description}
                    </div>
                    <div class="activity-meta">
                        ${formatDate(activity.created_at)} • ${activity.repository_name || ''}
                    </div>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading activity feed:', error);
    }
}

async function analyzeRepository(repoId) {
    try {
        const response = await fetch(`/api/repositories/${repoId}/analyze`, {
            method: 'POST'
        });

        if (response.ok) {
            showSuccess('Analysis started');
            setTimeout(() => loadSharedRepositories(currentTeam), 2000);
        } else {
            throw new Error('Analysis failed');
        }
    } catch (error) {
        showError('Failed to start analysis');
    }
}

function getStatusBadge(status) {
    const badges = {
        'ready': 'success',
        'pending': 'warning',
        'error': 'danger',
        'analyzing': 'primary'
    };
    return badges[status] || 'secondary';
}

function getHealthClass(score) {
    if (!score) return '';
    if (score >= 80) return 'health-good';
    if (score >= 60) return 'health-ok';
    return 'health-poor';
}

function getActivityIconClass(type) {
    const classes = {
        'analysis': 'activity-analysis',
        'pr_review': 'activity-pr',
        'issue': 'activity-issue',
        'member_join': 'activity-member'
    };
    return classes[type] || '';
}

function getActivityIcon(type) {
    const icons = {
        'analysis': '🔍',
        'pr_review': '✅',
        'issue': '⚠️',
        'member_join': '👤'
    };
    return icons[type] || '📝';
}

function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) return 'Today';
    if (days === 1) return 'Yesterday';
    if (days < 7) return `${days} days ago`;
    return date.toLocaleDateString();
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showSuccess(message) {
    alert(message);
}

function showError(message) {
    alert('Error: ' + message);
}
