/**
 * Notification Manager
 * Handles notification center, preferences, and rules management
 */

class NotificationManager {
    constructor() {
        this.notifications = [];
        this.currentFilter = 'all';
        this.currentPage = 0;
        this.pageSize = 20;
        this.hasMore = true;
    }

    async init() {
        await this.loadNotifications();
        await this.loadRepositories();
        this.updateCounts();
        this.startPolling();
    }

    async loadNotifications() {
        try {
            const loadingState = document.getElementById('loading-state');
            const emptyState = document.getElementById('empty-state');

            if (loadingState) loadingState.style.display = 'flex';

            const response = await fetch(`/api/notifications?offset=${this.currentPage * this.pageSize}&limit=${this.pageSize}`);
            const data = await response.json();

            if (loadingState) loadingState.style.display = 'none';

            if (data.success) {
                this.notifications = this.notifications.concat(data.notifications || []);
                this.hasMore = data.has_more || false;
                this.renderNotifications();

                if (this.notifications.length === 0 && emptyState) {
                    emptyState.style.display = 'flex';
                }
            }
        } catch (error) {
            console.error('Failed to load notifications:', error);
            this.showError('Failed to load notifications');
        }
    }

    renderNotifications() {
        const container = document.getElementById('notifications-list');
        if (!container) return;

        // Clear loading/empty states
        const loadingState = document.getElementById('loading-state');
        const emptyState = document.getElementById('empty-state');
        if (loadingState) loadingState.style.display = 'none';
        if (emptyState) emptyState.style.display = 'none';

        // Filter notifications
        const filtered = this.filterNotifications();

        if (filtered.length === 0) {
            if (emptyState) emptyState.style.display = 'flex';
            return;
        }

        // Render each notification
        filtered.forEach(notification => {
            if (!document.querySelector(`[data-id="${notification.id}"]`)) {
                const element = this.createNotificationElement(notification);
                container.appendChild(element);
            }
        });

        // Show/hide load more button
        const loadMore = document.getElementById('load-more');
        if (loadMore) {
            loadMore.style.display = this.hasMore ? 'block' : 'none';
        }
    }

    createNotificationElement(notification) {
        const template = document.getElementById('notification-template');
        if (!template) return document.createElement('div');

        const html = template.innerHTML
            .replace(/{id}/g, notification.id)
            .replace(/{read}/g, notification.read)
            .replace(/{severity}/g, notification.severity || 'info')
            .replace(/{icon}/g, this.getSeverityIcon(notification.severity))
            .replace(/{title}/g, notification.title || 'Notification')
            .replace(/{time}/g, this.formatTime(notification.created_at))
            .replace(/{message}/g, notification.message || '')
            .replace(/{repository}/g, notification.repository ? `<span class="badge">${notification.repository}</span>` : '')
            .replace(/{pr_number}/g, notification.pr_number ? `<span class="badge">#${notification.pr_number}</span>` : '');

        const div = document.createElement('div');
        div.innerHTML = html.trim();
        return div.firstChild;
    }

    getSeverityIcon(severity) {
        const icons = {
            'critical': '🔴',
            'error': '🟠',
            'warning': '🟡',
            'info': '🔵'
        };
        return icons[severity] || '⚪';
    }

    formatTime(timestamp) {
        if (!timestamp) return '';
        const date = new Date(timestamp);
        const now = new Date();
        const diff = now - date;
        const minutes = Math.floor(diff / 60000);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        if (minutes < 1) return 'Just now';
        if (minutes < 60) return `${minutes}m ago`;
        if (hours < 24) return `${hours}h ago`;
        if (days < 7) return `${days}d ago`;
        return date.toLocaleDateString();
    }

    filterNotifications() {
        let filtered = this.notifications;

        // Apply type filter
        if (this.currentFilter !== 'all') {
            filtered = filtered.filter(n => {
                if (this.currentFilter === 'unread') return !n.read;
                if (this.currentFilter === 'critical') return n.severity === 'critical';
                return n.type === this.currentFilter;
            });
        }

        // Apply severity filter
        const severityFilter = document.getElementById('severity-filter');
        if (severityFilter && severityFilter.value) {
            filtered = filtered.filter(n => n.severity === severityFilter.value);
        }

        // Apply repository filter
        const repoFilter = document.getElementById('repository-filter');
        if (repoFilter && repoFilter.value) {
            filtered = filtered.filter(n => n.repository === repoFilter.value);
        }

        return filtered;
    }

