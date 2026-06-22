/**
 * Rule Marketplace JavaScript
 * Handles marketplace browsing, rule details, ratings, and import/export
 */

let currentPage = 0;
const pageSize = 12;
let currentFilters = {
    category: '',
    language: '',
    search: '',
    sort_by: 'popular'
};
let allRules = [];
let currentRuleId = null;
let selectedRating = 0;
let myRules = [];

// Load featured rules and marketplace on page load
document.addEventListener('DOMContentLoaded', () => {
    loadFeaturedRules();
    loadMarketplaceRules();
});

/**
 * Load featured rules
 */
async function loadFeaturedRules() {
    const loading = document.getElementById('featured-loading');
    const container = document.getElementById('featured-container');

    loading.style.display = 'block';
    container.innerHTML = '';

    try {
        const response = await fetch('/api/marketplace/featured?limit=6', {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('Failed to load featured rules');
        }

        const data = await response.json();
        loading.style.display = 'none';

        if (data.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: #718096;">No featured rules yet</p>';
        } else {
            data.forEach(rule => {
                const card = createRuleCard(rule, true);
                container.appendChild(card);
            });
        }
    } catch (error) {
        loading.style.display = 'none';
        showAlert('Failed to load featured rules: ' + error.message, 'error');
    }
}

/**
 * Load marketplace rules with filters
 */
async function loadMarketplaceRules() {
    const loading = document.getElementById('loading');
    const container = document.getElementById('rules-container');
    const emptyState = document.getElementById('empty-state');
    const pagination = document.getElementById('pagination');

    loading.style.display = 'block';
    container.innerHTML = '';
    emptyState.style.display = 'none';
    pagination.style.display = 'none';

    try {
        const params = new URLSearchParams({
            limit: pageSize,
            offset: currentPage * pageSize,
            sort_by: currentFilters.sort_by
        });

        if (currentFilters.category) params.append('category', currentFilters.category);
        if (currentFilters.language) params.append('language', currentFilters.language);
        if (currentFilters.search) params.append('search', currentFilters.search);

        const response = await fetch('/api/marketplace/rules?' + params, {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('Failed to load marketplace rules');
        }

        const data = await response.json();
        allRules = data.rules || [];

        loading.style.display = 'none';

        if (allRules.length === 0) {
            emptyState.style.display = 'block';
        } else {
            allRules.forEach(rule => {
                const card = createRuleCard(rule, false);
                container.appendChild(card);
            });

            // Update pagination
            updatePagination(data);
        }
    } catch (error) {
        loading.style.display = 'none';
        showAlert('Failed to load marketplace rules: ' + error.message, 'error');
    }
}

/**
 * Create a rule card element
 */
function createRuleCard(rule, isFeatured) {
    const card = document.createElement('div');
    card.className = `rule-card ${isFeatured ? 'featured' : ''}`;
    card.onclick = () => viewRuleDetails(rule.id);

    const tags = rule.tags ? rule.tags.split(',') : [];
    const languages = rule.languages ? rule.languages.split(',') : [];

    card.innerHTML = `
        <div class="rule-header">
            <div class="rule-title">
                <h3>${escapeHtml(rule.name)}</h3>
                <div class="rule-author">by ${escapeHtml(rule.original_author || 'Unknown')}</div>
            </div>
            <div class="rule-badges">
                ${isFeatured ? '<span class="badge badge-featured">Featured</span>' : ''}
                <span class="badge severity-${rule.severity}">${escapeHtml(rule.severity)}</span>
            </div>
        </div>

        <div class="rule-description">
            ${escapeHtml(rule.description || 'No description available')}
        </div>

        <div class="rule-meta">
            <div class="rule-meta-item">
                <strong>Category:</strong> ${escapeHtml(rule.category)}
            </div>
            <div class="rule-meta-item">
                <strong>Pattern:</strong> ${escapeHtml(rule.pattern_type)}
            </div>
        </div>

        ${languages.length > 0 ? `
            <div class="rule-tags">
                ${languages.map(lang => `
                    <span class="tag">${escapeHtml(lang.trim())}</span>
                `).join('')}
            </div>
        ` : ''}

        <div class="rating-display">
            <div class="stars">
                ${generateStars(rule.avg_rating || 0)}
            </div>
            <span class="rating-text">${(rule.avg_rating || 0).toFixed(1)} (${rule.rating_count || 0} reviews)</span>
        </div>

        <div class="rule-stats">
            <div class="stat-item">
                <div class="stat-value">${rule.download_count || 0}</div>
                <div class="stat-label">Downloads</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">${rule.fork_count || 0}</div>
                <div class="stat-label">Forks</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">${rule.rating_count || 0}</div>
                <div class="stat-label">Reviews</div>
            </div>
        </div>
    `;

    return card;
}

/**
 * Generate star rating HTML
 */
function generateStars(rating) {
    let starsHtml = '';
    for (let i = 1; i <= 5; i++) {
        if (i <= Math.floor(rating)) {
            starsHtml += '<span class="star">★</span>';
        } else {
            starsHtml += '<span class="star empty">★</span>';
        }
    }
    return starsHtml;
}

/**
 * View rule details
 */
async function viewRuleDetails(ruleId) {
    currentRuleId = ruleId;

    try {
        const response = await fetch(`/api/marketplace/rules?search=&limit=1000`, {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('Failed to load rule details');
        }

        const data = await response.json();
        const rule = data.rules.find(r => r.id === ruleId);

        if (!rule) {
            throw new Error('Rule not found');
        }

        const modal = document.getElementById('rule-details-modal');
        const nameEl = document.getElementById('details-rule-name');
        const contentEl = document.getElementById('rule-details-content');

        nameEl.textContent = rule.name;

        const languages = rule.languages ? rule.languages.split(',') : [];
        const tags = rule.tags ? rule.tags.split(',') : [];

        let detailsHtml = `
            <div class="rating-display">
                <div class="stars">
                    ${generateStars(rule.avg_rating || 0)}
                </div>
                <span class="rating-text">${(rule.avg_rating || 0).toFixed(1)} (${rule.rating_count || 0} reviews)</span>
            </div>

            <div class="form-group">
                <label>Description</label>
                <div>${escapeHtml(rule.description || 'No description')}</div>
            </div>

            <div class="form-group">
                <label>Author</label>
                <div>${escapeHtml(rule.original_author || 'Unknown')}</div>
            </div>

            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem;">
                <div class="form-group">
                    <label>Category</label>
                    <div>${escapeHtml(rule.category)}</div>
                </div>
                <div class="form-group">
                    <label>Severity</label>
                    <div><span class="badge severity-${rule.severity}">${escapeHtml(rule.severity)}</span></div>
                </div>
            </div>

            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem;">
                <div class="form-group">
                    <label>Pattern Type</label>
                    <div>${escapeHtml(rule.pattern_type)}</div>
                </div>
                <div class="form-group">
                    <label>Auto-Fixable</label>
                    <div>${rule.auto_fixable ? 'Yes' : 'No'}</div>
                </div>
            </div>

            ${languages.length > 0 ? `
                <div class="form-group">
                    <label>Supported Languages</label>
                    <div class="rule-tags">
                        ${languages.map(lang => `<span class="tag">${escapeHtml(lang.trim())}</span>`).join('')}
                    </div>
                </div>
            ` : ''}

            ${tags.length > 0 ? `
                <div class="form-group">
                    <label>Tags</label>
                    <div class="rule-tags">
                        ${tags.map(tag => `<span class="tag">${escapeHtml(tag.trim())}</span>`).join('')}
                    </div>
                </div>
            ` : ''}

            <div class="form-group">
                <label>Message</label>
                <div>${escapeHtml(rule.message)}</div>
            </div>

            ${rule.fix_suggestion ? `
                <div class="form-group">
                    <label>Fix Suggestion</label>
                    <div>${escapeHtml(rule.fix_suggestion)}</div>
                </div>
            ` : ''}

            <div class="rule-stats">
                <div class="stat-item">
                    <div class="stat-value">${rule.download_count || 0}</div>
                    <div class="stat-label">Downloads</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${rule.fork_count || 0}</div>
                    <div class="stat-label">Forks</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${rule.rating_count || 0}</div>
                    <div class="stat-label">Reviews</div>
                </div>
            </div>
        `;

        // Load recent reviews
        const reviewsResponse = await fetch(`/api/marketplace/rules/${ruleId}/ratings?limit=5`, {
            credentials: 'include'
        });

        if (reviewsResponse.ok) {
            const reviewsData = await reviewsResponse.json();
            if (reviewsData.ratings && reviewsData.ratings.length > 0) {
                detailsHtml += `
                    <div class="form-group">
                        <label>Recent Reviews</label>
                        <div>
                            ${reviewsData.ratings.map(review => `
                                <div class="review-item">
                                    <div class="review-header">
                                        <div class="review-author">${escapeHtml(review.username)}</div>
                                        <div class="stars">${generateStars(review.rating)}</div>
                                    </div>
                                    ${review.review ? `<div class="review-text">${escapeHtml(review.review)}</div>` : ''}
                                    <div class="review-date">${formatDate(review.created_at)}</div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            }
        }

        contentEl.innerHTML = detailsHtml;
        modal.classList.add('active');
    } catch (error) {
        showAlert('Failed to load rule details: ' + error.message, 'error');
    }
}

/**
 * Fork current rule
 */
async function forkCurrentRule() {
    if (!currentRuleId) return;

    if (!confirm('Fork this rule to your collection?')) {
        return;
    }

    try {
        const response = await fetch(`/api/marketplace/rules/${currentRuleId}/fork`, {
            method: 'POST',
            credentials: 'include'
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || data.error || 'Failed to fork rule');
        }

        showAlert('Rule forked successfully!', 'success');
        closeDetailsModal();
        loadMarketplaceRules(); // Refresh to update fork count
    } catch (error) {
        showAlert('Failed to fork rule: ' + error.message, 'error');
    }
}

/**
 * Show rate modal
 */
function showRateModal() {
    selectedRating = 0;
    document.getElementById('rating-value').value = '';
    document.getElementById('review-text').value = '';
    updateRatingStars();

    closeDetailsModal();
    const modal = document.getElementById('rate-modal');
    modal.classList.add('active');
}

/**
 * Close rate modal
 */
function closeRateModal() {
    const modal = document.getElementById('rate-modal');
    modal.classList.remove('active');
}

/**
 * Select rating
 */
function selectRating(rating) {
    selectedRating = rating;
    document.getElementById('rating-value').value = rating;
    updateRatingStars();
}

/**
 * Update rating stars display
 */
function updateRatingStars() {
    const stars = document.querySelectorAll('#rating-input .star');
    stars.forEach((star, index) => {
        if (index < selectedRating) {
            star.classList.remove('empty');
        } else {
            star.classList.add('empty');
        }
    });
}

/**
 * Submit rating
 */
async function submitRating(event) {
    event.preventDefault();

    if (!currentRuleId || selectedRating === 0) {
        showAlert('Please select a rating', 'error');
        return;
    }

    const review = document.getElementById('review-text').value;

    try {
        const response = await fetch(`/api/marketplace/rules/${currentRuleId}/rate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({
                rating: selectedRating,
                review: review || null
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to submit rating');
        }

        showAlert('Rating submitted successfully!', 'success');
        closeRateModal();
        loadMarketplaceRules(); // Refresh to update ratings
    } catch (error) {
        showAlert('Failed to submit rating: ' + error.message, 'error');
    }
}

/**
 * Close details modal
 */
function closeDetailsModal() {
    const modal = document.getElementById('rule-details-modal');
    modal.classList.remove('active');
    currentRuleId = null;
}

/**
 * Apply filters
 */
function applyFilters() {
    currentFilters.category = document.getElementById('filter-category').value;
    currentFilters.language = document.getElementById('filter-language').value;
    currentFilters.search = document.getElementById('filter-search').value;
    currentFilters.sort_by = document.getElementById('filter-sort').value;
    currentPage = 0;
    loadMarketplaceRules();
}

/**
 * Clear filters
 */
function clearFilters() {
    document.getElementById('filter-category').value = '';
    document.getElementById('filter-language').value = '';
    document.getElementById('filter-search').value = '';
    document.getElementById('filter-sort').value = 'popular';
    currentFilters = {
        category: '',
        language: '',
        search: '',
        sort_by: 'popular'
    };
    currentPage = 0;
    loadMarketplaceRules();
}

/**
 * Update pagination controls
 */
function updatePagination(data) {
    const pagination = document.getElementById('pagination');
    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');
    const pageInfo = document.getElementById('page-info');

    if (data.total > pageSize) {
        pagination.style.display = 'flex';
        pageInfo.textContent = `Page ${currentPage + 1} of ${Math.ceil(data.total / pageSize)}`;

        prevBtn.disabled = currentPage === 0;
        nextBtn.disabled = !data.has_more;
    } else {
        pagination.style.display = 'none';
    }
}

/**
 * Go to previous page
 */
function previousPage() {
    if (currentPage > 0) {
        currentPage--;
        loadMarketplaceRules();
    }
}

/**
 * Go to next page
 */
function nextPage() {
    currentPage++;
    loadMarketplaceRules();
}

/**
 * Show my rules modal
 */
async function showMyRulesModal() {
    try {
        const response = await fetch('/api/rules/custom', {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('Failed to load your rules');
        }

        const data = await response.json();
        myRules = data.rules || [];

        const modal = document.getElementById('my-rules-modal');
        const container = document.getElementById('my-rules-container');

        if (myRules.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: #718096;">No custom rules yet</p>';
        } else {
            let html = '<table style="width: 100%; border-collapse: collapse; margin-top: 1rem;">';
            html += '<thead><tr style="border-bottom: 2px solid #e2e8f0;">';
            html += '<th style="padding: 0.5rem; text-align: left;">Name</th>';
            html += '<th style="padding: 0.5rem; text-align: left;">Category</th>';
            html += '<th style="padding: 0.5rem; text-align: left;">Visibility</th>';
            html += '<th style="padding: 0.5rem; text-align: left;">Actions</th>';
            html += '</tr></thead><tbody>';

            myRules.forEach(rule => {
                html += `<tr style="border-bottom: 1px solid #e2e8f0;">`;
                html += `<td style="padding: 0.5rem;">${escapeHtml(rule.name)}</td>`;
                html += `<td style="padding: 0.5rem;">${escapeHtml(rule.category)}</td>`;
                html += `<td style="padding: 0.5rem;"><span class="badge">${escapeHtml(rule.visibility || 'private')}</span></td>`;
                html += `<td style="padding: 0.5rem;">`;
                if (rule.visibility === 'public') {
                    html += `<button class="btn btn-sm btn-secondary" onclick="unpublishRule('${rule.id}')">Unpublish</button>`;
                } else {
                    html += `<button class="btn btn-sm btn-success" onclick="publishRule('${rule.id}')">Publish</button>`;
                }
                html += `</td></tr>`;
            });

            html += '</tbody></table>';
            container.innerHTML = html;
        }

        modal.classList.add('active');
    } catch (error) {
        showAlert('Failed to load your rules: ' + error.message, 'error');
    }
}

/**
 * Close my rules modal
 */
function closeMyRulesModal() {
    const modal = document.getElementById('my-rules-modal');
    modal.classList.remove('active');
}

/**
 * Publish rule
 */
async function publishRule(ruleId) {
    const tags = prompt('Enter tags (comma-separated, optional):');

    try {
        const response = await fetch(`/api/rules/custom/${ruleId}/publish`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({
                tags: tags ? tags.split(',').map(t => t.trim()) : []
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to publish rule');
        }

        showAlert('Rule published successfully!', 'success');
        closeMyRulesModal();
        loadMarketplaceRules();
        loadFeaturedRules();
    } catch (error) {
        showAlert('Failed to publish rule: ' + error.message, 'error');
    }
}

/**
 * Unpublish rule
 */
async function unpublishRule(ruleId) {
    if (!confirm('Unpublish this rule from the marketplace?')) {
        return;
    }

    try {
        const response = await fetch(`/api/rules/custom/${ruleId}/unpublish`, {
            method: 'POST',
            credentials: 'include'
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to unpublish rule');
        }

        showAlert('Rule unpublished successfully!', 'success');
        closeMyRulesModal();
        loadMarketplaceRules();
        loadFeaturedRules();
    } catch (error) {
        showAlert('Failed to unpublish rule: ' + error.message, 'error');
    }
}

/**
 * Show export modal
 */
async function showExportModal() {
    const modal = document.getElementById('export-modal');
    const list = document.getElementById('export-rules-list');

    if (myRules.length === 0) {
        await showMyRulesModal();
    }

    let html = '<div style="max-height: 400px; overflow-y: auto;">';
    myRules.forEach(rule => {
        html += `
            <div style="padding: 0.5rem; border-bottom: 1px solid #e2e8f0;">
                <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                    <input type="checkbox" class="export-checkbox" value="${rule.id}">
                    <span>${escapeHtml(rule.name)} (${escapeHtml(rule.category)})</span>
                </label>
            </div>
        `;
    });
    html += '</div>';

    list.innerHTML = html;
    modal.classList.add('active');
}

/**
 * Close export modal
 */
function closeExportModal() {
    const modal = document.getElementById('export-modal');
    modal.classList.remove('active');
}

/**
 * Export selected rules
 */
async function exportSelectedRules() {
    const checkboxes = document.querySelectorAll('.export-checkbox:checked');
    const ruleIds = Array.from(checkboxes).map(cb => cb.value);

    if (ruleIds.length === 0) {
        showAlert('Please select at least one rule to export', 'error');
        return;
    }

    try {
        const response = await fetch('/api/rules/export?rule_ids=' + ruleIds.join(','), {
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('Failed to export rules');
        }

        const data = await response.json();

        // Download as JSON file
        const blob = new Blob([JSON.stringify(data.rules, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `rules_export_${new Date().toISOString().split('T')[0]}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        showAlert(`Exported ${data.rules.length} rule(s) successfully!`, 'success');
        closeExportModal();
    } catch (error) {
        showAlert('Failed to export rules: ' + error.message, 'error');
    }
}

/**
 * Show import modal
 */
function showImportModal() {
    const modal = document.getElementById('import-modal');
    modal.classList.add('active');
}

/**
 * Close import modal
 */
function closeImportModal() {
    const modal = document.getElementById('import-modal');
    modal.classList.remove('active');
    document.getElementById('import-form').reset();
}

/**
 * Import rules
 */
async function importRules(event) {
    event.preventDefault();

    const fileInput = document.getElementById('import-file');
    const overwrite = document.getElementById('import-overwrite').checked;

    if (!fileInput.files || fileInput.files.length === 0) {
        showAlert('Please select a file', 'error');
        return;
    }

    const file = fileInput.files[0];

    try {
        const text = await file.text();
        const rules = JSON.parse(text);

        if (!Array.isArray(rules)) {
            throw new Error('Invalid file format. Expected an array of rules.');
        }

        const response = await fetch('/api/rules/import', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({
                rules: rules,
                overwrite: overwrite
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to import rules');
        }

        showAlert(`Imported ${data.imported_count} rule(s) successfully!`, 'success');
        closeImportModal();
        closeMyRulesModal();
    } catch (error) {
        showAlert('Failed to import rules: ' + error.message, 'error');
    }
}

/**
 * Format date
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
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
