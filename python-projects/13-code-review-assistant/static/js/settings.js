/**
 * Settings & Configuration Component
 * User preferences and system configuration management
 */

class SettingsManager {
    /**
     * Create a new SettingsManager instance
     * @param {Object} options - Configuration options
     */
    constructor(options = {}) {
        this.options = {
            onSave: options.onSave || null,
            autoSave: options.autoSave !== false,
            storageKey: options.storageKey || 'userSettings',
            ...options
        };

        this.settings = this.loadSettings();
        this.isInitialized = false;
        this.hasUnsavedChanges = false;
    }

    /**
     * Initialize the settings manager
     */
    init() {
        if (this.isInitialized) {
            console.warn('SettingsManager already initialized');
            return;
        }

        this.renderSettings();
        this.attachEventListeners();
        this.updateUI();

        this.isInitialized = true;
    }

    /**
     * Load settings from localStorage and API
     */
    loadSettings() {
        // Default settings
        const defaults = {
            // Analysis Rules
            rules: {
                security: {
                    sqlInjection: true,
                    commandInjection: true,
                    hardcodedSecrets: true,
                    pathTraversal: true,
                    unsafeDeserialization: true,
                    weakCrypto: true
                },
                smell: {
                    longMethods: true,
                    longParameters: true,
                    godClasses: true,
                    deepNesting: true,
                    magicNumbers: true,
                    duplicateCode: true
                },
                complexity: {
                    cyclomaticComplexity: true,
                    cognitiveComplexity: true,
                    nestingDepth: true
                }
            },

            // Thresholds
            thresholds: {
                complexityWarn: 10,
                complexityError: 15,
                methodLengthWarn: 50,
                methodLengthError: 100,
                parameterCountWarn: 5,
                parameterCountError: 8,
                nestingDepthWarn: 3,
                nestingDepthError: 5,
                classMethodsWarn: 15,
                classMethodsError: 25,
                fileLinesWarn: 500,
                fileLinesError: 1000
            },

            // AI Configuration
            ai: {
                provider: 'ollama', // 'ollama', 'anthropic', 'openai'
                ollamaModel: 'llama3.2',
                anthropicModel: 'claude-sonnet-4-5-20250929',
                openaiModel: 'gpt-4',
                enableExplanations: true,
                enableRefactoring: true,
                autoApplyFixes: false,
                confidenceThreshold: 0.8
            },

            // UI Preferences
            ui: {
                theme: 'auto', // 'light', 'dark', 'auto'
                notifications: true,
                toastDuration: 3000,
                defaultDiffView: 'unified', // 'unified' or 'split'
                issuesPerPage: 50,
                autoRefresh: false,
                refreshInterval: 30 // seconds
            },

            // GitHub Integration
            github: {
                autoPostReviews: false,
                commentOnIssues: true,
                minSeverityToPost: 'error', // 'info', 'warning', 'error', 'critical'
                includeRefactorings: true
            }
        };

        try {
            // Load from localStorage
            const stored = localStorage.getItem(this.options.storageKey);
            if (stored) {
                return this.mergeSettings(defaults, JSON.parse(stored));
            }
        } catch (e) {
            console.error('Error loading settings:', e);
        }

        return defaults;
    }

    /**
     * Merge stored settings with defaults
     */
    mergeSettings(defaults, stored) {
        const merged = { ...defaults };

        for (const [key, value] of Object.entries(stored)) {
            if (typeof value === 'object' && !Array.isArray(value)) {
                merged[key] = { ...defaults[key], ...value };
            } else {
                merged[key] = value;
            }
        }

        return merged;
    }