    filterByType(type) {
        this.currentFilter = type;

        // Update active tab
        document.querySelectorAll('.filter-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.filter === type);
        });

        // Clear and re-render
        const container = document.getElementById('notifications-list');
        if (container) {
            const items = container.querySelectorAll('.notification-item');
            items.forEach(item => item.remove());
        }

        this.renderNotifications();
    }

    applyFilters() {
        this.filterByType(this.currentFilter);
    }

    updateCounts() {
        const counts = {
            all: this.notifications.length,
            unread: this.notifications.filter(n => !n.read).length,
            pr: this.notifications.filter(n => n.type === 'pr_analysis').length,
            critical: this.notifications.filter(n => n.severity === 'critical').length,
            mentions: this.notifications.filter(n => n.type === 'mention').length
        };

        document.getElementById('count-all').textContent = counts.all;
        document.getElementById('count-unread').textContent = counts.unread;
        document.getElementById('count-pr').textContent = counts.pr;
        document.getElementById('count-critical').textContent = counts.critical;
        document.getElementById('count-mentions').textContent = counts.mentions;
    }

    async markAsRead(notificationId) {
        try {
            const response = await fetch(`/api/notifications/${notificationId}/read`, {
                method: 'POST'
            });

            if (response.ok) {
                const notification = this.notifications.find(n => n.id === notificationId);
                if (notification) {
                    notification.read = true;
                }

                const element = document.querySelector(`[data-id="${notificationId}"]`);
                if (element) {
                    element.dataset.read = 'true';
                }

                this.updateCounts();
            }
        } catch (error) {
            console.error('Failed to mark as read:', error);
        }
    }

    async markAllRead() {
        try {
            const response = await fetch('/api/notifications/read-all', {
                method: 'POST'
            });

            if (response.ok) {
                this.notifications.forEach(n => n.read = true);
                document.querySelectorAll('.notification-item').forEach(el => {
                    el.dataset.read = 'true';
                });
                this.updateCounts();
                this.showSuccess('All notifications marked as read');
            }
        } catch (error) {
            console.error('Failed to mark all as read:', error);
        }
    }

    async deleteNotification(notificationId) {
        if (!confirm('Delete this notification?')) return;

        try {
            const response = await fetch(`/api/notifications/${notificationId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                this.notifications = this.notifications.filter(n => n.id !== notificationId);
                const element = document.querySelector(`[data-id="${notificationId}"]`);
                if (element) {
                    element.remove();
                }
                this.updateCounts();
            }
        } catch (error) {
            console.error('Failed to delete notification:', error);
        }
    }

    viewDetails(notificationId) {
        const notification = this.notifications.find(n => n.id === notificationId);
        if (!notification) return;

        const modal = document.getElementById('notification-modal');
        const title = document.getElementById('modal-title');
        const body = document.getElementById('modal-body');

        title.textContent = notification.title;
        body.innerHTML = `
            <div class="notification-details">
                <p><strong>Type:</strong> ${notification.type}</p>
                <p><strong>Severity:</strong> <span class="badge badge-${notification.severity}">${notification.severity}</span></p>
                <p><strong>Time:</strong> ${new Date(notification.created_at).toLocaleString()}</p>
                ${notification.repository ? `<p><strong>Repository:</strong> ${notification.repository}</p>` : ''}
                ${notification.pr_number ? `<p><strong>PR:</strong> #${notification.pr_number}</p>` : ''}
                <div class="message-content">
                    <h4>Message:</h4>
                    <p>${notification.message}</p>
                </div>
                ${notification.metadata ? `
                    <div class="metadata">
                        <h4>Additional Details:</h4>
                        <pre>${JSON.stringify(notification.metadata, null, 2)}</pre>
                    </div>
                ` : ''}
            </div>
        `;

        modal.style.display = 'flex';
        this.markAsRead(notificationId);
    }

    closeModal() {
        const modal = document.getElementById('notification-modal');
        if (modal) {
            modal.style.display = 'none';
        }
    }

    async loadRepositories() {
        try {
            const response = await fetch('/api/repositories');
            const data = await response.json();

            if (data.success) {
                const select = document.getElementById('repository-filter');
                if (select) {
                    data.repositories.forEach(repo => {
                        const option = document.createElement('option');
                        option.value = repo.name;
                        option.textContent = repo.name;
                        select.appendChild(option);
                    });
                }
            }
        } catch (error) {
            console.error('Failed to load repositories:', error);
        }
    }

    async loadMore() {
        this.currentPage++;
        await this.loadNotifications();
    }

    startPolling() {
        // Poll for new notifications every 30 seconds
        setInterval(() => {
            this.checkForNew();
        }, 30000);
    }

    async checkForNew() {
        try {
            const latestId = this.notifications[0]?.id;
            const response = await fetch(`/api/notifications?since=${latestId}&limit=10`);
            const data = await response.json();

            if (data.success && data.notifications.length > 0) {
                this.notifications = data.notifications.concat(this.notifications);
                this.renderNotifications();
                this.updateCounts();
                this.showNotificationBadge(data.notifications.length);
            }
        } catch (error) {
            console.error('Failed to check for new notifications:', error);
        }
    }

    showNotificationBadge(count) {
        // Update page title
        document.title = `(${count}) Notifications - AI Code Review Assistant`;

        // Show browser notification if permitted
        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification('New Code Review Notifications', {
                body: `You have ${count} new notification${count > 1 ? 's' : ''}`,
                icon: '/static/favicon.ico'
            });
        }
    }

    showError(message) {
        this.showToast(message, 'error');
    }

    showSuccess(message) {
        this.showToast(message, 'success');
    }

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            top: 2rem;
            right: 2rem;
            background: ${type === 'success' ? '#10b981' : '#ef4444'};
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            z-index: 10000;
        `;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 3000);
    }
}


