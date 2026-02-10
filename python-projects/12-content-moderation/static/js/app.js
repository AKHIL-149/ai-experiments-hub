/**
 * Content Moderation System - Client Application
 */

class ContentModerationApp {
    constructor() {
        this.currentUser = null;
        this.currentView = 'submit';
        this.init();
    }

    async init() {
        // Check if user is already logged in
        await this.checkAuth();

        // Setup event listeners
        this.setupAuthListeners();
        this.setupNavigationListeners();
        this.setupSubmitListeners();
        this.setupModalListeners();
    }

    // Authentication

    async checkAuth() {
        try {
            const response = await fetch('/api/auth/me', {
                credentials: 'include'
            });

            if (response.ok) {
                this.currentUser = await response.json();
                this.showAppView();
                this.updateUserInfo();
                await this.loadView(this.currentView);
            } else {
                this.showAuthView();
            }
        } catch (error) {
            console.error('Auth check failed:', error);
            this.showAuthView();
        }
    }

    setupAuthListeners() {
        // Show register form
        document.getElementById('show-register').addEventListener('click', (e) => {
            e.preventDefault();
            document.getElementById('login-form').style.display = 'none';
            document.getElementById('register-form').style.display = 'block';
            this.clearError('login-error');
        });

        // Show login form
        document.getElementById('show-login').addEventListener('click', (e) => {
            e.preventDefault();
            document.getElementById('register-form').style.display = 'none';
            document.getElementById('login-form').style.display = 'block';
            this.clearError('register-error');
        });

        // Login
        document.getElementById('login-submit').addEventListener('click', () => this.login());
        document.getElementById('login-password').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.login();
        });

        // Register
        document.getElementById('register-submit').addEventListener('click', () => this.register());
        document.getElementById('register-password').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.register();
        });

        // Logout
        document.getElementById('logout-btn').addEventListener('click', () => this.logout());
    }

    async login() {
        const username = document.getElementById('login-username').value.trim();
        const password = document.getElementById('login-password').value;

        if (!username || !password) {
            this.showError('login-error', 'Please enter username and password');
            return;
        }

        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ username, password })
            });

            const data = await response.json();

            if (response.ok) {
                this.currentUser = data.user;
                this.showAppView();
                this.updateUserInfo();
                await this.loadView('submit');
            } else {
                this.showError('login-error', data.detail || 'Login failed');
            }
        } catch (error) {
            this.showError('login-error', 'Network error. Please try again.');
        }
    }

    async register() {
        const username = document.getElementById('register-username').value.trim();
        const email = document.getElementById('register-email').value.trim();
        const password = document.getElementById('register-password').value;

        if (!username || !email || !password) {
            this.showError('register-error', 'Please fill in all fields');
            return;
        }

        try {
            const response = await fetch('/api/auth/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ username, email, password })
            });

            const data = await response.json();

            if (response.ok) {
                this.currentUser = data.user;
                this.showAppView();
                this.updateUserInfo();
                await this.loadView('submit');
            } else {
                this.showError('register-error', data.detail || 'Registration failed');
            }
        } catch (error) {
            this.showError('register-error', 'Network error. Please try again.');
        }
    }

    async logout() {
        try {
            await fetch('/api/auth/logout', {
                method: 'POST',
                credentials: 'include'
            });
        } catch (error) {
            console.error('Logout error:', error);
        }

        this.currentUser = null;
        this.showAuthView();
    }

    // View Management

    showAuthView() {
        document.getElementById('auth-view').style.display = 'flex';
        document.getElementById('app-view').style.display = 'none';
        document.getElementById('login-form').style.display = 'block';
        document.getElementById('register-form').style.display = 'none';
        this.clearError('login-error');
        this.clearError('register-error');
    }

    showAppView() {
        document.getElementById('auth-view').style.display = 'none';
        document.getElementById('app-view').style.display = 'flex';
    }

    updateUserInfo() {
        document.getElementById('current-username').textContent = this.currentUser.username;

        const roleBadge = document.getElementById('user-role');
        roleBadge.textContent = this.currentUser.role;
        roleBadge.className = `role-badge ${this.currentUser.role}`;

        // Show/hide role-specific navigation
        if (this.currentUser.role === 'admin' || this.currentUser.role === 'moderator') {
            document.querySelectorAll('.moderator-only').forEach(el => {
                el.style.display = 'block';
            });
        }

        if (this.currentUser.role === 'admin') {
            document.querySelectorAll('.admin-only').forEach(el => {
                el.style.display = 'block';
            });
        }
    }

    setupNavigationListeners() {
        document.querySelectorAll('.nav-item').forEach(btn => {
            btn.addEventListener('click', async () => {
                const view = btn.dataset.view;
                await this.loadView(view);

                // Update active state
                document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            });
        });
    }

    async loadView(viewName) {
        this.currentView = viewName;

        // Hide all views
        document.querySelectorAll('.content-view').forEach(view => {
            view.style.display = 'none';
        });

        // Show selected view
        switch (viewName) {
            case 'submit':
                document.getElementById('submit-view').style.display = 'block';
                break;
            case 'my-content':
                document.getElementById('my-content-view').style.display = 'block';
                await this.loadMyContent();
                break;
            case 'queue':
                document.getElementById('queue-view').style.display = 'block';
                await this.loadQueue();
                break;
            case 'admin':
                document.getElementById('admin-view').style.display = 'block';
                await this.loadAdminPanel();
                break;
        }
    }

    // Content Submission

    setupSubmitListeners() {
        // Content type selector
        document.querySelectorAll('.type-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const type = btn.dataset.type;

                // Update active state
                document.querySelectorAll('.type-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');

                // Show appropriate form
                document.querySelectorAll('.submit-form').forEach(form => {
                    form.style.display = 'none';
                });
                document.getElementById(`${type}-submit`).style.display = 'block';

                this.clearError('submit-error');
                this.clearError('submit-success');
            });
        });

        // Text submission
        document.getElementById('submit-text-btn').addEventListener('click', () => this.submitText());

        // Image submission
        document.getElementById('image-file').addEventListener('change', (e) => this.previewImage(e));
        document.getElementById('submit-image-btn').addEventListener('click', () => this.submitImage());

        // Video submission
        document.getElementById('video-file').addEventListener('change', (e) => this.previewVideo(e));
        document.getElementById('submit-video-btn').addEventListener('click', () => this.submitVideo());
    }

    async submitText() {
        const textContent = document.getElementById('text-content').value.trim();
        const priority = parseInt(document.getElementById('text-priority').value);

        if (!textContent) {
            this.showError('submit-error', 'Please enter text content');
            return;
        }

        const formData = new FormData();
        formData.append('content_type', 'text');
        formData.append('text_content', textContent);
        formData.append('priority', priority);

        await this.submitContent(formData);

        // Clear form on success
        document.getElementById('text-content').value = '';
    }

    async submitImage() {
        const fileInput = document.getElementById('image-file');
        const priority = parseInt(document.getElementById('image-priority').value);

        if (!fileInput.files.length) {
            this.showError('submit-error', 'Please select an image file');
            return;
        }

        const formData = new FormData();
        formData.append('content_type', 'image');
        formData.append('file', fileInput.files[0]);
        formData.append('priority', priority);

        await this.submitContent(formData);

        // Clear form on success
        fileInput.value = '';
        document.getElementById('image-preview').style.display = 'none';
    }

    async submitVideo() {
        const fileInput = document.getElementById('video-file');
        const priority = parseInt(document.getElementById('video-priority').value);

        if (!fileInput.files.length) {
            this.showError('submit-error', 'Please select a video file');
            return;
        }

        const formData = new FormData();
        formData.append('content_type', 'video');
        formData.append('file', fileInput.files[0]);
        formData.append('priority', priority);

        await this.submitContent(formData);

        // Clear form on success
        fileInput.value = '';
        document.getElementById('video-preview').style.display = 'none';
    }

    async submitContent(formData) {
        this.clearError('submit-error');
        this.clearError('submit-success');

        try {
            const response = await fetch('/api/content', {
                method: 'POST',
                credentials: 'include',
                body: formData
            });

            const data = await response.json();

            if (response.ok) {
                this.showSuccess('submit-success', data.message || 'Content submitted successfully!');
                setTimeout(() => this.clearError('submit-success'), 3000);
            } else {
                this.showError('submit-error', data.detail || 'Submission failed');
            }
        } catch (error) {
            this.showError('submit-error', 'Network error. Please try again.');
        }
    }

    previewImage(event) {
        const file = event.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = (e) => {
                document.getElementById('image-preview-img').src = e.target.result;
                document.getElementById('image-preview').style.display = 'block';
            };
            reader.readAsDataURL(file);
        }
    }

    previewVideo(event) {
        const file = event.target.files[0];
        if (file) {
            const url = URL.createObjectURL(file);
            document.getElementById('video-preview-player').src = url;
            document.getElementById('video-preview').style.display = 'block';
        }
    }

    // Content Listing

    async loadMyContent() {
        const listEl = document.getElementById('content-list');
        listEl.innerHTML = '<div class="loading">Loading content...</div>';

        try {
            const statusFilter = document.getElementById('content-status-filter').value;
            const url = statusFilter ? `/api/content?status=${statusFilter}` : '/api/content';

            const response = await fetch(url, { credentials: 'include' });
            const data = await response.json();

            if (response.ok && data.content.length > 0) {
                listEl.innerHTML = data.content.map(item => this.renderContentItem(item)).join('');
            } else {
                listEl.innerHTML = '<p class="loading">No content found</p>';
            }
        } catch (error) {
            listEl.innerHTML = '<p class="error-message">Failed to load content</p>';
        }

        // Setup filter listeners
        document.getElementById('content-status-filter').addEventListener('change', () => this.loadMyContent());
        document.getElementById('refresh-content-btn').addEventListener('click', () => this.loadMyContent());
    }

    async loadQueue() {
        const listEl = document.getElementById('queue-list');
        listEl.innerHTML = '<div class="loading">Loading queue...</div>';

        // Load stats
        await this.loadQueueStats();

        try {
            const response = await fetch('/api/moderation/queue', { credentials: 'include' });
            const data = await response.json();

            if (response.ok && data.queue.length > 0) {
                listEl.innerHTML = data.queue.map(item => this.renderContentItem(item, true)).join('');
            } else {
                listEl.innerHTML = '<p class="loading">Queue is empty</p>';
            }
        } catch (error) {
            listEl.innerHTML = '<p class="error-message">Failed to load queue</p>';
        }
    }

    async loadQueueStats() {
        try {
            const response = await fetch('/api/moderation/stats', { credentials: 'include' });
            const stats = await response.json();

            if (response.ok) {
                document.getElementById('stat-pending').textContent = stats.pending;
                document.getElementById('stat-flagged').textContent = stats.flagged;
                document.getElementById('stat-processing').textContent = stats.processing;
            }
        } catch (error) {
            console.error('Failed to load stats:', error);
        }
    }

    async loadAdminPanel() {
        const listEl = document.getElementById('users-list');
        listEl.innerHTML = '<div class="loading">Loading users...</div>';

        try {
            const response = await fetch('/api/admin/users', { credentials: 'include' });
            const data = await response.json();

            if (response.ok && data.users.length > 0) {
                listEl.innerHTML = data.users.map(user => this.renderUserItem(user)).join('');
            } else {
                listEl.innerHTML = '<p class="loading">No users found</p>';
            }
        } catch (error) {
            listEl.innerHTML = '<p class="error-message">Failed to load users</p>';
        }
    }

    renderContentItem(item, showClassifications = false) {
        const date = new Date(item.created_at).toLocaleString();

        let preview = '';
        if (item.content_type === 'text') {
            preview = `<div class="content-preview">${this.truncate(item.text_content, 150)}</div>`;
        } else if (item.file_path) {
            preview = `<div class="content-preview">File: ${item.file_path.split('/').pop()}</div>`;
        }

        let classificationsHtml = '';
        if (showClassifications && item.classifications && item.classifications.length > 0) {
            classificationsHtml = '<div class="classifications">';
            item.classifications.forEach(c => {
                classificationsHtml += `
                    <div class="classification-item">
                        <strong>${c.category}</strong>: ${(c.confidence * 100).toFixed(1)}%
                        (${c.provider})
                    </div>
                `;
            });
            classificationsHtml += '</div>';
        }

        return `
            <div class="content-item" data-id="${item.id}">
                <div class="content-item-header">
                    <span class="content-type-badge ${item.content_type}">${item.content_type}</span>
                    <span class="content-status-badge ${item.status}">${item.status}</span>
                </div>
                ${preview}
                ${classificationsHtml}
                <div class="content-meta">
                    <span>Priority: ${item.priority}</span>
                    <span>Submitted: ${date}</span>
                </div>
            </div>
        `;
    }

    renderUserItem(user) {
        return `
            <div class="user-item">
                <div class="user-item-info">
                    <div class="user-item-name">
                        ${user.username}
                        <span class="role-badge ${user.role}">${user.role}</span>
                    </div>
                    <div class="user-item-email">${user.email}</div>
                </div>
                <div class="user-item-actions">
                    ${user.is_active ?
                        `<button class="btn-secondary" onclick="app.deactivateUser('${user.id}')">Deactivate</button>` :
                        `<button class="btn-primary" onclick="app.reactivateUser('${user.id}')">Reactivate</button>`
                    }
                </div>
            </div>
        `;
    }

    // Admin Actions

    async deactivateUser(userId) {
        if (!confirm('Are you sure you want to deactivate this user?')) return;

        try {
            const response = await fetch(`/api/admin/users/${userId}/deactivate`, {
                method: 'POST',
                credentials: 'include'
            });

            if (response.ok) {
                await this.loadAdminPanel();
            } else {
                alert('Failed to deactivate user');
            }
        } catch (error) {
            alert('Network error');
        }
    }

    async reactivateUser(userId) {
        try {
            const response = await fetch(`/api/admin/users/${userId}/reactivate`, {
                method: 'POST',
                credentials: 'include'
            });

            if (response.ok) {
                await this.loadAdminPanel();
            } else {
                alert('Failed to reactivate user');
            }
        } catch (error) {
            alert('Network error');
        }
    }

    // Modal Management

    setupModalListeners() {
        document.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.modal').forEach(modal => {
                    modal.style.display = 'none';
                });
            });
        });
    }

    // Utility Functions

    showError(elementId, message) {
        const el = document.getElementById(elementId);
        el.textContent = message;
        el.style.display = 'block';
    }

    showSuccess(elementId, message) {
        const el = document.getElementById(elementId);
        el.textContent = message;
        el.style.display = 'block';
    }

    clearError(elementId) {
        const el = document.getElementById(elementId);
        el.textContent = '';
        el.style.display = 'none';
    }

    truncate(text, length) {
        if (text.length <= length) return text;
        return text.substring(0, length) + '...';
    }
}

// Initialize app
const app = new ContentModerationApp();