    /**
     * Render settings UI
     */
    renderSettings() {
        const container = document.getElementById('settings-container');
        if (!container) return;

        container.innerHTML = `
            <div class="settings-content">
                <!-- Analysis Rules Section -->
                <div class="settings-section">
                    <h2 class="settings-section-title">📋 Analysis Rules</h2>
                    <p class="settings-section-description">Enable or disable specific analysis rules</p>

                    ${this.renderRulesCategory('Security Rules', 'security', this.settings.rules.security)}
                    ${this.renderRulesCategory('Code Smell Rules', 'smell', this.settings.rules.smell)}
                    ${this.renderRulesCategory('Complexity Rules', 'complexity', this.settings.rules.complexity)}
                </div>

                <!-- Thresholds Section -->
                <div class="settings-section">
                    <h2 class="settings-section-title">⚙️ Thresholds</h2>
                    <p class="settings-section-description">Adjust warning and error thresholds</p>

                    <div class="threshold-grid">
                        ${this.renderThreshold('Complexity (Warning)', 'complexityWarn', this.settings.thresholds.complexityWarn, 1, 50)}
                        ${this.renderThreshold('Complexity (Error)', 'complexityError', this.settings.thresholds.complexityError, 1, 50)}
                        ${this.renderThreshold('Method Length (Warning)', 'methodLengthWarn', this.settings.thresholds.methodLengthWarn, 10, 200)}
                        ${this.renderThreshold('Method Length (Error)', 'methodLengthError', this.settings.thresholds.methodLengthError, 10, 200)}
                        ${this.renderThreshold('Parameter Count (Warning)', 'parameterCountWarn', this.settings.thresholds.parameterCountWarn, 1, 15)}
                        ${this.renderThreshold('Parameter Count (Error)', 'parameterCountError', this.settings.thresholds.parameterCountError, 1, 15)}
                    </div>
                </div>

                <!-- AI Configuration Section -->
                <div class="settings-section">
                    <h2 class="settings-section-title">🤖 AI Configuration</h2>
                    <p class="settings-section-description">Configure AI provider and behavior</p>

                    <div class="setting-group">
                        <label class="setting-label">AI Provider</label>
                        <select class="setting-select" data-setting="ai.provider">
                            <option value="ollama" ${this.settings.ai.provider === 'ollama' ? 'selected' : ''}>Ollama (Local)</option>
                            <option value="anthropic" ${this.settings.ai.provider === 'anthropic' ? 'selected' : ''}>Anthropic (Claude)</option>
                            <option value="openai" ${this.settings.ai.provider === 'openai' ? 'selected' : ''}>OpenAI (GPT)</option>
                        </select>
                    </div>

                    <div class="setting-group" id="ollama-model-group" style="display: ${this.settings.ai.provider === 'ollama' ? 'flex' : 'none'}">
                        <label class="setting-label">Ollama Model</label>
                        <input type="text" class="setting-input" data-setting="ai.ollamaModel" value="${this.settings.ai.ollamaModel}">
                    </div>

                    <div class="setting-group" id="anthropic-model-group" style="display: ${this.settings.ai.provider === 'anthropic' ? 'flex' : 'none'}">
                        <label class="setting-label">Anthropic Model</label>
                        <select class="setting-select" data-setting="ai.anthropicModel">
                            <option value="claude-sonnet-4-5-20250929" ${this.settings.ai.anthropicModel === 'claude-sonnet-4-5-20250929' ? 'selected' : ''}>Claude Sonnet 4.5</option>
                            <option value="claude-opus-4-5-20251101" ${this.settings.ai.anthropicModel === 'claude-opus-4-5-20251101' ? 'selected' : ''}>Claude Opus 4.5</option>
                        </select>
                    </div>

                    <div class="toggle-group">
                        ${this.renderToggle('Enable AI Explanations', 'ai.enableExplanations', this.settings.ai.enableExplanations)}
                        ${this.renderToggle('Enable Refactoring Suggestions', 'ai.enableRefactoring', this.settings.ai.enableRefactoring)}
                        ${this.renderToggle('Auto-Apply Fixes (Dangerous!)', 'ai.autoApplyFixes', this.settings.ai.autoApplyFixes)}
                    </div>
                </div>

                <!-- UI Preferences Section -->
                <div class="settings-section">
                    <h2 class="settings-section-title">🎨 UI Preferences</h2>
                    <p class="settings-section-description">Customize the user interface</p>

                    <div class="setting-group">
                        <label class="setting-label">Theme</label>
                        <select class="setting-select" data-setting="ui.theme">
                            <option value="auto" ${this.settings.ui.theme === 'auto' ? 'selected' : ''}>Auto (System)</option>
                            <option value="light" ${this.settings.ui.theme === 'light' ? 'selected' : ''}>Light</option>
                            <option value="dark" ${this.settings.ui.theme === 'dark' ? 'selected' : ''}>Dark</option>
                        </select>
                    </div>

                    <div class="setting-group">
                        <label class="setting-label">Default Diff View</label>
                        <select class="setting-select" data-setting="ui.defaultDiffView">
                            <option value="unified" ${this.settings.ui.defaultDiffView === 'unified' ? 'selected' : ''}>Unified</option>
                            <option value="split" ${this.settings.ui.defaultDiffView === 'split' ? 'selected' : ''}>Split</option>
                        </select>
                    </div>

                    <div class="toggle-group">
                        ${this.renderToggle('Enable Notifications', 'ui.notifications', this.settings.ui.notifications)}
                        ${this.renderToggle('Auto-Refresh Dashboard', 'ui.autoRefresh', this.settings.ui.autoRefresh)}
                    </div>
                </div>

                <!-- GitHub Integration Section -->
                <div class="settings-section">
                    <h2 class="settings-section-title">🔗 GitHub Integration</h2>
                    <p class="settings-section-description">Configure GitHub PR review settings</p>

                    <div class="setting-group">
                        <label class="setting-label">Minimum Severity to Post</label>
                        <select class="setting-select" data-setting="github.minSeverityToPost">
                            <option value="info" ${this.settings.github.minSeverityToPost === 'info' ? 'selected' : ''}>Info</option>
                            <option value="warning" ${this.settings.github.minSeverityToPost === 'warning' ? 'selected' : ''}>Warning</option>
                            <option value="error" ${this.settings.github.minSeverityToPost === 'error' ? 'selected' : ''}>Error</option>
                            <option value="critical" ${this.settings.github.minSeverityToPost === 'critical' ? 'selected' : ''}>Critical</option>
                        </select>
                    </div>

                    <div class="toggle-group">
                        ${this.renderToggle('Auto-Post Reviews to GitHub', 'github.autoPostReviews', this.settings.github.autoPostReviews)}
                        ${this.renderToggle('Comment on Issues', 'github.commentOnIssues', this.settings.github.commentOnIssues)}
                        ${this.renderToggle('Include Refactoring Suggestions', 'github.includeRefactorings', this.settings.github.includeRefactorings)}
                    </div>
                </div>

                <!-- Actions -->
                <div class="settings-actions">
                    <button class="btn btn-secondary" id="reset-settings">Reset to Defaults</button>
                    <button class="btn btn-secondary" id="export-settings">Export Settings</button>
                    <button class="btn btn-secondary" id="import-settings">Import Settings</button>
                    <button class="btn btn-primary" id="save-settings" ${this.hasUnsavedChanges ? '' : 'disabled'}>
                        Save Changes
                    </button>
                </div>
            </div>
        `;
    }

