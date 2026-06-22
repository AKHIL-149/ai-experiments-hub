/**
 * GitHub App Configuration Manager
 * Manages GitHub App setup, status checking, and installation management
 */

class GitHubAppManager {
    constructor(containerId = 'github-app-container') {
        this.containerId = containerId;
        this.status = null;
        this.installations = [];
        this.isLoading = false;
    }

    /**
     * Initialize the GitHub App manager
     */
    async init() {
        await this.loadStatus();
        this.render();
        this.attachEventListeners();
    }

    /**
     * Load GitHub App status from API
     */
    async loadStatus() {
        this.isLoading = true;
        try {
            const response = await fetch('/api/github/app/status', {
                credentials: 'same-origin'
            });

            if (response.ok) {
                this.status = await response.json();
            } else {
                this.status = { configured: false, error: 'Failed to load status' };
            }
        } catch (error) {
            console.error('Error loading GitHub App status:', error);
            this.status = { configured: false, error: error.message };
        } finally {
            this.isLoading = false;
        }
    }

    /**
     * Load GitHub App installations
     */
    async loadInstallations() {
        try {
            const response = await fetch('/api/github/app/installations', {
                credentials: 'same-origin'
            });

            if (response.ok) {
                const data = await response.json();
                this.installations = data.installations || [];
            } else {
                this.installations = [];
            }
        } catch (error) {
            console.error('Error loading installations:', error);
            this.installations = [];
        }
    }

    /**
     * Render the GitHub App configuration UI
     */
    render() {
        const container = document.getElementById(this.containerId);
        if (!container) return;

        container.innerHTML = `
            <div class="github-app-manager">
                ${this.renderStatusCard()}
                ${this.status && this.status.configured ? this.renderConfigurationCard() : this.renderSetupCard()}
                ${this.status && this.status.configured ? this.renderInstallationsCard() : ''}
            </div>
        `;
    }

    /**
     * Render status card
     */
    renderStatusCard() {
        if (this.isLoading) {
            return `
                <div class="settings-section">
                    <div class="loading-spinner">Loading GitHub App status...</div>
                </div>
            `;
        }

        if (!this.status) {
            return '';
        }

        const statusIcon = this.status.configured ? '✅' : '⚠️';
        const statusText = this.status.configured ? 'Configured' : 'Not Configured';
        const statusClass = this.status.configured ? 'status-success' : 'status-warning';

        return `
            <div class="settings-section">
                <h2 class="settings-section-title">🤖 GitHub App Status</h2>
                <div class="status-card ${statusClass}">
                    <div class="status-header">
                        <span class="status-icon">${statusIcon}</span>
                        <span class="status-text">${statusText}</span>
                    </div>
                    ${this.status.configured ? `
                        <div class="status-details">
                            <div class="status-item">
                                <strong>App ID:</strong> ${this.status.app_id}
                            </div>
                            <div class="status-item">
                                <strong>Private Key:</strong> ${this.status.private_key_set ? '✓ Set' : '✗ Not Set'}
                            </div>
                            ${this.status.webhook_url ? `
                                <div class="status-item">
                                    <strong>Webhook URL:</strong>
                                    <code class="webhook-url">${this.status.webhook_url}</code>
                                    <button class="btn-copy" onclick="navigator.clipboard.writeText('${this.status.webhook_url}')">
                                        Copy
                                    </button>
                                </div>
                            ` : ''}
                        </div>
                        <div class="status-actions">
                            <button class="btn btn-secondary" id="test-github-app">Test Connection</button>
                            <button class="btn btn-secondary" id="refresh-installations">Refresh Installations</button>
                        </div>
                    ` : `
                        <p class="status-description">
                            GitHub App is not configured. Configure it below to enable automatic PR analysis via webhooks.
                        </p>
                    `}
                </div>
            </div>
        `;
    }

