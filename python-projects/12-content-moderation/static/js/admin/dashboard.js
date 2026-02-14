/**
 * Admin Dashboard JavaScript
 * Handles admin functionality: review queue, appeals, policies, analytics
 */

// State
let currentUser = null;
let currentView = 'overview';
let reviewQueue = [];
let currentPage = 1;
let totalPages = 1;
const pageSize = 50;
let currentFilters = {
    status: '',
    priority: null
};
let selectedContentId = null;
let selectedAppealId = null;
let selectedPolicyId = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initializeAuth();
    setupEventListeners();
    loadDashboardStats();
});

// Authentication
async function initializeAuth() {
    try {
        const response = await fetch('/api/auth/me', {
            credentials: 'include'
        });

        if (!response.ok) {
            window.location.href = '/';
            return;
        }

        currentUser = await response.json();

        // Check if user is moderator or admin
        if (currentUser.role !== 'moderator' && currentUser.role !== 'admin') {
            alert('Access denied. Moderator or admin role required.');
            window.location.href = '/';
            return;
        }

        // Update UI
        document.getElementById('current-username').textContent = currentUser.username;
        document.getElementById('user-role').textContent = currentUser.role.toUpperCase();
        document.getElementById('user-role').className = `role-badge role-${currentUser.role}`;

        // Hide admin-only sections if not admin
        if (currentUser.role !== 'admin') {
            document.querySelectorAll('.admin-only').forEach(el => {
                el.style.display = 'none';
            });
        }

    } catch (error) {
        console.error('Auth error:', error);
        window.location.href = '/';
    }
}

// Event Listeners
function setupEventListeners() {
    // Navigation
    document.querySelectorAll('.nav-item').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const view = e.target.dataset.view;
            switchView(view);
        });
    });

    // Logout
    document.getElementById('logout-btn').addEventListener('click', logout);

    // Back to app
    document.getElementById('back-to-app').addEventListener('click', () => {
        window.location.href = '/';
    });

    // Overview actions
    document.getElementById('refresh-stats')?.addEventListener('click', loadDashboardStats);
    document.getElementById('view-queue')?.addEventListener('click', () => switchView('review'));

    // Queue filters
    document.getElementById('apply-filters')?.addEventListener('click', applyFilters);
    document.getElementById('clear-filters')?.addEventListener('click', clearFilters);

    // Pagination
    document.getElementById('prev-page')?.addEventListener('click', () => changePage(currentPage - 1));
    document.getElementById('next-page')?.addEventListener('click', () => changePage(currentPage + 1));

    // Policy actions
    document.getElementById('create-policy-btn')?.addEventListener('click', openCreatePolicyModal);

    // Modal close buttons
    document.querySelectorAll('.modal-close').forEach(btn => {
        btn.addEventListener('click', closeAllModals);
    });

    // Review form
    document.querySelectorAll('input[name="review-decision"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            const categoryGroup = document.getElementById('category-group');
            if (e.target.value === 'reject') {
                categoryGroup.style.display = 'block';
            } else {
                categoryGroup.style.display = 'none';
            }
        });
    });

    // Submit review
    document.getElementById('submit-review')?.addEventListener('click', submitReview);

    // Submit appeal review
    document.getElementById('submit-appeal-review')?.addEventListener('click', submitAppealReview);

    // Save policy
    document.getElementById('save-policy')?.addEventListener('click', savePolicy);
}

// View Switching
function switchView(view) {
    currentView = view;

    // Update nav
    document.querySelectorAll('.nav-item').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.view === view) {
            btn.classList.add('active');
        }
    });

    // Hide all views
    document.querySelectorAll('.content-view').forEach(v => {
        v.style.display = 'none';
    });

    // Show selected view
    const viewElement = document.getElementById(`${view}-view`);
    if (viewElement) {
        viewElement.style.display = 'block';
    }

    // Load view data
    switch (view) {
        case 'overview':
            loadDashboardStats();
            break;
        case 'review':
            loadReviewQueue();
            break;
        case 'appeals':
            loadAppeals();
            break;
        case 'policies':
            loadPolicies();
            break;
        case 'analytics':
            // Analytics view placeholder
            break;
    }
}

