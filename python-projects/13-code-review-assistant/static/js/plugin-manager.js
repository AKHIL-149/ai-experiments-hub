/**
 * Plugin Manager JavaScript
 * Handles plugin loading, management, and UI interactions
 */

let plugins = [];

// Load plugins on page load
document.addEventListener('DOMContentLoaded', () => {
    loadPlugins();
});

/**
 * Load all plugins from the API
 */
async function loadPlugins() {
    const loading = document.getElementById('loading');
    const container = document.getElementById('plugins-container');
    const emptyState = document.getElementById('empty-state');

    loading.style.display = 'block';
    container.innerHTML = '';
    emptyState.style.display = 'none';

    try {
        const response = await fetch('/api/plugins', {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('Failed to load plugins');
        }

        const data = await response.json();
        plugins = data.plugins || [];

        loading.style.display = 'none';

        if (plugins.length === 0) {
            emptyState.style.display = 'block';
        } else {
            renderPlugins();
        }
    } catch (error) {
        loading.style.display = 'none';
        showAlert('Failed to load plugins: ' + error.message, 'error');
    }
}

/**
 * Render plugins in the grid
 */
function renderPlugins() {
    const container = document.getElementById('plugins-container');
    container.innerHTML = '';

    plugins.forEach(plugin => {
        const card = createPluginCard(plugin);
        container.appendChild(card);
    });
}

/**
 * Create a plugin card element
 */
function createPluginCard(plugin) {
    const card = document.createElement('div');
    card.className = 'plugin-card';

    const statusClass = `status-${plugin.status}`;
    const languages = plugin.supported_languages || [];

    card.innerHTML = `
        <div class="plugin-header">
            <div class="plugin-title">
                <h3>${escapeHtml(plugin.name)}</h3>
                <div class="plugin-version">v${escapeHtml(plugin.version)}</div>
            </div>
            <div class="plugin-status ${statusClass}">${plugin.status}</div>
        </div>

        <div class="plugin-meta">
            <div class="plugin-meta-item">
                <strong>Type:</strong> ${escapeHtml(plugin.plugin_type)}
            </div>
            <div class="plugin-meta-item">
                <strong>Author:</strong> ${escapeHtml(plugin.author || 'Unknown')}
            </div>
            <div class="plugin-meta-item">
                <strong>License:</strong> ${escapeHtml(plugin.license || 'N/A')}
            </div>
            <div class="plugin-meta-item">
                <strong>Loaded:</strong> ${plugin.load_count || 0}x
            </div>
        </div>

        <div class="plugin-description">
            ${escapeHtml(plugin.description || 'No description available')}
        </div>

        ${languages.length > 0 ? `
            <div class="plugin-languages">
                ${languages.map(lang => `
                    <span class="language-badge">${escapeHtml(lang)}</span>
                `).join('')}
            </div>
        ` : ''}

        ${plugin.last_error ? `
            <div class="alert alert-error" style="font-size: 0.875rem; padding: 0.5rem;">
                <strong>Error:</strong> ${escapeHtml(plugin.last_error)}
            </div>
        ` : ''}

        <div class="plugin-stats">
            <div class="stat-item">
                <div class="stat-value">${plugin.load_count || 0}</div>
                <div class="stat-label">Loads</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">${plugin.execution_count || 0}</div>
                <div class="stat-label">Executions</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">${plugin.error_count || 0}</div>
                <div class="stat-label">Errors</div>
            </div>
        </div>

        <div class="plugin-actions">
            <button class="btn btn-sm ${plugin.enabled ? 'btn-secondary' : 'btn-success'}"
                    onclick="togglePlugin('${plugin.id}', ${!plugin.enabled})">
                ${plugin.enabled ? 'Disable' : 'Enable'}
            </button>
            <button class="btn btn-sm btn-secondary" onclick="viewPluginDetails('${plugin.id}')">
                Details
            </button>
            <button class="btn btn-sm btn-danger" onclick="deletePlugin('${plugin.id}')">
                Delete
            </button>
        </div>
    `;

    return card;
}

/**
 * Show load plugin modal
 */
function showLoadPluginModal() {
    const modal = document.getElementById('load-plugin-modal');
    modal.classList.add('active');
    document.getElementById('plugin-file-path').value = './plugins/';
}

/**
 * Close load plugin modal
 */
function closeLoadPluginModal() {
    const modal = document.getElementById('load-plugin-modal');
    modal.classList.remove('active');
    document.getElementById('load-plugin-form').reset();
}

/**
 * Load a new plugin
 */
async function loadPlugin(event) {
    event.preventDefault();

    const filePath = document.getElementById('plugin-file-path').value;
    const enabled = document.getElementById('plugin-enabled').checked;

    try {
        const response = await fetch('/api/plugins/load', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({
                file_path: filePath,
                enabled: enabled
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to load plugin');
        }

        showAlert('Plugin loaded successfully!', 'success');
        closeLoadPluginModal();
        await loadPlugins();
    } catch (error) {
        showAlert('Failed to load plugin: ' + error.message, 'error');
    }
}

/**
 * Toggle plugin enable/disable
 */
async function togglePlugin(pluginId, enabled) {
    try {
        const response = await fetch(`/api/plugins/${pluginId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({
                enabled: enabled
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to update plugin');
        }

        showAlert(`Plugin ${enabled ? 'enabled' : 'disabled'} successfully!`, 'success');
        await loadPlugins();
    } catch (error) {
        showAlert('Failed to update plugin: ' + error.message, 'error');
    }
}

/**
 * Delete a plugin
 */
async function deletePlugin(pluginId) {
    if (!confirm('Are you sure you want to delete this plugin?')) {
        return;
    }

    try {
        const response = await fetch(`/api/plugins/${pluginId}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to delete plugin');
        }

        showAlert('Plugin deleted successfully!', 'success');
        await loadPlugins();
    } catch (error) {
        showAlert('Failed to delete plugin: ' + error.message, 'error');
    }
}

/**
 * View plugin details
 */
async function viewPluginDetails(pluginId) {
    try {
        const response = await fetch(`/api/plugins/${pluginId}/manifest`, {
            credentials: 'include'
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to load plugin details');
        }

        const manifest = data.manifest;
        const modal = document.getElementById('plugin-details-modal');
        const nameEl = document.getElementById('details-plugin-name');
        const contentEl = document.getElementById('plugin-details-content');

        nameEl.textContent = manifest.name;

        let detailsHtml = `
            <div class="form-group">
                <label>Name</label>
                <div>${escapeHtml(manifest.name)}</div>
            </div>
            <div class="form-group">
                <label>Version</label>
                <div>${escapeHtml(manifest.version)}</div>
            </div>
            <div class="form-group">
                <label>Author</label>
                <div>${escapeHtml(manifest.author || 'Unknown')}</div>
            </div>
            <div class="form-group">
                <label>Description</label>
                <div>${escapeHtml(manifest.description || 'No description')}</div>
            </div>
            <div class="form-group">
                <label>Type</label>
                <div>${escapeHtml(manifest.plugin_type)}</div>
            </div>
            <div class="form-group">
                <label>Status</label>
                <div>${escapeHtml(manifest.status)}</div>
            </div>
            <div class="form-group">
                <label>File Path</label>
                <div style="word-break: break-all;">${escapeHtml(manifest.file_path)}</div>
            </div>
        `;

        if (manifest.homepage) {
            detailsHtml += `
                <div class="form-group">
                    <label>Homepage</label>
                    <div><a href="${escapeHtml(manifest.homepage)}" target="_blank">${escapeHtml(manifest.homepage)}</a></div>
                </div>
            `;
        }

        if (manifest.license) {
            detailsHtml += `
                <div class="form-group">
                    <label>License</label>
                    <div>${escapeHtml(manifest.license)}</div>
                </div>
            `;
        }

        if (manifest.supported_languages && manifest.supported_languages.length > 0) {
            detailsHtml += `
                <div class="form-group">
                    <label>Supported Languages</label>
                    <div>${manifest.supported_languages.map(l => escapeHtml(l)).join(', ')}</div>
                </div>
            `;
        }

        if (manifest.hooks && manifest.hooks.length > 0) {
            detailsHtml += `
                <div class="form-group">
                    <label>Registered Hooks</label>
                    <div>${manifest.hooks.join(', ')}</div>
                </div>
            `;
        }

        if (manifest.rules && manifest.rules.length > 0) {
            detailsHtml += `
                <div class="form-group">
                    <label>Analysis Rules</label>
                    <div style="margin-top: 0.5rem;">
                        ${manifest.rules.map(rule => `
                            <div style="background: #f7fafc; padding: 0.75rem; border-radius: 4px; margin-bottom: 0.5rem;">
                                <strong>${escapeHtml(rule.name)}</strong> (${escapeHtml(rule.id)})<br>
                                <small style="color: #718096;">${escapeHtml(rule.description)}</small><br>
                                <small style="color: #718096;">Severity: ${escapeHtml(rule.severity)}, Category: ${escapeHtml(rule.category)}</small>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        }

        detailsHtml += `
            <div class="form-group">
                <label>Statistics</label>
                <div class="plugin-stats">
                    <div class="stat-item">
                        <div class="stat-value">${manifest.load_count || 0}</div>
                        <div class="stat-label">Loads</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">${manifest.execution_count || 0}</div>
                        <div class="stat-label">Executions</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">${manifest.error_count || 0}</div>
                        <div class="stat-label">Errors</div>
                    </div>
                </div>
            </div>
        `;

        contentEl.innerHTML = detailsHtml;
        modal.classList.add('active');
    } catch (error) {
        showAlert('Failed to load plugin details: ' + error.message, 'error');
    }
}

/**
 * Close details modal
 */
function closeDetailsModal() {
    const modal = document.getElementById('plugin-details-modal');
    modal.classList.remove('active');
}

/**
 * Show alert message
 */
function showAlert(message, type = 'success') {
    const container = document.getElementById('alert-container');
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;
    container.appendChild(alert);

    setTimeout(() => {
        alert.remove();
    }, 5000);
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Close modals when clicking outside
document.addEventListener('click', (event) => {
    if (event.target.classList.contains('modal')) {
        event.target.classList.remove('active');
    }
});
