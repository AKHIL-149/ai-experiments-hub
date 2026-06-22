/**
 * Rule Builder - Visual Custom Rule Editor
 */

class RuleBuilder {
    constructor() {
        this.currentRule = {};
        this.astPatterns = [];
        this.templates = [];
        this.savedRules = [];
    }

    /**
     * Initialize the rule builder
     */
    init() {
        this.setupEventListeners();
        this.loadDefaultTemplates();
        this.updateJSONPreview();
    }

    /**
     * Set up event listeners
     */
    setupEventListeners() {
        // Pattern type selector
        const patternTypeInputs = document.querySelectorAll('input[name="pattern-type"]');
        patternTypeInputs.forEach(input => {
            input.addEventListener('change', () => this.handlePatternTypeChange());
        });

        // Form inputs - update JSON preview on change
        const formInputs = document.querySelectorAll('.form-input, .form-select');
        formInputs.forEach(input => {
            input.addEventListener('input', () => this.updateJSONPreview());
            input.addEventListener('change', () => this.updateJSONPreview());
        });

        // Regex test input
        document.getElementById('regex-pattern')?.addEventListener('input', () => {
            this.updateJSONPreview();
        });
    }

    /**
     * Handle pattern type change
     */
    handlePatternTypeChange() {
        const selectedType = document.querySelector('input[name="pattern-type"]:checked')?.value;
        const astSection = document.getElementById('ast-pattern-section');
        const regexSection = document.getElementById('regex-pattern-section');

        if (selectedType === 'ast') {
            astSection.style.display = 'block';
            regexSection.style.display = 'none';
        } else if (selectedType === 'regex') {
            astSection.style.display = 'none';
            regexSection.style.display = 'block';
        } else if (selectedType === 'both') {
            astSection.style.display = 'block';
            regexSection.style.display = 'block';
        }
    }

    /**
     * Add AST pattern to the list
     */
    addASTPattern() {
        const nodeType = document.getElementById('ast-node-type').value;
        const attributes = document.getElementById('ast-attributes').value;
        const childPattern = document.getElementById('ast-child-pattern').value;

        if (!nodeType) {
            this.showToast('Please select a node type', 'error');
            return;
        }

        const pattern = {
            id: Date.now(),
            nodeType,
            attributes: attributes ? JSON.parse(attributes) : {},
            childPattern: childPattern || null
        };

        this.astPatterns.push(pattern);
        this.renderASTPatterns();
        this.updateJSONPreview();

        // Clear inputs
        document.getElementById('ast-node-type').value = '';
        document.getElementById('ast-attributes').value = '';
        document.getElementById('ast-child-pattern').value = '';
    }

    /**
     * Remove AST pattern
     */
    removeASTPattern(patternId) {
        this.astPatterns = this.astPatterns.filter(p => p.id !== patternId);
        this.renderASTPatterns();
        this.updateJSONPreview();
    }

    /**
     * Render AST patterns list
     */
    renderASTPatterns() {
        const container = document.getElementById('ast-patterns-list');
        if (this.astPatterns.length === 0) {
            container.innerHTML = '<p class="empty-state"><small>No patterns added yet</small></p>';
            return;
        }

        container.innerHTML = this.astPatterns.map(pattern => `
            <div class="pattern-item">
                <div class="pattern-item-content">
                    <h5>${pattern.nodeType}</h5>
                    ${Object.keys(pattern.attributes).length > 0 ? `
                        <code>${JSON.stringify(pattern.attributes, null, 2)}</code>
                    ` : ''}
                    ${pattern.childPattern ? `
                        <small>Child: ${pattern.childPattern}</small>
                    ` : ''}
                </div>
                <div class="pattern-item-actions">
                    <button class="btn-icon btn-danger" onclick="ruleBuilder.removeASTPattern(${pattern.id})" title="Remove">
                        🗑️
                    </button>
                </div>
            </div>
        `).join('');
    }