class PreferencesManager {
    constructor() {
        this.preferences = {};
        this.configs = {
            email: null,
            slack: null,
            discord: null
        };
    }

    async init() {
        await this.loadPreferences();
        await this.loadChannelConfigs();
    }

    async loadPreferences() {
        try {
            const response = await fetch('/api/notifications/preferences');
            const data = await response.json();

            if (data.success) {
                this.preferences = data.preferences || {};
                this.populateForm();
            }
        } catch (error) {
            console.error('Failed to load preferences:', error);
        }
    }

    async loadChannelConfigs() {
        // Load email config
        try {
            const response = await fetch('/api/email/config');
            const data = await response.json();
            if (data.success && data.configurations.length > 0) {
                this.configs.email = data.configurations[0];
                this.populateEmailConfig();
            }
        } catch (error) {
            console.error('Failed to load email config:', error);
        }

        // Load Slack config
        try {
            const response = await fetch('/api/slack/config');
            const data = await response.json();
            if (data.success && data.configurations.length > 0) {
                this.configs.slack = data.configurations[0];
                this.populateSlackConfig();
            }
        } catch (error) {
            console.error('Failed to load Slack config:', error);
        }

        // Load Discord config
        try {
            const response = await fetch('/api/discord/config');
            const data = await response.json();
            if (data.success && data.configurations.length > 0) {
                this.configs.discord = data.configurations[0];
                this.populateDiscordConfig();
            }
        } catch (error) {
            console.error('Failed to load Discord config:', error);
        }
    }

    populateForm() {
        // Populate severity filters
        ['critical', 'error', 'warning', 'info'].forEach(severity => {
            const checkbox = document.getElementById(`severity-${severity}`);
            if (checkbox && this.preferences.severities) {
                checkbox.checked = this.preferences.severities.includes(severity);
            }
        });

        // Populate quiet hours
        if (this.preferences.quiet_hours) {
            const enabled = document.getElementById('quiet-hours-enabled');
            if (enabled) {
                enabled.checked = this.preferences.quiet_hours.enabled || false;
                if (enabled.checked) {
                    document.getElementById('quiet-hours-settings').style.display = 'block';
                }
            }
        }

        // Populate advanced settings
        const batchEnabled = document.getElementById('batch-notifications');
        if (batchEnabled) {
            batchEnabled.checked = this.preferences.batch_notifications || false;
            if (batchEnabled.checked) {
                document.getElementById('batch-interval-setting').style.display = 'block';
            }
        }

        const rateLimit = document.getElementById('rate-limit');
        if (rateLimit && this.preferences.rate_limit) {
            rateLimit.value = this.preferences.rate_limit;
        }
    }