// Dashboard Stats
async function loadDashboardStats() {
    try {
        const response = await fetch('/api/admin/stats', {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('Failed to load stats');
        }

        const data = await response.json();
        const stats = data.stats;

        // Update content stats
        document.getElementById('stat-total').textContent = stats.content.total || 0;
        document.getElementById('stat-pending').textContent = stats.content.pending || 0;
        document.getElementById('stat-flagged').textContent = stats.content.flagged || 0;
        document.getElementById('stat-approved').textContent = stats.content.approved || 0;
        document.getElementById('stat-rejected').textContent = stats.content.rejected || 0;

        // Update review stats
        document.getElementById('stat-reviews-total').textContent = stats.reviews.total || 0;
        document.getElementById('stat-reviews-manual').textContent = stats.reviews.manual || 0;
        document.getElementById('stat-appeals-pending').textContent = stats.reviews.appeals_pending || 0;
        document.getElementById('stat-appeals-resolved').textContent = stats.reviews.appeals_resolved || 0;

        // Update user stats
        document.getElementById('stat-users-total').textContent = stats.users.total || 0;
        document.getElementById('stat-users-active').textContent = stats.users.active || 0;
        document.getElementById('stat-users-moderators').textContent = stats.users.moderators || 0;

        // Update policy stats
        document.getElementById('stat-policies-total').textContent = stats.policies.total || 0;
        document.getElementById('stat-policies-enabled').textContent = stats.policies.enabled || 0;

    } catch (error) {
        console.error('Error loading stats:', error);
        showError('Failed to load dashboard statistics');
    }
}

// Review Queue
async function loadReviewQueue() {
    try {
        const params = new URLSearchParams({
            limit: pageSize,
            offset: (currentPage - 1) * pageSize
        });

        if (currentFilters.status) {
            params.append('status', currentFilters.status);
        }
        if (currentFilters.priority !== null) {
            params.append('priority', currentFilters.priority);
        }

        const response = await fetch(`/api/moderation/queue?${params}`, {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('Failed to load queue');
        }

        const data = await response.json();
        reviewQueue = data.queue || [];
        const total = data.total || 0;
        totalPages = Math.ceil(total / pageSize);

        renderReviewQueue();
        updatePagination();

    } catch (error) {
        console.error('Error loading queue:', error);
        showError('Failed to load review queue');
    }
}

function renderReviewQueue() {
    const container = document.getElementById('queue-container');

    if (reviewQueue.length === 0) {
        container.innerHTML = '<p class="loading">No items in review queue</p>';
        return;
    }

    container.innerHTML = reviewQueue.map(item => {
        const priorityClass = item.priority >= 10 ? 'priority-critical' : item.priority >= 5 ? 'priority-high' : '';
        const classifications = item.classifications || [];
        const latestClassification = classifications[classifications.length - 1];

        let preview = '';
        if (item.content_type === 'text') {
            preview = `<div class="content-text">${escapeHtml(item.text_content || '')}</div>`;
        } else if (item.content_type === 'image') {
            preview = `<img src="${item.file_path}" alt="Content image">`;
        } else if (item.content_type === 'video') {
            preview = `<div class="content-text">Video content</div>`;
        }

        return `
            <div class="queue-item">
                <div class="queue-item-preview">
                    <h4>${item.content_type.toUpperCase()} - ${item.id.substring(0, 8)}</h4>
                    ${preview}
                    <div class="queue-item-meta">
                        <span class="meta-badge">Status: ${item.status}</span>
                        <span class="meta-badge ${priorityClass}">Priority: ${item.priority}</span>
                        <span class="meta-badge">User: ${item.user_id.substring(0, 8)}</span>
                        ${latestClassification ? `
                            <span class="meta-badge">
                                ${latestClassification.category}: ${(latestClassification.confidence * 100).toFixed(1)}%
                            </span>
                        ` : ''}
                    </div>
                </div>
                <div class="queue-item-actions">
                    <button class="btn-primary" onclick="openReviewModal('${item.id}')">
                        Review
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function applyFilters() {
    currentFilters.status = document.getElementById('filter-status').value;
    const priorityValue = document.getElementById('filter-priority').value;
    currentFilters.priority = priorityValue ? parseInt(priorityValue) : null;
    currentPage = 1;
    loadReviewQueue();
}

function clearFilters() {
    document.getElementById('filter-status').value = '';
    document.getElementById('filter-priority').value = '';
    currentFilters = { status: '', priority: null };
    currentPage = 1;
    loadReviewQueue();
}

function updatePagination() {
    document.getElementById('page-info').textContent = `Page ${currentPage} of ${totalPages || 1}`;
    document.getElementById('prev-page').disabled = currentPage === 1;
    document.getElementById('next-page').disabled = currentPage >= totalPages;
}

function changePage(page) {
    if (page < 1 || page > totalPages) return;
    currentPage = page;
    loadReviewQueue();
}

// Review Modal
async function openReviewModal(contentId) {
    try {
        const response = await fetch(`/api/content/${contentId}`, {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('Failed to load content');
        }

        const content = await response.json();
        selectedContentId = contentId;

        // Render content
        const display = document.getElementById('review-content-display');
        let contentHtml = '';

        if (content.content_type === 'text') {
            contentHtml = `<div class="content-text"><strong>Text:</strong><br>${escapeHtml(content.text_content || '')}</div>`;
        } else if (content.content_type === 'image') {
            contentHtml = `<img src="${content.file_path}" alt="Content" style="max-width: 100%; border-radius: 4px;">`;
        } else if (content.content_type === 'video') {
            contentHtml = `<video src="${content.file_path}" controls style="max-width: 100%; border-radius: 4px;"></video>`;
        }

        display.innerHTML = contentHtml;

        // Render classifications
        const classResults = document.getElementById('classification-results');
        if (content.classifications && content.classifications.length > 0) {
            classResults.innerHTML = content.classifications.map(c => {
                const confidence = (c.confidence * 100).toFixed(1);
                const confClass = c.confidence > 0.8 ? 'high' : c.confidence > 0.5 ? 'medium' : 'low';
                return `
                    <div class="classification-result">
                        <span class="classification-category">${c.category}</span>
                        <div class="classification-confidence">
                            <div class="confidence-bar">
                                <div class="confidence-fill ${confClass}" style="width: ${confidence}%"></div>
                            </div>
                            <span>${confidence}%</span>
                        </div>
                    </div>
                `;
            }).join('');
        } else {
            classResults.innerHTML = '<p>No classifications available</p>';
        }

        // Reset form
        document.querySelector('input[name="review-decision"][value="approve"]').checked = true;
        document.getElementById('category-group').style.display = 'none';
        document.getElementById('review-notes').value = '';

        // Show modal
        document.getElementById('review-modal').style.display = 'flex';

    } catch (error) {
        console.error('Error opening review modal:', error);
        showError('Failed to load content for review');
    }
}

async function submitReview() {
    const decision = document.querySelector('input[name="review-decision"]:checked').value;
    const approved = decision === 'approve';
    const category = approved ? null : document.getElementById('violation-category').value;
    const notes = document.getElementById('review-notes').value;

    try {
        const response = await fetch('/api/moderation/review', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                content_id: selectedContentId,
                approved,
                category,
                notes
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to submit review');
        }

        showSuccess(`Content ${approved ? 'approved' : 'rejected'} successfully`);
        closeAllModals();
        loadReviewQueue();

    } catch (error) {
        console.error('Error submitting review:', error);
        showError(error.message);
    }
}

// Appeals
async function loadAppeals() {
    try {
        const response = await fetch('/api/appeals', {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('Failed to load appeals');
        }

        const data = await response.json();
        const appeals = data.appeals || [];

        renderAppeals(appeals);

    } catch (error) {
        console.error('Error loading appeals:', error);
        showError('Failed to load appeals');
    }
}

function renderAppeals(appeals) {
    const container = document.getElementById('appeals-container');

    if (appeals.length === 0) {
        container.innerHTML = '<p class="loading">No appeals pending</p>';
        return;
    }

    container.innerHTML = appeals.map(appeal => {
        const isPending = !appeal.moderator_id;
        const statusClass = isPending ? 'pending' : 'resolved';

        return `
            <div class="appeal-item ${statusClass}">
                <div class="appeal-header">
                    <h4>Appeal #${appeal.id.substring(0, 8)}</h4>
                    <span class="policy-badge ${statusClass}">${isPending ? 'Pending' : 'Resolved'}</span>
                </div>
                <div class="appeal-meta">
                    <p><strong>Content ID:</strong> ${appeal.content_id}</p>
                    <p><strong>Submitted:</strong> ${new Date(appeal.created_at).toLocaleString()}</p>
                </div>
                <div class="appeal-reason">
                    <strong>Reason:</strong><br>
                    ${escapeHtml(appeal.notes || '')}
                </div>
                ${isPending ? `
                    <div class="appeal-actions">
                        <button class="btn-primary" onclick="openAppealModal('${appeal.id}')">
                            Review Appeal
                        </button>
                    </div>
                ` : `
                    <div class="appeal-resolution">
                        <p><strong>Resolution:</strong> ${appeal.approved ? 'Approved' : 'Rejected'}</p>
                        <p><strong>Moderator:</strong> ${appeal.moderator_id}</p>
                    </div>
                `}
            </div>
        `;
    }).join('');
}

async function openAppealModal(appealId) {
    try {
        // Find appeal
        const response = await fetch('/api/appeals', {
            credentials: 'include'
        });

        const data = await response.json();
        const appeal = data.appeals.find(a => a.id === appealId);

        if (!appeal) {
            throw new Error('Appeal not found');
        }

        selectedAppealId = appealId;

        // Render appeal info
        const display = document.getElementById('appeal-content-display');
        display.innerHTML = `
            <div>
                <h4>Appeal Information</h4>
                <p><strong>Content ID:</strong> ${appeal.content_id}</p>
                <p><strong>Submitted:</strong> ${new Date(appeal.created_at).toLocaleString()}</p>
                <div class="appeal-reason">
                    <strong>User's Reason:</strong><br>
                    ${escapeHtml(appeal.notes || '')}
                </div>
            </div>
        `;

        // Reset form
        document.querySelector('input[name="appeal-decision"][value="approve"]').checked = true;
        document.getElementById('appeal-response').value = '';

        // Show modal
        document.getElementById('appeal-modal').style.display = 'flex';

    } catch (error) {
        console.error('Error opening appeal modal:', error);
        showError('Failed to load appeal');
    }
}

async function submitAppealReview() {
    const decision = document.querySelector('input[name="appeal-decision"]:checked').value;
    const approved = decision === 'approve';
    const notes = document.getElementById('appeal-response').value;

    try {
        const response = await fetch(`/api/appeals/${selectedAppealId}/review`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ approved, notes })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to submit appeal review');
        }

        showSuccess(`Appeal ${approved ? 'approved' : 'rejected'} successfully`);
        closeAllModals();
        loadAppeals();

    } catch (error) {
        console.error('Error submitting appeal review:', error);
        showError(error.message);
    }
}

// Policies
async function loadPolicies() {
    try {
        const response = await fetch('/api/admin/policies', {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('Failed to load policies');
        }

        const data = await response.json();
        const policies = data.policies || [];

        renderPolicies(policies);

    } catch (error) {
        console.error('Error loading policies:', error);
        showError('Failed to load policies');
    }
}

function renderPolicies(policies) {
    const container = document.getElementById('policies-container');

    if (policies.length === 0) {
        container.innerHTML = '<p class="loading">No policies configured</p>';
        return;
    }

    container.innerHTML = policies.map(policy => {
        const statusClass = policy.enabled ? 'enabled' : 'disabled';

        return `
            <div class="policy-item ${statusClass}">
                <div class="policy-header">
                    <h4>${policy.name}</h4>
                    <span class="policy-badge ${statusClass}">${statusClass}</span>
                </div>
                <div class="policy-details">
                    <div class="policy-detail-item">
                        <label>Category</label>
                        <span>${policy.category}</span>
                    </div>
                    <div class="policy-detail-item">
                        <label>Auto-Reject Threshold</label>
                        <span>${(policy.auto_reject_threshold * 100).toFixed(0)}%</span>
                    </div>
                    <div class="policy-detail-item">
                        <label>Flag Threshold</label>
                        <span>${(policy.flag_review_threshold * 100).toFixed(0)}%</span>
                    </div>
                    <div class="policy-detail-item">
                        <label>Severity</label>
                        <span>${policy.severity}/10</span>
                    </div>
                </div>
                ${currentUser && currentUser.role === 'admin' ? `
                    <div class="policy-actions">
                        <button class="btn-secondary" onclick="openEditPolicyModal('${policy.id}')">
                            Edit
                        </button>
                        <button class="btn-secondary" onclick="togglePolicy('${policy.id}', ${!policy.enabled})">
                            ${policy.enabled ? 'Disable' : 'Enable'}
                        </button>
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
}

function openCreatePolicyModal() {
    selectedPolicyId = null;
    document.getElementById('policy-modal-title').textContent = 'Create Policy';
    document.getElementById('policy-name').disabled = false;
    document.getElementById('policy-category').disabled = false;
    document.getElementById('policy-form').reset();
    document.getElementById('policy-modal').style.display = 'flex';
}

async function openEditPolicyModal(policyId) {
    selectedPolicyId = policyId;

    try {
        const response = await fetch('/api/admin/policies', {
            credentials: 'include'
        });

        const data = await response.json();
        const policy = data.policies.find(p => p.id === policyId);

        if (!policy) {
            throw new Error('Policy not found');
        }

        document.getElementById('policy-modal-title').textContent = 'Edit Policy';
        document.getElementById('policy-name').value = policy.name;
        document.getElementById('policy-name').disabled = true;
        document.getElementById('policy-category').value = policy.category;
        document.getElementById('policy-category').disabled = true;
        document.getElementById('policy-auto-reject').value = policy.auto_reject_threshold;
        document.getElementById('policy-flag-threshold').value = policy.flag_review_threshold;
        document.getElementById('policy-severity').value = policy.severity;
        document.getElementById('policy-enabled').checked = policy.enabled;

        document.getElementById('policy-modal').style.display = 'flex';

    } catch (error) {
        console.error('Error loading policy:', error);
        showError('Failed to load policy');
    }
}

async function savePolicy() {
    const isEdit = selectedPolicyId !== null;
    const url = isEdit ? `/api/admin/policies/${selectedPolicyId}` : '/api/admin/policies';
    const method = isEdit ? 'PATCH' : 'POST';

    const data = {
        auto_reject_threshold: parseFloat(document.getElementById('policy-auto-reject').value),
        flag_review_threshold: parseFloat(document.getElementById('policy-flag-threshold').value),
        severity: parseInt(document.getElementById('policy-severity').value),
        enabled: document.getElementById('policy-enabled').checked
    };

    if (!isEdit) {
        data.name = document.getElementById('policy-name').value;
        data.category = document.getElementById('policy-category').value;
    }

    try {
        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to save policy');
        }

        showSuccess(`Policy ${isEdit ? 'updated' : 'created'} successfully`);
        closeAllModals();
        loadPolicies();

    } catch (error) {
        console.error('Error saving policy:', error);
        showError(error.message);
    }
}

async function togglePolicy(policyId, enabled) {
    try {
        const response = await fetch(`/api/admin/policies/${policyId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ enabled })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to update policy');
        }

        showSuccess(`Policy ${enabled ? 'enabled' : 'disabled'} successfully`);
        loadPolicies();

    } catch (error) {
        console.error('Error toggling policy:', error);
        showError(error.message);
    }
}

// Utility Functions
function closeAllModals() {
    document.querySelectorAll('.modal').forEach(modal => {
        modal.style.display = 'none';
    });
}

async function logout() {
    try {
        await fetch('/api/auth/logout', {
            method: 'POST',
            credentials: 'include'
        });
        window.location.href = '/';
    } catch (error) {
        console.error('Logout error:', error);
        window.location.href = '/';
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showSuccess(message) {
    alert(message); // TODO: Replace with better notification system
}

function showError(message) {
    alert('Error: ' + message); // TODO: Replace with better notification system
}
