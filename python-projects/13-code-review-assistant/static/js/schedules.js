/**
 * Schedule Management JavaScript
 */

let schedules = [];
let repositories = [];
let currentScheduleId = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadRepositories();
    loadSchedules();
    setupEventListeners();
});

function setupEventListeners() {
    // Create schedule button
    document.getElementById('create-schedule-btn').addEventListener('click', () => {
        currentScheduleId = null;
        openScheduleModal();
    });

    // Modal close
    document.querySelectorAll('.modal .close').forEach(el => {
        el.addEventListener('click', (e) => {
            e.target.closest('.modal').style.display = 'none';
        });
    });

    // Click outside modal
    window.addEventListener('click', (e) => {
        if (e.target.classList.contains('modal')) {
            e.target.style.display = 'none';
        }
    });

    // Schedule form
    document.getElementById('schedule-form').addEventListener('submit', handleScheduleSubmit);
    document.getElementById('cancel-btn').addEventListener('click', () => {
        document.getElementById('schedule-modal').style.display = 'none';
    });

    // Schedule type change
    document.getElementById('schedule-type').addEventListener('change', (e) => {
        const type = e.target.value;
        document.getElementById('interval-group').style.display = type === 'interval' ? 'block' : 'none';
        document.getElementById('cron-group').style.display = type === 'cron' ? 'block' : 'none';
    });

    // Analyze all files checkbox
    document.getElementById('analyze-all-files').addEventListener('change', (e) => {
        document.getElementById('patterns-group').style.display = e.target.checked ? 'none' : 'block';
    });

    // Filters
    document.getElementById('repository-filter').addEventListener('change', loadSchedules);
    document.getElementById('enabled-only-filter').addEventListener('change', loadSchedules);
}

async function loadRepositories() {
    try {
        const response = await fetch('/api/repositories');
        const data = await response.json();
        repositories = data.repositories || [];

        // Populate repository dropdowns
        const repositoryFilter = document.getElementById('repository-filter');
        const scheduleRepository = document.getElementById('schedule-repository');

        repositories.forEach(repo => {
            const option = new Option(repo.name, repo.id);
            repositoryFilter.add(option.cloneNode(true));
            scheduleRepository.add(option);
        });
    } catch (error) {
        console.error('Error loading repositories:', error);
        showError('Failed to load repositories');
    }
}

async function loadSchedules() {
    try {
        const repositoryId = document.getElementById('repository-filter').value;
        const enabledOnly = document.getElementById('enabled-only-filter').checked;

        let url = '/api/schedules?';
        if (repositoryId) url += `repository_id=${repositoryId}&`;
        if (enabledOnly) url += `enabled_only=true`;

        const response = await fetch(url);
        const data = await response.json();
        schedules = data.schedules || [];

        renderSchedules();
    } catch (error) {
        console.error('Error loading schedules:', error);
        showError('Failed to load schedules');
    }
}

function renderSchedules() {
    const container = document.getElementById('schedules-list');

    if (schedules.length === 0) {
        container.innerHTML = '<p class="empty-state">No schedules found. Create one to get started!</p>';
        return;
    }

    container.innerHTML = schedules.map(schedule => `
        <div class="schedule-card ${schedule.enabled ? '' : 'disabled'}">
            <div class="schedule-header">
                <h3>${escapeHtml(schedule.name)}</h3>
                <div class="schedule-status">
                    <span class="badge ${schedule.enabled ? 'badge-success' : 'badge-secondary'}">
                        ${schedule.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                </div>
            </div>

            <div class="schedule-info">
                <p><strong>Repository:</strong> ${escapeHtml(schedule.repository?.name || 'Unknown')}</p>
                <p><strong>Schedule:</strong> ${getScheduleDescription(schedule)}</p>
                <p><strong>Next Run:</strong> ${schedule.next_run_at ? formatDate(schedule.next_run_at) : 'N/A'}</p>
                <p><strong>Last Run:</strong> ${schedule.last_run_at ? formatDate(schedule.last_run_at) : 'Never'}</p>
                ${schedule.last_run ? `
                    <p><strong>Last Result:</strong>
                        <span class="${schedule.last_run.status === 'completed' ? 'text-success' : 'text-error'}">
                            ${schedule.last_run.issues_found || 0} issues found
                        </span>
                    </p>
                ` : ''}
                <p><strong>Total Runs:</strong> ${schedule.run_count || 0}</p>
            </div>

            <div class="schedule-actions">
                <button onclick="toggleSchedule('${schedule.id}', ${!schedule.enabled})" class="btn btn-sm">
                    ${schedule.enabled ? 'Disable' : 'Enable'}
                </button>
                <button onclick="triggerSchedule('${schedule.id}')" class="btn btn-sm btn-primary">
                    ▶ Trigger Now
                </button>
                <button onclick="viewRuns('${schedule.id}')" class="btn btn-sm">
                    View Runs
                </button>
                <button onclick="editSchedule('${schedule.id}')" class="btn btn-sm">
                    Edit
                </button>
                <button onclick="deleteSchedule('${schedule.id}')" class="btn btn-sm btn-danger">
                    Delete
                </button>
            </div>
        </div>
    `).join('');
}