    populateEmailConfig() {
        const config = this.configs.email;
        const enabled = document.getElementById('email-enabled');
        if (enabled) {
            enabled.checked = config.enabled || false;
            if (enabled.checked) {
                document.getElementById('email-config').style.display = 'block';
            }
        }

        const email = document.getElementById('email-address');
        if (email) email.value = config.to_email || '';

        const digest = document.getElementById('email-digest');
        if (digest) digest.checked = config.enable_digest || false;

        const time = document.getElementById('email-digest-time');
        if (time && config.digest_time) time.value = config.digest_time;
    }

    populateSlackConfig() {
        const config = this.configs.slack;
        const enabled = document.getElementById('slack-enabled');
        if (enabled) {
            enabled.checked = config.enabled || false;
            if (enabled.checked) {
                document.getElementById('slack-config').style.display = 'block';
            }
        }

        const webhook = document.getElementById('slack-webhook');
        if (webhook) webhook.value = config.webhook_url || '';

        const channel = document.getElementById('slack-channel');
        if (channel) channel.value = config.channel || '';

        const threading = document.getElementById('slack-threading');
        if (threading) threading.checked = config.use_threading || false;
    }

    populateDiscordConfig() {
        const config = this.configs.discord;
        const enabled = document.getElementById('discord-enabled');
        if (enabled) {
            enabled.checked = config.enabled || false;
            if (enabled.checked) {
                document.getElementById('discord-config').style.display = 'block';
            }
        }

        const webhook = document.getElementById('discord-webhook');
        if (webhook) webhook.value = config.webhook_url || '';

        const username = document.getElementById('discord-username');
        if (username) username.value = config.username || '';
    }

    toggleChannel(channel) {
        const checkbox = document.getElementById(`${channel}-enabled`);
        const config = document.getElementById(`${channel}-config`);

        if (checkbox && config) {
            config.style.display = checkbox.checked ? 'block' : 'none';
        }
    }

    toggleQuietHours() {
        const checkbox = document.getElementById('quiet-hours-enabled');
        const settings = document.getElementById('quiet-hours-settings');

        if (checkbox && settings) {
            settings.style.display = checkbox.checked ? 'block' : 'none';
        }
    }