    /**
     * Render setup card for configuring GitHub App
     */
    renderSetupCard() {
        return `
            <div class="settings-section">
                <h2 class="settings-section-title">⚙️ Configure GitHub App</h2>
                <p class="settings-section-description">
                    Set up a GitHub App to enable automatic PR analysis via webhooks.
                    <a href="https://docs.github.com/en/apps/creating-github-apps/creating-github-apps/creating-a-github-app" target="_blank">
                        Learn more →
                    </a>
                </p>

                <form id="github-app-config-form" class="config-form">
                    <div class="form-group">
                        <label for="app-id">GitHub App ID</label>
                        <input
                            type="text"
                            id="app-id"
                            name="app_id"
                            class="form-input"
                            placeholder="123456"
                            required
                        >
                        <span class="form-help">Found in your GitHub App's settings page</span>
                    </div>

                    <div class="form-group">
                        <label for="private-key">Private Key (PEM format)</label>
                        <textarea
                            id="private-key"
                            name="private_key"
                            class="form-textarea"
                            rows="10"
                            placeholder="-----BEGIN RSA PRIVATE KEY-----
...
-----END RSA PRIVATE KEY-----"
                            required
                        ></textarea>
                        <span class="form-help">Generate and download from your GitHub App's settings</span>
                    </div>

                    <div class="form-actions">
                        <button type="submit" class="btn btn-primary">Save Configuration</button>
                    </div>
                </form>

                <div id="config-result" class="config-result"></div>
            </div>
        `;
    }

    /**
     * Render configuration card for updating existing GitHub App
     */
    renderConfigurationCard() {
        return `
            <div class="settings-section">
                <h2 class="settings-section-title">⚙️ Update GitHub App Configuration</h2>
                <p class="settings-section-description">
                    Update your GitHub App credentials (admin only).
                </p>

                <div class="config-warning">
                    ⚠️ Updating these settings requires server restart to take effect.
                </div>

                <form id="github-app-update-form" class="config-form">
                    <div class="form-group">
                        <label for="update-app-id">GitHub App ID</label>
                        <input
                            type="text"
                            id="update-app-id"
                            name="app_id"
                            class="form-input"
                            placeholder="${this.status.app_id}"
                            value="${this.status.app_id}"
                        >
                    </div>

                    <div class="form-group">
                        <label for="update-private-key">Private Key (PEM format)</label>
                        <textarea
                            id="update-private-key"
                            name="private_key"
                            class="form-textarea"
                            rows="8"
                            placeholder="Paste new private key to update..."
                        ></textarea>
                        <span class="form-help">Leave empty to keep existing key</span>
                    </div>

                    <div class="form-actions">
                        <button type="submit" class="btn btn-primary">Update Configuration</button>
                    </div>
                </form>

                <div id="update-result" class="config-result"></div>
            </div>
        `;
    }

    /**
     * Render installations card
     */
    renderInstallationsCard() {
        return `
            <div class="settings-section">
                <h2 class="settings-section-title">📦 Installations</h2>
                <p class="settings-section-description">
                    GitHub App installations and connected repositories.
                </p>

                <div id="installations-container">
                    ${this.installations.length === 0 ? `
                        <div class="empty-state">
                            <p>No installations found. Click "Refresh Installations" to check for new installations.</p>
                        </div>
                    ` : `
                        <div class="installations-list">
                            ${this.installations.map(inst => this.renderInstallation(inst)).join('')}
                        </div>
                    `}
                </div>
            </div>
        `;
    }