    /**
     * Test regex pattern
     */
    testRegex() {
        const pattern = document.getElementById('regex-pattern').value;
        const testInput = document.getElementById('regex-test-input').value;
        const caseInsensitive = document.getElementById('regex-case-insensitive').checked;
        const multiline = document.getElementById('regex-multiline').checked;
        const dotall = document.getElementById('regex-dotall').checked;

        if (!pattern) {
            this.showToast('Please enter a regex pattern', 'error');
            return;
        }

        if (!testInput) {
            this.showToast('Please enter test input', 'error');
            return;
        }

        try {
            let flags = '';
            if (caseInsensitive) flags += 'i';
            if (multiline) flags += 'm';
            if (dotall) flags += 's';

            const regex = new RegExp(pattern, flags + 'g');
            const matches = [...testInput.matchAll(regex)];

            const resultsContainer = document.getElementById('regex-test-results');

            if (matches.length > 0) {
                resultsContainer.className = 'test-results success';
                resultsContainer.innerHTML = `
                    <h4>✅ ${matches.length} match${matches.length > 1 ? 'es' : ''} found</h4>
                    ${matches.map((match, index) => `
                        <div class="test-result-item">
                            <strong>Match ${index + 1}:</strong>
                            <div class="test-result-match">${this.escapeHtml(match[0])}</div>
                            ${match.length > 1 ? `
                                <small>Groups: ${match.slice(1).map(g => this.escapeHtml(g || 'null')).join(', ')}</small>
                            ` : ''}
                        </div>
                    `).join('')}
                `;
            } else {
                resultsContainer.className = 'test-results error';
                resultsContainer.innerHTML = '<h4>❌ No matches found</h4>';
            }
        } catch (error) {
            const resultsContainer = document.getElementById('regex-test-results');
            resultsContainer.className = 'test-results error';
            resultsContainer.innerHTML = `<h4>❌ Invalid regex: ${this.escapeHtml(error.message)}</h4>`;
        }
    }