    /**
     * Render rules category
     */
    renderRulesCategory(title, category, rules) {
        const ruleToggles = Object.entries(rules).map(([key, enabled]) => {
            const displayName = key.replace(/([A-Z])/g, ' $1').trim();
            return this.renderToggle(
                displayName.charAt(0).toUpperCase() + displayName.slice(1),
                `rules.${category}.${key}`,
                enabled
            );
        }).join('');

        return `
            <div class="rules-category">
                <h3 class="rules-category-title">${title}</h3>
                <div class="toggle-group">
                    ${ruleToggles}
                </div>
            </div>
        `;
    }

    /**
     * Render toggle switch
     */
    renderToggle(label, settingPath, value) {
        return `
            <div class="setting-toggle">
                <label class="toggle-label">
                    <span>${label}</span>
                    <div class="toggle-switch">
                        <input type="checkbox"
                               class="toggle-input"
                               data-setting="${settingPath}"
                               ${value ? 'checked' : ''}>
                        <span class="toggle-slider"></span>
                    </div>
                </label>
            </div>
        `;
    }

    /**
     * Render threshold slider
     */
    renderThreshold(label, key, value, min, max) {
        return `
            <div class="threshold-item">
                <label class="threshold-label">
                    ${label}
                    <span class="threshold-value">${value}</span>
                </label>
                <input type="range"
                       class="threshold-slider"
                       data-setting="thresholds.${key}"
                       min="${min}"
                       max="${max}"
                       value="${value}">
            </div>
        `;
    }