function getScheduleDescription(schedule) {
    switch (schedule.schedule_type) {
        case 'daily':
            return 'Daily at midnight UTC';
        case 'weekly':
            return 'Weekly on Sunday at midnight UTC';
        case 'interval':
            return `Every ${schedule.interval_minutes} minutes`;
        case 'cron':
            return `Cron: ${schedule.cron_expression}`;
        default:
            return schedule.schedule_type;
    }
}

function openScheduleModal() {
    const modal = document.getElementById('schedule-modal');
    const form = document.getElementById('schedule-form');

    // Reset form
    form.reset();
    document.getElementById('modal-title').textContent = currentScheduleId ? 'Edit Schedule' : 'Create Schedule';

    if (currentScheduleId) {
        // Load schedule data
        const schedule = schedules.find(s => s.id === currentScheduleId);
        if (schedule) {
            document.getElementById('schedule-name').value = schedule.name;
            document.getElementById('schedule-repository').value = schedule.repository_id;
            document.getElementById('schedule-description').value = schedule.description || '';
            document.getElementById('schedule-type').value = schedule.schedule_type;
            document.getElementById('schedule-interval').value = schedule.interval_minutes || '';
            document.getElementById('schedule-cron').value = schedule.cron_expression || '';
            document.getElementById('analyze-all-files').checked = schedule.analyze_all_files;
            document.getElementById('file-patterns').value = (schedule.file_patterns || []).join('\n');
            document.getElementById('severity-threshold').value = schedule.severity_threshold;
            document.getElementById('notify-on-completion').checked = schedule.notify_on_completion;
            document.getElementById('notify-on-issues').checked = schedule.notify_on_issues;
            document.getElementById('notification-emails').value = (schedule.notification_emails || []).join('\n');
            document.getElementById('slack-webhook').value = schedule.slack_webhook_url || '';

            // Trigger type change to show/hide fields
            document.getElementById('schedule-type').dispatchEvent(new Event('change'));
            document.getElementById('analyze-all-files').dispatchEvent(new Event('change'));
        }
    }

    modal.style.display = 'block';
}

async function handleScheduleSubmit(e) {
    e.preventDefault();

    const formData = {
        name: document.getElementById('schedule-name').value,
        repository_id: document.getElementById('schedule-repository').value,
        description: document.getElementById('schedule-description').value,
        schedule_type: document.getElementById('schedule-type').value,
        analyze_all_files: document.getElementById('analyze-all-files').checked,
        severity_threshold: document.getElementById('severity-threshold').value,
        notify_on_completion: document.getElementById('notify-on-completion').checked,
        notify_on_issues: document.getElementById('notify-on-issues').checked
    };

    // Add type-specific fields
    if (formData.schedule_type === 'interval') {
        formData.interval_minutes = parseInt(document.getElementById('schedule-interval').value);
    } else if (formData.schedule_type === 'cron') {
        formData.cron_expression = document.getElementById('schedule-cron').value;
    }

    // Parse multi-line fields
    const patternsText = document.getElementById('file-patterns').value.trim();
    if (patternsText && !formData.analyze_all_files) {
        formData.file_patterns = patternsText.split('\n').filter(p => p.trim());
    }

    const emailsText = document.getElementById('notification-emails').value.trim();
    if (emailsText) {
        formData.notification_emails = emailsText.split('\n').filter(e => e.trim());
    }

    const slackWebhook = document.getElementById('slack-webhook').value.trim();
    if (slackWebhook) {
        formData.slack_webhook_url = slackWebhook;
    }

    try {
        const url = currentScheduleId ? `/api/schedules/${currentScheduleId}` : '/api/schedules';
        const method = currentScheduleId ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to save schedule');
        }

        showSuccess(currentScheduleId ? 'Schedule updated successfully' : 'Schedule created successfully');
        document.getElementById('schedule-modal').style.display = 'none';
        loadSchedules();
    } catch (error) {
        console.error('Error saving schedule:', error);
        showError(error.message);
    }
}

async function editSchedule(scheduleId) {
    currentScheduleId = scheduleId;
    openScheduleModal();
}