    /**
     * Test the rule against sample code
     */
    async testRule() {
        const code = document.getElementById('preview-code').value;
        const language = document.getElementById('preview-language').value;

        if (!code) {
            this.showToast('Please enter test code', 'error');
            return;
        }

        const rule = this.buildRuleObject();
        if (!this.validateRule(rule)) {
            return;
        }

        try {
            const response = await fetch('/api/rules/test', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    rule,
                    code,
                    language
                })
            });

            const data = await response.json();
            this.displayTestResults(data);
        } catch (error) {
            this.showToast('Failed to test rule: ' + error.message, 'error');
        }
    }

    /**
     * Display test results
     */
    displayTestResults(data) {
        const container = document.getElementById('test-results-container');

        if (!data.success) {
            container.innerHTML = `
                <div class="result-item no-match">
                    <div class="result-header">
                        <h4>❌ Test Failed</h4>
                    </div>
                    <div class="result-details">${this.escapeHtml(data.error)}</div>
                </div>
            `;
            return;
        }

        const matches = data.matches || [];

        if (matches.length === 0) {
            container.innerHTML = `
                <div class="result-item no-match">
                    <div class="result-header">
                        <h4>No Matches</h4>
                        <span class="result-badge no-match">0 issues</span>
                    </div>
                    <div class="result-details">The rule did not match any patterns in the test code.</div>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="result-item match">
                <div class="result-header">
                    <h4>✅ Rule Matched</h4>
                    <span class="result-badge match">${matches.length} issue${matches.length > 1 ? 's' : ''}</span>
                </div>
                ${matches.map((match, index) => `
                    <div class="result-details">
                        <strong>Match ${index + 1}:</strong> Line ${match.line}
                        <div>${this.escapeHtml(match.message)}</div>
                        ${match.code_snippet ? `
                            <pre><code>${this.escapeHtml(match.code_snippet)}</code></pre>
                        ` : ''}
                    </div>
                `).join('')}
            </div>
        `;
    }

    /**
     * Build rule object from form inputs
     */
    buildRuleObject() {
        const languages = Array.from(document.getElementById('rule-languages').selectedOptions).map(opt => opt.value);
        const patternType = document.querySelector('input[name="pattern-type"]:checked')?.value;

        const rule = {
            id: document.getElementById('rule-id').value,
            name: document.getElementById('rule-name').value,
            description: document.getElementById('rule-description').value,
            category: document.getElementById('rule-category').value,
            severity: document.getElementById('rule-severity').value,
            languages,
            pattern_type: patternType,
            message: document.getElementById('rule-message').value,
            fix_suggestion: document.getElementById('rule-fix-suggestion').value,
            auto_fixable: document.getElementById('rule-auto-fixable').checked
        };

        // Add pattern-specific data
        if (patternType === 'ast' || patternType === 'both') {
            rule.ast_patterns = this.astPatterns;
        }

        if (patternType === 'regex' || patternType === 'both') {
            rule.regex_pattern = {
                pattern: document.getElementById('regex-pattern').value,
                flags: {
                    case_insensitive: document.getElementById('regex-case-insensitive').checked,
                    multiline: document.getElementById('regex-multiline').checked,
                    dotall: document.getElementById('regex-dotall').checked
                }
            };
        }

        return rule;
    }

    /**
     * Validate rule object
     */
    validateRule(rule) {
        const requiredFields = ['id', 'name', 'description', 'category', 'severity', 'message'];

        for (const field of requiredFields) {
            if (!rule[field]) {
                this.showToast(`Please fill in the ${field} field`, 'error');
                return false;
            }
        }

        if (rule.languages.length === 0) {
            this.showToast('Please select at least one target language', 'error');
            return false;
        }

        if (rule.pattern_type === 'ast' && this.astPatterns.length === 0) {
            this.showToast('Please add at least one AST pattern', 'error');
            return false;
        }

        if (rule.pattern_type === 'regex' && !rule.regex_pattern.pattern) {
            this.showToast('Please enter a regex pattern', 'error');
            return false;
        }

        return true;
    }

    /**
     * Update JSON preview
     */
    updateJSONPreview() {
        const rule = this.buildRuleObject();
        const preview = document.getElementById('rule-json-preview');
        const codeElement = preview.querySelector('code');

        codeElement.textContent = JSON.stringify(rule, null, 2);

        // Highlight if hljs is available
        if (typeof hljs !== 'undefined') {
            hljs.highlightElement(codeElement);
        }
    }

    /**
     * Copy rule JSON to clipboard
     */
    async copyRuleJSON() {
        const rule = this.buildRuleObject();
        const json = JSON.stringify(rule, null, 2);

        try {
            await navigator.clipboard.writeText(json);
            this.showToast('Rule JSON copied to clipboard!', 'success');
        } catch (error) {
            this.showToast('Failed to copy: ' + error.message, 'error');
        }
    }

    /**
     * Save rule
     */
    async saveRule() {
        const rule = this.buildRuleObject();

        if (!this.validateRule(rule)) {
            return;
        }

        try {
            const response = await fetch('/api/rules/custom', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(rule)
            });

            const data = await response.json();

            if (data.success) {
                this.showToast('Rule saved successfully!', 'success');
            } else {
                this.showToast('Failed to save rule: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to save rule: ' + error.message, 'error');
        }
    }

    /**
     * Load rule from server
     */
    async loadRule() {
        try {
            const response = await fetch('/api/rules/custom');
            const data = await response.json();

            if (data.success) {
                this.savedRules = data.rules || [];
                this.showLoadModal();
            } else {
                this.showToast('Failed to load rules: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to load rules: ' + error.message, 'error');
        }
    }

    /**
     * Show load rule modal
     */
    showLoadModal() {
        const modal = document.getElementById('load-rule-modal');
        const listContainer = document.getElementById('saved-rules-list');

        if (this.savedRules.length === 0) {
            listContainer.innerHTML = '<p class="empty-state">No saved rules found</p>';
        } else {
            listContainer.innerHTML = this.savedRules.map(rule => `
                <div class="saved-rule-item" onclick="ruleBuilder.selectRule('${rule.id}')">
                    <div class="saved-rule-info">
                        <h4>${this.escapeHtml(rule.name)}</h4>
                        <p>${this.escapeHtml(rule.description)}</p>
                    </div>
                    <div class="saved-rule-actions">
                        <button class="btn-icon btn-danger" onclick="event.stopPropagation(); ruleBuilder.deleteRule('${rule.id}')" title="Delete">
                            🗑️
                        </button>
                    </div>
                </div>
            `).join('');
        }

        modal.classList.add('active');
    }

    /**
     * Close load modal
     */
    closeLoadModal() {
        document.getElementById('load-rule-modal').classList.remove('active');
    }

    /**
     * Select and load a rule
     */
    async selectRule(ruleId) {
        const rule = this.savedRules.find(r => r.id === ruleId);
        if (!rule) return;

        // Populate form with rule data
        document.getElementById('rule-id').value = rule.id;
        document.getElementById('rule-name').value = rule.name;
        document.getElementById('rule-description').value = rule.description;
        document.getElementById('rule-category').value = rule.category;
        document.getElementById('rule-severity').value = rule.severity;
        document.getElementById('rule-message').value = rule.message;
        document.getElementById('rule-fix-suggestion').value = rule.fix_suggestion || '';
        document.getElementById('rule-auto-fixable').checked = rule.auto_fixable || false;

        // Set languages
        const languageSelect = document.getElementById('rule-languages');
        Array.from(languageSelect.options).forEach(option => {
            option.selected = rule.languages.includes(option.value);
        });

        // Set pattern type
        document.querySelector(`input[name="pattern-type"][value="${rule.pattern_type}"]`).checked = true;
        this.handlePatternTypeChange();

        // Load AST patterns
        if (rule.ast_patterns) {
            this.astPatterns = rule.ast_patterns;
            this.renderASTPatterns();
        }

        // Load regex pattern
        if (rule.regex_pattern) {
            document.getElementById('regex-pattern').value = rule.regex_pattern.pattern;
            document.getElementById('regex-case-insensitive').checked = rule.regex_pattern.flags.case_insensitive;
            document.getElementById('regex-multiline').checked = rule.regex_pattern.flags.multiline;
            document.getElementById('regex-dotall').checked = rule.regex_pattern.flags.dotall;
        }

        this.updateJSONPreview();
        this.closeLoadModal();
        this.showToast('Rule loaded successfully!', 'success');
    }

    /**
     * Delete a rule
     */
    async deleteRule(ruleId) {
        if (!confirm('Are you sure you want to delete this rule?')) {
            return;
        }

        try {
            const response = await fetch(`/api/rules/custom/${ruleId}`, {
                method: 'DELETE'
            });

            const data = await response.json();

            if (data.success) {
                this.showToast('Rule deleted successfully!', 'success');
                this.loadRule(); // Refresh the list
            } else {
                this.showToast('Failed to delete rule: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to delete rule: ' + error.message, 'error');
        }
    }

    /**
     * Load default templates
     */
    loadDefaultTemplates() {
        this.templates = [
            {
                id: 'sql-injection',
                name: 'SQL Injection Detection',
                description: 'Detects potential SQL injection vulnerabilities',
                category: 'security',
                severity: 'critical',
                pattern_type: 'regex',
                regex_pattern: '(execute|query)\\s*\\(["\'].*?\\+.*?["\']\\)'
            },
            {
                id: 'hardcoded-secrets',
                name: 'Hardcoded Secrets',
                description: 'Finds hardcoded passwords and API keys',
                category: 'security',
                severity: 'critical',
                pattern_type: 'regex',
                regex_pattern: '(password|api_key|secret)\\s*=\\s*["\'].+["\']'
            },
            {
                id: 'long-function',
                name: 'Long Function',
                description: 'Functions exceeding recommended length',
                category: 'smell',
                severity: 'warning',
                pattern_type: 'ast',
                threshold: 50
            },
            {
                id: 'complex-condition',
                name: 'Complex Conditional',
                description: 'Overly complex if/else conditions',
                category: 'complexity',
                severity: 'warning',
                pattern_type: 'ast'
            }
        ];
    }

    /**
     * Load templates
     */
    loadTemplates() {
        const modal = document.getElementById('templates-modal');
        const grid = document.getElementById('templates-grid');

        grid.innerHTML = this.templates.map(template => `
            <div class="template-card" onclick="ruleBuilder.useTemplate('${template.id}')">
                <h4>${this.escapeHtml(template.name)}</h4>
                <p>${this.escapeHtml(template.description)}</p>
                <div class="template-meta">
                    <span class="badge badge-${template.category}">${template.category}</span>
                    <span class="badge">${template.severity}</span>
                    <span class="badge">${template.pattern_type}</span>
                </div>
            </div>
        `).join('');

        modal.classList.add('active');
    }

    /**
     * Close templates modal
     */
    closeTemplatesModal() {
        document.getElementById('templates-modal').classList.remove('active');
    }

    /**
     * Use a template
     */
    useTemplate(templateId) {
        const template = this.templates.find(t => t.id === templateId);
        if (!template) return;

        document.getElementById('rule-id').value = template.id.toUpperCase();
        document.getElementById('rule-name').value = template.name;
        document.getElementById('rule-description').value = template.description;
        document.getElementById('rule-category').value = template.category;
        document.getElementById('rule-severity').value = template.severity;

        if (template.pattern_type === 'regex' && template.regex_pattern) {
            document.querySelector('input[name="pattern-type"][value="regex"]').checked = true;
            this.handlePatternTypeChange();
            document.getElementById('regex-pattern').value = template.regex_pattern;
        }

        this.updateJSONPreview();
        this.closeTemplatesModal();
        this.showToast('Template loaded! Customize as needed.', 'success');
    }

    /**
     * Update preview language
     */
    updatePreviewLanguage() {
        const language = document.getElementById('preview-language').value;
        const codeTextarea = document.getElementById('preview-code');

        // Set appropriate placeholder based on language
        const placeholders = {
            python: '# Enter Python code here\ndef vulnerable_function(user_input):\n    query = "SELECT * FROM users WHERE id = " + user_input\n    execute(query)',
            javascript: '// Enter JavaScript code here\nfunction vulnerableFunction(userInput) {\n  const query = "SELECT * FROM users WHERE id = " + userInput;\n  execute(query);\n}',
            java: '// Enter Java code here\npublic void vulnerableMethod(String userInput) {\n  String query = "SELECT * FROM users WHERE id = " + userInput;\n  execute(query);\n}',
            go: '// Enter Go code here\nfunc vulnerableFunction(userInput string) {\n  query := "SELECT * FROM users WHERE id = " + userInput\n  execute(query)\n}',
            rust: '// Enter Rust code here\nfn vulnerable_function(user_input: &str) {\n  let query = format!("SELECT * FROM users WHERE id = {}", user_input);\n  execute(&query);\n}'
        };

        codeTextarea.placeholder = placeholders[language] || 'Enter test code here...';
    }

    /**
     * Show toast notification
     */
    showToast(message, type = 'info') {
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            padding: 1rem 1.5rem;
            background: ${type === 'success' ? '#22c55e' : type === 'error' ? '#ef4444' : '#3b82f6'};
            color: white;
            border-radius: 6px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            z-index: 10000;
            animation: slideIn 0.3s ease-out;
        `;

        document.body.appendChild(toast);

        // Remove after 3 seconds
        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease-out';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}