    /**
     * Attach event listeners
     */
    attachEventListeners() {
        // Toggle switches
        document.querySelectorAll('.toggle-input').forEach(toggle => {
            toggle.addEventListener('change', (e) => {
                this.updateSetting(e.target.dataset.setting, e.target.checked);
            });
        });

        // Select dropdowns
        document.querySelectorAll('.setting-select').forEach(select => {
            select.addEventListener('change', (e) => {
                this.updateSetting(e.target.dataset.setting, e.target.value);

                // Show/hide model-specific settings
                if (e.target.dataset.setting === 'ai.provider') {
                    this.updateAIProviderUI(e.target.value);
                }
            });
        });

        // Text inputs
        document.querySelectorAll('.setting-input').forEach(input => {
            input.addEventListener('input', (e) => {
                this.updateSetting(e.target.dataset.setting, e.target.value);
            });
        });

        // Threshold sliders
        document.querySelectorAll('.threshold-slider').forEach(slider => {
            slider.addEventListener('input', (e) => {
                this.updateSetting(e.target.dataset.setting, parseInt(e.target.value));
                // Update displayed value
                const valueSpan = e.target.parentElement.querySelector('.threshold-value');
                if (valueSpan) {
                    valueSpan.textContent = e.target.value;
                }
            });
        });

        // Save button
        const saveBtn = document.getElementById('save-settings');
        if (saveBtn) {
            saveBtn.addEventListener('click', () => {
                this.saveSettings();
            });
        }

        // Reset button
        const resetBtn = document.getElementById('reset-settings');
        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                this.resetToDefaults();
            });
        }

        // Export button
        const exportBtn = document.getElementById('export-settings');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => {
                this.exportSettings();
            });
        }

        // Import button
        const importBtn = document.getElementById('import-settings');
        if (importBtn) {
            importBtn.addEventListener('click', () => {
                this.importSettings();
            });
        }
    }

    /**
     * Update AI provider UI visibility
     */
    updateAIProviderUI(provider) {
        document.getElementById('ollama-model-group').style.display = provider === 'ollama' ? 'flex' : 'none';
        document.getElementById('anthropic-model-group').style.display = provider === 'anthropic' ? 'flex' : 'none';
    }

    /**
     * Update a setting value
     */
    updateSetting(path, value) {
        const keys = path.split('.');
        let obj = this.settings;

        for (let i = 0; i < keys.length - 1; i++) {
            obj = obj[keys[i]];
        }

        obj[keys[keys.length - 1]] = value;
        this.hasUnsavedChanges = true;

        // Update save button state
        const saveBtn = document.getElementById('save-settings');
        if (saveBtn) {
            saveBtn.disabled = false;
        }

        // Auto-save if enabled
        if (this.options.autoSave) {
            this.debouncedSave();
        }
    }

    /**
     * Save settings
     */
    async saveSettings() {
        try {
            // Save to localStorage
            localStorage.setItem(this.options.storageKey, JSON.stringify(this.settings));

            // Call API if provided
            if (this.options.onSave) {
                await this.options.onSave(this.settings);
            }

            this.hasUnsavedChanges = false;

            // Update save button
            const saveBtn = document.getElementById('save-settings');
            if (saveBtn) {
                saveBtn.disabled = true;
            }

            if (window.showNotification) {
                window.showNotification('Settings saved successfully', 'success');
            }

            // Apply theme immediately
            this.applyTheme();

        } catch (e) {
            console.error('Error saving settings:', e);
            if (window.showNotification) {
                window.showNotification('Failed to save settings', 'error');
            }
        }
    }

    /**
     * Debounced save for auto-save
     */
    debouncedSave = this.debounce(() => {
        this.saveSettings();
    }, 1000);

    /**
     * Debounce utility
     */
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    /**
     * Reset to default settings
     */
    resetToDefaults() {
        if (!confirm('Reset all settings to defaults? This cannot be undone.')) {
            return;
        }

        localStorage.removeItem(this.options.storageKey);
        this.settings = this.loadSettings();
        this.renderSettings();
        this.attachEventListeners();
        this.saveSettings();

        if (window.showNotification) {
            window.showNotification('Settings reset to defaults', 'info');
        }
    }

    /**
     * Export settings to JSON file
     */
    exportSettings() {
        const dataStr = JSON.stringify(this.settings, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(dataBlob);

        const link = document.createElement('a');
        link.href = url;
        link.download = 'code-review-settings.json';
        link.click();

        URL.revokeObjectURL(url);

        if (window.showNotification) {
            window.showNotification('Settings exported', 'success');
        }
    }

    /**
     * Import settings from JSON file
     */
    importSettings() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'application/json';

        input.onchange = (e) => {
            const file = e.target.files[0];
            if (!file) return;

            const reader = new FileReader();
            reader.onload = (event) => {
                try {
                    const imported = JSON.parse(event.target.result);
                    this.settings = this.mergeSettings(this.loadSettings(), imported);
                    this.renderSettings();
                    this.attachEventListeners();
                    this.saveSettings();

                    if (window.showNotification) {
                        window.showNotification('Settings imported successfully', 'success');
                    }
                } catch (e) {
                    console.error('Error importing settings:', e);
                    if (window.showNotification) {
                        window.showNotification('Invalid settings file', 'error');
                    }
                }
            };

            reader.readAsText(file);
        };

        input.click();
    }

    /**
     * Apply theme
     */
    applyTheme() {
        const theme = this.settings.ui.theme;
        const html = document.documentElement;

        if (theme === 'dark') {
            html.setAttribute('data-theme', 'dark');
        } else if (theme === 'light') {
            html.setAttribute('data-theme', 'light');
        } else {
            html.removeAttribute('data-theme');
        }
    }

    /**
     * Update UI based on current settings
     */
    updateUI() {
        this.applyTheme();
    }

    /**
     * Get current settings
     */
    getSettings() {
        return { ...this.settings };
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { SettingsManager };
}
