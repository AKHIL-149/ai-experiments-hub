/**
 * Advanced Filtering & Search Component
 * Multi-criteria filtering with presets and persistence
 */

class AdvancedFilters {
    /**
     * Create a new AdvancedFilters instance
     * @param {string} containerId - Container element ID
     * @param {Object} options - Configuration options
     */
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            throw new Error(`Container element '${containerId}' not found`);
        }

        this.options = {
            onFilterChange: options.onFilterChange || null,
            defaultFilters: options.defaultFilters || {},
            allowPresets: options.allowPresets !== false,
            persistState: options.persistState !== false,
            storageKey: options.storageKey || 'advancedFilters',
            ...options
        };

        this.currentFilters = { ...this.options.defaultFilters };
        this.presets = this.loadPresets();
        this.isInitialized = false;
    }

    /**
     * Initialize the filters UI
     */
    init() {
        if (this.isInitialized) {
            console.warn('AdvancedFilters already initialized');
            return;
        }

        this.render();
        this.attachEventListeners();

        // Load persisted state
        if (this.options.persistState) {
            this.loadPersistedState();
        }

        this.isInitialized = true;
    }

    /**
     * Render the filters UI
     */
    render() {
        this.container.innerHTML = `
            <div class="advanced-filters">
                <!-- Search Bar -->
                <div class="filter-section">
                    <div class="search-bar">
                        <input type="text"
                               id="filter-search"
                               class="search-input"
                               placeholder="Search issues by title, description, or file..."
                               value="${this.currentFilters.search || ''}">
                        <button class="search-clear-btn" id="clear-search" title="Clear search">×</button>
                    </div>
                </div>

                <!-- Filter Controls -->
                <div class="filter-section">
                    <div class="filter-row">
                        <!-- Severity Filter -->
                        <div class="filter-group">
                            <label class="filter-label">Severity</label>
                            <div class="filter-chips" id="severity-filters">
                                <button class="filter-chip ${this.isFilterActive('severity', 'critical') ? 'active' : ''}"
                                        data-filter="severity"
                                        data-value="critical">
                                    <span class="severity-badge severity-critical">Critical</span>
                                </button>
                                <button class="filter-chip ${this.isFilterActive('severity', 'error') ? 'active' : ''}"
                                        data-filter="severity"
                                        data-value="error">
                                    <span class="severity-badge severity-error">Error</span>
                                </button>
                                <button class="filter-chip ${this.isFilterActive('severity', 'warning') ? 'active' : ''}"
                                        data-filter="severity"
                                        data-value="warning">
                                    <span class="severity-badge severity-warning">Warning</span>
                                </button>
                                <button class="filter-chip ${this.isFilterActive('severity', 'info') ? 'active' : ''}"
                                        data-filter="severity"
                                        data-value="info">
                                    <span class="severity-badge severity-info">Info</span>
                                </button>
                            </div>
                        </div>

                        <!-- Category Filter -->
                        <div class="filter-group">
                            <label class="filter-label">Category</label>
                            <div class="filter-chips" id="category-filters">
                                <button class="filter-chip ${this.isFilterActive('category', 'security') ? 'active' : ''}"
                                        data-filter="category"
                                        data-value="security">
                                    🔒 Security
                                </button>
                                <button class="filter-chip ${this.isFilterActive('category', 'smell') ? 'active' : ''}"
                                        data-filter="category"
                                        data-value="smell">
                                    👃 Code Smell
                                </button>
                                <button class="filter-chip ${this.isFilterActive('category', 'complexity') ? 'active' : ''}"
                                        data-filter="category"
                                        data-value="complexity">
                                    🔢 Complexity
                                </button>
                            </div>
                        </div>
                    </div>

                    <!-- Date Range Filter -->
                    <div class="filter-row">
                        <div class="filter-group">
                            <label class="filter-label">Date Range</label>
                            <div class="date-range-inputs">
                                <input type="date"
                                       id="filter-date-from"
                                       class="date-input"
                                       value="${this.currentFilters.dateFrom || ''}">
                                <span class="date-separator">to</span>
                                <input type="date"
                                       id="filter-date-to"
                                       class="date-input"
                                       value="${this.currentFilters.dateTo || ''}">
                            </div>
                        </div>

                        <!-- File Filter -->
                        <div class="filter-group">
                            <label class="filter-label">File Path</label>
                            <input type="text"
                                   id="filter-file-path"
                                   class="filter-input"
                                   placeholder="e.g., src/services/*.py"
                                   value="${this.currentFilters.filePath || ''}">
                        </div>
                    </div>
                </div>

                <!-- Quick Filters -->
                <div class="filter-section">
                    <label class="filter-label">Quick Filters</label>
                    <div class="quick-filters">
                        <button class="quick-filter-btn" data-preset="critical-only">
                            🚨 Critical Only
                        </button>
                        <button class="quick-filter-btn" data-preset="recent">
                            🕐 Recent (24h)
                        </button>
                        <button class="quick-filter-btn" data-preset="security">
                            🔒 Security Issues
                        </button>
                        <button class="quick-filter-btn" data-preset="high-complexity">
                            📊 High Complexity
                        </button>
                    </div>
                </div>

                ${this.options.allowPresets ? this.renderPresetsSection() : ''}

                <!-- Actions -->
                <div class="filter-actions">
                    <button class="btn btn-secondary" id="clear-filters">Clear All Filters</button>
                    <button class="btn btn-primary" id="apply-filters">Apply Filters</button>
                    ${this.options.allowPresets ? '<button class="btn btn-secondary" id="save-preset">Save as Preset</button>' : ''}
                </div>
            </div>
        `;
    }

    /**
     * Render presets section
     */
    renderPresetsSection() {
        const presetButtons = this.presets.map((preset, index) => `
            <div class="preset-item">
                <button class="preset-btn" data-preset-index="${index}">
                    ${preset.name}
                </button>
                <button class="preset-delete-btn" data-preset-index="${index}" title="Delete preset">×</button>
            </div>
        `).join('');

        return `
            <div class="filter-section">
                <label class="filter-label">Saved Presets</label>
                <div class="presets-list" id="presets-list">
                    ${presetButtons || '<p class="no-presets">No saved presets</p>'}
                </div>
            </div>
        `;
    }

    /**
     * Check if a filter is active
     */
    isFilterActive(filterType, value) {
        const currentValue = this.currentFilters[filterType];
        if (Array.isArray(currentValue)) {
            return currentValue.includes(value);
        }
        return currentValue === value;
    }

    /**
     * Attach event listeners
     */
    attachEventListeners() {
        // Search input
        const searchInput = document.getElementById('filter-search');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.currentFilters.search = e.target.value;
                this.debouncedFilterChange();
            });
        }

        // Clear search button
        const clearSearchBtn = document.getElementById('clear-search');
        if (clearSearchBtn) {
            clearSearchBtn.addEventListener('click', () => {
                searchInput.value = '';
                this.currentFilters.search = '';
                this.triggerFilterChange();
            });
        }

        // Filter chips (severity and category)
        document.querySelectorAll('.filter-chip').forEach(chip => {
            chip.addEventListener('click', (e) => {
                const filterType = e.currentTarget.dataset.filter;
                const value = e.currentTarget.dataset.value;
                this.toggleFilter(filterType, value);
                e.currentTarget.classList.toggle('active');
            });
        });

        // Date range inputs
        const dateFromInput = document.getElementById('filter-date-from');
        const dateToInput = document.getElementById('filter-date-to');
        if (dateFromInput) {
            dateFromInput.addEventListener('change', (e) => {
                this.currentFilters.dateFrom = e.target.value;
                this.triggerFilterChange();
            });
        }
        if (dateToInput) {
            dateToInput.addEventListener('change', (e) => {
                this.currentFilters.dateTo = e.target.value;
                this.triggerFilterChange();
            });
        }

        // File path input
        const filePathInput = document.getElementById('filter-file-path');
        if (filePathInput) {
            filePathInput.addEventListener('input', (e) => {
                this.currentFilters.filePath = e.target.value;
                this.debouncedFilterChange();
            });
        }

        // Quick filters
        document.querySelectorAll('.quick-filter-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const presetName = e.currentTarget.dataset.preset;
                this.applyQuickFilter(presetName);
            });
        });

        // Clear filters button
        const clearBtn = document.getElementById('clear-filters');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                this.clearFilters();
            });
        }

        // Apply filters button
        const applyBtn = document.getElementById('apply-filters');
        if (applyBtn) {
            applyBtn.addEventListener('click', () => {
                this.triggerFilterChange();
            });
        }

        // Save preset button
        const savePresetBtn = document.getElementById('save-preset');
        if (savePresetBtn) {
            savePresetBtn.addEventListener('click', () => {
                this.saveCurrentAsPreset();
            });
        }

        // Preset buttons
        document.querySelectorAll('.preset-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const index = parseInt(e.currentTarget.dataset.presetIndex);
                this.applyPreset(index);
            });
        });

        // Delete preset buttons
        document.querySelectorAll('.preset-delete-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const index = parseInt(e.currentTarget.dataset.presetIndex);
                this.deletePreset(index);
            });
        });
    }

    /**
     * Toggle a filter value
     */
    toggleFilter(filterType, value) {
        if (!this.currentFilters[filterType]) {
            this.currentFilters[filterType] = [];
        }

        if (Array.isArray(this.currentFilters[filterType])) {
            const index = this.currentFilters[filterType].indexOf(value);
            if (index > -1) {
                this.currentFilters[filterType].splice(index, 1);
            } else {
                this.currentFilters[filterType].push(value);
            }
        } else {
            this.currentFilters[filterType] = [value];
        }

        this.triggerFilterChange();
    }

    /**
     * Apply quick filter preset
     */
    applyQuickFilter(presetName) {
        const quickFilters = {
            'critical-only': {
                severity: ['critical']
            },
            'recent': {
                dateFrom: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString().split('T')[0]
            },
            'security': {
                category: ['security']
            },
            'high-complexity': {
                category: ['complexity'],
                search: 'complexity'
            }
        };

        const preset = quickFilters[presetName];
        if (preset) {
            this.currentFilters = { ...preset };
            this.render();
            this.attachEventListeners();
            this.triggerFilterChange();
        }
    }

    /**
     * Clear all filters
     */
    clearFilters() {
        this.currentFilters = {};
        this.render();
        this.attachEventListeners();
        this.triggerFilterChange();
    }

    /**
     * Trigger filter change callback
     */
    triggerFilterChange() {
        if (this.options.persistState) {
            this.persistState();
        }

        if (this.options.onFilterChange) {
            this.options.onFilterChange(this.getActiveFilters());
        }
    }

    /**
     * Debounced filter change for inputs
     */
    debouncedFilterChange = this.debounce(() => {
        this.triggerFilterChange();
    }, 300);

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
     * Get active filters
     */
    getActiveFilters() {
        // Clean up empty arrays and null values
        const cleaned = {};
        for (const [key, value] of Object.entries(this.currentFilters)) {
            if (value !== null && value !== undefined && value !== '') {
                if (Array.isArray(value)) {
                    if (value.length > 0) {
                        cleaned[key] = value;
                    }
                } else {
                    cleaned[key] = value;
                }
            }
        }
        return cleaned;
    }

    /**
     * Save current filters as preset
     */
    saveCurrentAsPreset() {
        const name = prompt('Enter preset name:');
        if (!name) return;

        const preset = {
            name: name.trim(),
            filters: { ...this.currentFilters }
        };

        this.presets.push(preset);
        this.savePresets();
        this.render();
        this.attachEventListeners();

        if (window.showNotification) {
            window.showNotification(`Preset "${name}" saved`, 'success');
        }
    }

    /**
     * Apply saved preset
     */
    applyPreset(index) {
        if (index < 0 || index >= this.presets.length) return;

        const preset = this.presets[index];
        this.currentFilters = { ...preset.filters };
        this.render();
        this.attachEventListeners();
        this.triggerFilterChange();

        if (window.showNotification) {
            window.showNotification(`Applied preset "${preset.name}"`, 'info');
        }
    }

    /**
     * Delete preset
     */
    deletePreset(index) {
        if (index < 0 || index >= this.presets.length) return;

        const preset = this.presets[index];
        if (confirm(`Delete preset "${preset.name}"?`)) {
            this.presets.splice(index, 1);
            this.savePresets();
            this.render();
            this.attachEventListeners();

            if (window.showNotification) {
                window.showNotification(`Preset "${preset.name}" deleted`, 'info');
            }
        }
    }

    /**
     * Load presets from localStorage
     */
    loadPresets() {
        try {
            const stored = localStorage.getItem(`${this.options.storageKey}_presets`);
            return stored ? JSON.parse(stored) : [];
        } catch (e) {
            console.error('Error loading presets:', e);
            return [];
        }
    }

    /**
     * Save presets to localStorage
     */
    savePresets() {
        try {
            localStorage.setItem(
                `${this.options.storageKey}_presets`,
                JSON.stringify(this.presets)
            );
        } catch (e) {
            console.error('Error saving presets:', e);
        }
    }

    /**
     * Persist current state to localStorage
     */
    persistState() {
        try {
            localStorage.setItem(
                this.options.storageKey,
                JSON.stringify(this.currentFilters)
            );
        } catch (e) {
            console.error('Error persisting state:', e);
        }
    }

    /**
     * Load persisted state from localStorage
     */
    loadPersistedState() {
        try {
            const stored = localStorage.getItem(this.options.storageKey);
            if (stored) {
                this.currentFilters = JSON.parse(stored);
                this.render();
                this.attachEventListeners();
            }
        } catch (e) {
            console.error('Error loading persisted state:', e);
        }
    }

    /**
     * Reset to default filters
     */
    reset() {
        this.currentFilters = { ...this.options.defaultFilters };
        this.render();
        this.attachEventListeners();
        this.triggerFilterChange();
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { AdvancedFilters };
}