    async savePreferences() {
        try {
            // Save channel configurations
            await this.saveChannelConfig('email');
            await this.saveChannelConfig('slack');
            await this.saveChannelConfig('discord');

            // Save general preferences
            const severities = [];
            ['critical', 'error', 'warning', 'info'].forEach(severity => {
                const checkbox = document.getElementById(`severity-${severity}`);
                if (checkbox && checkbox.checked) {
                    severities.push(severity);
                }
            });

            const quietHoursEnabled = document.getElementById('quiet-hours-enabled');
            const quietHours = quietHoursEnabled?.checked ? {
                enabled: true,
                start: document.getElementById('quiet-start').value,
                end: document.getElementById('quiet-end').value,
                timezone: document.getElementById('quiet-timezone').value,
                days: Array.from(document.querySelectorAll('input[name="quiet-day"]:checked')).map(cb => parseInt(cb.value))
            } : { enabled: false };

            const preferences = {
                severities,
                quiet_hours: quietHours,
                batch_notifications: document.getElementById('batch-notifications').checked,
                batch_interval: parseInt(document.getElementById('batch-interval').value),
                rate_limit: parseInt(document.getElementById('rate-limit').value)
            };

            const response = await fetch('/api/notifications/preferences', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(preferences)
            });

            if (response.ok) {
                document.getElementById('save-reminder').style.display = 'none';
                this.showSuccess('Preferences saved successfully');
            }
        } catch (error) {
            console.error('Failed to save preferences:', error);
            this.showError('Failed to save preferences');
        }
    }

    async saveChannelConfig(channel) {
        const enabled = document.getElementById(`${channel}-enabled`);
        if (!enabled || !enabled.checked) return;

        const config = {};

        if (channel === 'email') {
            config.to_email = document.getElementById('email-address').value;
            config.enable_digest = document.getElementById('email-digest').checked;
            config.digest_time = document.getElementById('email-digest-time').value;
            config.enabled = true;
        } else if (channel === 'slack') {
            config.webhook_url = document.getElementById('slack-webhook').value;
            config.channel = document.getElementById('slack-channel').value;
            config.use_threading = document.getElementById('slack-threading').checked;
            config.enabled = true;
        } else if (channel === 'discord') {
            config.webhook_url = document.getElementById('discord-webhook').value;
            config.username = document.getElementById('discord-username').value;
            config.enabled = true;
        }

        if (this.configs[channel]) {
            config.id = this.configs[channel].id;
        }

        try {
            const response = await fetch(`/api/${channel}/config`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });

            return response.ok;
        } catch (error) {
            console.error(`Failed to save ${channel} config:`, error);
            return false;
        }
    }

    async testChannel(channel) {
        try {
            const config = {};

            if (channel === 'email') {
                config.to_email = document.getElementById('email-address').value;
            } else if (channel === 'slack') {
                config.webhook_url = document.getElementById('slack-webhook').value;
                config.channel = document.getElementById('slack-channel').value;
            } else if (channel === 'discord') {
                config.webhook_url = document.getElementById('discord-webhook').value;
            }

            const response = await fetch(`/api/${channel}/test`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });

            if (response.ok) {
                this.showSuccess(`Test notification sent to ${channel}!`);
            } else {
                this.showError(`Failed to send test notification to ${channel}`);
            }
        } catch (error) {
            console.error(`Test ${channel} failed:`, error);
            this.showError(`Failed to test ${channel} configuration`);
        }
    }

    showSuccess(message) {
        const toast = document.createElement('div');
        toast.className = 'toast toast-success';
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            top: 2rem;
            right: 2rem;
            background: #10b981;
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            z-index: 10000;
        `;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 3000);
    }

    showError(message) {
        const toast = document.createElement('div');
        toast.className = 'toast toast-error';
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            top: 2rem;
            right: 2rem;
            background: #ef4444;
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            z-index: 10000;
        `;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 3000);
    }
}


class RulesManager {
    constructor() {
        this.rules = [];
        this.currentRule = null;
    }

    async init() {
        await this.loadRules();
    }

    async loadRules() {
        try {
            const loading = document.getElementById('rules-loading');
            const empty = document.getElementById('rules-empty');
            const list = document.getElementById('rules-list');

            if (loading) loading.style.display = 'flex';

            const response = await fetch('/api/notification-rules');
            const data = await response.json();

            if (loading) loading.style.display = 'none';

            if (data.success) {
                this.rules = data.rules || [];

                if (this.rules.length === 0) {
                    if (empty) empty.style.display = 'block';
                } else {
                    this.renderRules();
                }
            }
        } catch (error) {
            console.error('Failed to load rules:', error);
        }
    }

    renderRules() {
        const list = document.getElementById('rules-list');
        if (!list) return;

        // Clear existing
        list.querySelectorAll('.rule-card').forEach(card => card.remove());

        this.rules.forEach(rule => {
            const card = this.createRuleCard(rule);
            list.appendChild(card);
        });
    }

    createRuleCard(rule) {
        const card = document.createElement('div');
        card.className = `rule-card ${rule.enabled ? '' : 'disabled'}`;
        card.innerHTML = `
            <div class="rule-info">
                <h4>${rule.name}</h4>
                <p>${rule.description || 'No description'}</p>
                <div class="rule-badges">
                    <span class="badge">Priority: ${rule.priority}</span>
                    ${rule.notify_slack ? '<span class="badge">Slack</span>' : ''}
                    ${rule.notify_email ? '<span class="badge">Email</span>' : ''}
                    ${rule.notify_discord ? '<span class="badge">Discord</span>' : ''}
                </div>
            </div>
            <div class="rule-actions">
                <button class="btn btn-sm btn-secondary" onclick="rulesManager.editRule('${rule.id}')">Edit</button>
                <button class="btn btn-sm btn-danger" onclick="rulesManager.deleteRule('${rule.id}')">Delete</button>
            </div>
        `;
        return card;
    }