async function toggleSchedule(scheduleId, enabled) {
    try {
        const response = await fetch(`/api/schedules/${scheduleId}/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled })
        });

        if (!response.ok) {
            throw new Error('Failed to toggle schedule');
        }

        showSuccess(`Schedule ${enabled ? 'enabled' : 'disabled'} successfully`);
        loadSchedules();
    } catch (error) {
        console.error('Error toggling schedule:', error);
        showError(error.message);
    }
}

async function triggerSchedule(scheduleId) {
    if (!confirm('Are you sure you want to trigger this schedule now?')) {
        return;
    }

    try {
        const response = await fetch(`/api/schedules/${scheduleId}/trigger`, {
            method: 'POST'
        });

        if (!response.ok) {
            throw new Error('Failed to trigger schedule');
        }

        showSuccess('Schedule triggered successfully. Check the runs section for progress.');
        setTimeout(loadSchedules, 2000);
    } catch (error) {
        console.error('Error triggering schedule:', error);
        showError(error.message);
    }
}

async function deleteSchedule(scheduleId) {
    if (!confirm('Are you sure you want to delete this schedule? This action cannot be undone.')) {
        return;
    }

    try {
        const response = await fetch(`/api/schedules/${scheduleId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            throw new Error('Failed to delete schedule');
        }

        showSuccess('Schedule deleted successfully');
        loadSchedules();
    } catch (error) {
        console.error('Error deleting schedule:', error);
        showError(error.message);
    }
}

async function viewRuns(scheduleId) {
    try {
        const response = await fetch(`/api/schedules/${scheduleId}/runs`);
        const data = await response.json();
        const runs = data.runs || [];

        const runsContainer = document.getElementById('runs-list');
        if (runs.length === 0) {
            runsContainer.innerHTML = '<p class="empty-state">No runs found for this schedule.</p>';
        } else {
            runsContainer.innerHTML = runs.map(run => `
                <div class="run-card">
                    <div class="run-header">
                        <span class="badge badge-${getStatusColor(run.status)}">${run.status}</span>
                        <span>${formatDate(run.created_at)}</span>
                    </div>
                    <div class="run-info">
                        ${run.status === 'completed' ? `
                            <p><strong>Files Analyzed:</strong> ${run.files_analyzed}</p>
                            <p><strong>Issues Found:</strong> ${run.issues_found}</p>
                            <p><strong>Duration:</strong> ${run.duration_seconds?.toFixed(2)}s</p>
                        ` : run.status === 'failed' ? `
                            <p><strong>Error:</strong> ${escapeHtml(run.error_message)}</p>
                        ` : ''}
                    </div>
                    <button onclick="viewRunDetails('${run.id}')" class="btn btn-sm">View Details</button>
                </div>
            `).join('');
        }

        // Scroll to runs section
        document.getElementById('runs-section').scrollIntoView({ behavior: 'smooth' });
    } catch (error) {
        console.error('Error loading runs:', error);
        showError('Failed to load runs');
    }
}

async function viewRunDetails(runId) {
    try {
        const response = await fetch(`/api/runs/${runId}`);
        const run = await response.json();

        const detailsHtml = `
            <div class="run-details">
                <div class="detail-row">
                    <strong>Status:</strong>
                    <span class="badge badge-${getStatusColor(run.status)}">${run.status}</span>
                </div>
                <div class="detail-row">
                    <strong>Created:</strong> ${formatDate(run.created_at)}
                </div>
                ${run.started_at ? `
                    <div class="detail-row">
                        <strong>Started:</strong> ${formatDate(run.started_at)}
                    </div>
                ` : ''}
                ${run.completed_at ? `
                    <div class="detail-row">
                        <strong>Completed:</strong> ${formatDate(run.completed_at)}
                    </div>
                    <div class="detail-row">
                        <strong>Duration:</strong> ${run.duration_seconds?.toFixed(2)}s
                    </div>
                ` : ''}
                ${run.status === 'completed' ? `
                    <hr>
                    <h4>Results</h4>
                    <div class="detail-row">
                        <strong>Files Analyzed:</strong> ${run.files_analyzed}
                    </div>
                    <div class="detail-row">
                        <strong>Total Issues:</strong> ${run.issues_found}
                    </div>
                    <div class="detail-row">
                        <strong>Critical:</strong> <span class="text-critical">${run.critical_issues}</span>
                    </div>
                    <div class="detail-row">
                        <strong>Error:</strong> <span class="text-error">${run.error_issues}</span>
                    </div>
                    <div class="detail-row">
                        <strong>Warning:</strong> <span class="text-warning">${run.warning_issues}</span>
                    </div>
                    <div class="detail-row">
                        <strong>Info:</strong> ${run.info_issues}
                    </div>
                ` : ''}
                ${run.error_message ? `
                    <hr>
                    <h4>Error</h4>
                    <pre>${escapeHtml(run.error_message)}</pre>
                ` : ''}
            </div>
        `;

        document.getElementById('run-details').innerHTML = detailsHtml;
        document.getElementById('run-modal').style.display = 'block';
    } catch (error) {
        console.error('Error loading run details:', error);
        showError('Failed to load run details');
    }
}

function getStatusColor(status) {
    const colors = {
        'pending': 'secondary',
        'running': 'primary',
        'completed': 'success',
        'failed': 'danger',
        'cancelled': 'secondary'
    };
    return colors[status] || 'secondary';
}

function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showSuccess(message) {
    alert(message); // Simple alert for now, can be replaced with toast notification
}

function showError(message) {
    alert('Error: ' + message);
}