    /**
     * Render single installation
     */
    renderInstallation(installation) {
        return `
            <div class="installation-card">
                <img src="${installation.account.avatar_url}" alt="${installation.account.login}" class="installation-avatar">
                <div class="installation-info">
                    <h3>${installation.account.login}</h3>
                    <span class="installation-type">${installation.account.type}</span>
                    <div class="installation-meta">
                        <span>ID: ${installation.id}</span>
                        <span>•</span>
                        <span>${installation.repository_selection || 'all'} repositories</span>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Attach event listeners
     */
    attachEventListeners() {
        // Test connection button
        const testBtn = document.getElementById('test-github-app');
        if (testBtn) {
            testBtn.addEventListener('click', () => this.testConnection());
        }

        // Refresh installations button
        const refreshBtn = document.getElementById('refresh-installations');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refreshInstallations());
        }

        // Configuration form (setup)
        const configForm = document.getElementById('github-app-config-form');
        if (configForm) {
            configForm.addEventListener('submit', (e) => this.handleConfigSubmit(e));
        }

        // Configuration form (update)
        const updateForm = document.getElementById('github-app-update-form');
        if (updateForm) {
            updateForm.addEventListener('submit', (e) => this.handleUpdateSubmit(e));
        }
    }

    /**
     * Test GitHub App connection
     */
    async testConnection() {
        const testBtn = document.getElementById('test-github-app');
        if (testBtn) {
            testBtn.disabled = true;
            testBtn.textContent = 'Testing...';
        }

        try {
            const response = await fetch('/api/github/app/test', {
                method: 'POST',
                credentials: 'same-origin'
            });

            const result = await response.json();

            if (result.success) {
                this.showToast('✅ GitHub App connection successful!', 'success');
                console.log('App Info:', result.app_info);
            } else {
                this.showToast('❌ Connection failed: ' + result.error, 'error');
            }
        } catch (error) {
            this.showToast('❌ Test failed: ' + error.message, 'error');
        } finally {
            if (testBtn) {
                testBtn.disabled = false;
                testBtn.textContent = 'Test Connection';
            }
        }
    }

    /**
     * Refresh installations list
     */
    async refreshInstallations() {
        const refreshBtn = document.getElementById('refresh-installations');
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.textContent = 'Refreshing...';
        }

        await this.loadInstallations();
        this.render();
        this.attachEventListeners();

        this.showToast(`Found ${this.installations.length} installation(s)`, 'success');
    }

    /**
     * Handle configuration form submit
     */
    async handleConfigSubmit(event) {
        event.preventDefault();

        const formData = new FormData(event.target);
        const data = {
            app_id: formData.get('app_id'),
            private_key: formData.get('private_key')
        };

        const resultDiv = document.getElementById('config-result');
        resultDiv.innerHTML = '<div class="loading-spinner">Saving configuration...</div>';

        try {
            const response = await fetch('/api/github/app/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                credentials: 'same-origin',
                body: JSON.stringify(data)
            });

            const result = await response.json();

            if (response.ok) {
                resultDiv.innerHTML = `
                    <div class="alert alert-success">
                        ✅ ${result.message}
                        ${result.restart_required ? '<br><strong>Please restart the server for changes to take effect.</strong>' : ''}
                    </div>
                `;

                // Reload status after a short delay
                setTimeout(async () => {
                    await this.loadStatus();
                    await this.loadInstallations();
                    this.render();
                    this.attachEventListeners();
                }, 2000);
            } else {
                resultDiv.innerHTML = `
                    <div class="alert alert-error">
                        ❌ ${result.detail || 'Configuration failed'}
                    </div>
                `;
            }
        } catch (error) {
            resultDiv.innerHTML = `
                <div class="alert alert-error">
                    ❌ Error: ${error.message}
                </div>
            `;
        }
    }

    /**
     * Handle update form submit
     */
    async handleUpdateSubmit(event) {
        event.preventDefault();

        const formData = new FormData(event.target);
        const data = {
            app_id: formData.get('app_id') || this.status.app_id,
            private_key: formData.get('private_key')
        };

        // If private key is empty, don't send it
        if (!data.private_key) {
            this.showToast('⚠️ Please provide a private key to update', 'warning');
            return;
        }

        const resultDiv = document.getElementById('update-result');
        resultDiv.innerHTML = '<div class="loading-spinner">Updating configuration...</div>';

        try {
            const response = await fetch('/api/github/app/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                credentials: 'same-origin',
                body: JSON.stringify(data)
            });

            const result = await response.json();

            if (response.ok) {
                resultDiv.innerHTML = `
                    <div class="alert alert-success">
                        ✅ ${result.message}
                        ${result.restart_required ? '<br><strong>Please restart the server for changes to take effect.</strong>' : ''}
                    </div>
                `;
            } else {
                resultDiv.innerHTML = `
                    <div class="alert alert-error">
                        ❌ ${result.detail || 'Update failed'}
                    </div>
                `;
            }
        } catch (error) {
            resultDiv.innerHTML = `
                <div class="alert alert-error">
                    ❌ Error: ${error.message}
                </div>
            `;
        }
    }

    /**
     * Show toast notification
     */
    showToast(message, type = 'info') {
        // Simple toast implementation
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
            color: white;
            border-radius: 6px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            z-index: 1000;
            animation: slideIn 0.3s ease-out;
        `;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease-out';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
}

// Export for use in settings page
if (typeof module !== 'undefined' && module.exports) {
    module.exports = GitHubAppManager;
}