    createRule() {
        this.currentRule = null;
        document.getElementById('rule-modal-title').textContent = 'Create Notification Rule';
        document.getElementById('rule-form').reset();
        document.getElementById('rule-modal').style.display = 'flex';
    }

    editRule(ruleId) {
        const rule = this.rules.find(r => r.id === ruleId);
        if (!rule) return;

        this.currentRule = rule;
        document.getElementById('rule-modal-title').textContent = 'Edit Notification Rule';

        // Populate form
        document.getElementById('rule-name').value = rule.name;
        document.getElementById('rule-description').value = rule.description || '';
        document.getElementById('rule-priority').value = rule.priority;

        // Conditions
        const conditions = rule.conditions || {};
        if (conditions.severity) {
            const select = document.getElementById('rule-severity');
            Array.from(select.options).forEach(option => {
                option.selected = conditions.severity.includes(option.value);
            });
        }

        if (conditions.file_patterns) {
            document.getElementById('rule-patterns').value = conditions.file_patterns.join('\n');
        }

        if (conditions.min_confidence) {
            document.getElementById('rule-confidence').value = conditions.min_confidence;
        }

        // Actions
        document.getElementById('rule-notify-slack').checked = rule.notify_slack || false;
        document.getElementById('rule-notify-email').checked = rule.notify_email || false;
        document.getElementById('rule-notify-discord').checked = rule.notify_discord || false;

        document.getElementById('rule-modal').style.display = 'flex';
    }

    async saveRule() {
        try {
            const name = document.getElementById('rule-name').value;
            if (!name) {
                alert('Please enter a rule name');
                return;
            }

            const severitySelect = document.getElementById('rule-severity');
            const selectedSeverities = Array.from(severitySelect.selectedOptions).map(opt => opt.value);

            const patterns = document.getElementById('rule-patterns').value
                .split('\n')
                .map(p => p.trim())
                .filter(p => p);

            const rule = {
                name,
                description: document.getElementById('rule-description').value,
                priority: parseInt(document.getElementById('rule-priority').value),
                conditions: {
                    severity: selectedSeverities.length > 0 ? selectedSeverities : undefined,
                    file_patterns: patterns.length > 0 ? patterns : undefined,
                    min_confidence: parseInt(document.getElementById('rule-confidence').value) || undefined
                },
                notify_slack: document.getElementById('rule-notify-slack').checked,
                notify_email: document.getElementById('rule-notify-email').checked,
                notify_discord: document.getElementById('rule-notify-discord').checked,
                enabled: true
            };

            if (this.currentRule) {
                rule.id = this.currentRule.id;
            }

            const response = await fetch('/api/notification-rules', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(rule)
            });

            if (response.ok) {
                this.closeModal();
                await this.loadRules();
                this.showSuccess('Rule saved successfully');
            }
        } catch (error) {
            console.error('Failed to save rule:', error);
            this.showError('Failed to save rule');
        }
    }

    async deleteRule(ruleId) {
        if (!confirm('Delete this rule?')) return;

        try {
            const response = await fetch(`/api/notification-rules/${ruleId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                await this.loadRules();
                this.showSuccess('Rule deleted successfully');
            }
        } catch (error) {
            console.error('Failed to delete rule:', error);
            this.showError('Failed to delete rule');
        }
    }

    closeModal() {
        document.getElementById('rule-modal').style.display = 'none';
    }

    showSuccess(message) {
        const toast = document.createElement('div');
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            top: 2rem;
            right: 2rem;
            background: #10b981;
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            z-index: 10000;
        `;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 3000);
    }

    showError(message) {
        const toast = document.createElement('div');
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            top: 2rem;
            right: 2rem;
            background: #ef4444;
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            z-index: 10000;
        `;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 3000);
    }
}
