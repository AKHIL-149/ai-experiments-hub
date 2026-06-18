/**
 * Diff Viewer Component
 * A reusable component for displaying code diffs with syntax highlighting
 * Supports unified and split (side-by-side) views
 */

class DiffViewer {
    /**
     * Create a new DiffViewer instance
     * @param {HTMLElement} container - The container element for the diff viewer
     * @param {Object} options - Configuration options
     */
    constructor(container, options = {}) {
        this.container = container;
        this.options = {
            mode: options.mode || 'unified', // 'unified' or 'split'
            language: options.language || 'python',
            showLineNumbers: options.showLineNumbers !== false,
            syntaxHighlighting: options.syntaxHighlighting !== false,
            allowComments: options.allowComments || false,
            theme: options.theme || 'github-dark',
            ...options
        };

        this.comments = [];
        this.initialized = false;
        this.currentDiff = null;
    }

    /**
     * Initialize the diff viewer
     */
    init() {
        if (this.initialized) return;

        // Create diff viewer structure
        this.container.classList.add('diff-viewer-container');
        this.container.innerHTML = `
            <div class="diff-viewer-header">
                <div class="diff-viewer-tabs">
                    <button class="diff-tab ${this.options.mode === 'unified' ? 'active' : ''}" data-mode="unified">
                        Unified
                    </button>
                    <button class="diff-tab ${this.options.mode === 'split' ? 'active' : ''}" data-mode="split">
                        Split
                    </button>
                </div>
                <div class="diff-viewer-actions">
                    <button class="diff-action-btn" data-action="copy">
                        📋 Copy Diff
                    </button>
                    <button class="diff-action-btn" data-action="download">
                        ⬇️ Download
                    </button>
                </div>
            </div>
            <div class="diff-viewer-content"></div>
        `;

        // Attach event listeners
        this.attachEventListeners();
        this.initialized = true;
    }

    /**
     * Attach event listeners
     */
    attachEventListeners() {
        // Mode switching
        const tabs = this.container.querySelectorAll('.diff-tab');
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const mode = tab.dataset.mode;
                this.switchMode(mode);
            });
        });

        // Actions
        const actionBtns = this.container.querySelectorAll('.diff-action-btn');
        actionBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const action = btn.dataset.action;
                this.handleAction(action);
            });
        });
    }

    /**
     * Load and render a diff
     * @param {Object} diff - Diff data
     */
    loadDiff(diff) {
        if (!this.initialized) {
            this.init();
        }

        this.currentDiff = diff;
        this.render();
    }

    /**
     * Render the diff in the current mode
     */
    render() {
        if (!this.currentDiff) return;

        const content = this.container.querySelector('.diff-viewer-content');

        if (this.options.mode === 'unified') {
            content.innerHTML = this.renderUnified();
        } else {
            content.innerHTML = this.renderSplit();
        }

        // Apply syntax highlighting
        if (this.options.syntaxHighlighting && window.hljs) {
            content.querySelectorAll('code').forEach(block => {
                hljs.highlightElement(block);
            });
        }

        // Attach line comment handlers
        if (this.options.allowComments) {
            this.attachCommentHandlers();
        }
    }

    /**
     * Render unified diff view
     * @returns {string} HTML string
     */
    renderUnified() {
        const changes = this.parseUnifiedDiff(this.currentDiff);

        let html = '<div class="diff-unified">';

        changes.forEach(change => {
            const lineClass = change.type === 'add' ? 'diff-line-added' :
                              change.type === 'remove' ? 'diff-line-removed' :
                              'diff-line-context';

            const lineSymbol = change.type === 'add' ? '+' :
                              change.type === 'remove' ? '-' :
                              ' ';

            html += `
                <div class="diff-line ${lineClass}" data-line="${change.lineNumber}">
                    ${this.options.showLineNumbers ? `<span class="line-number">${change.oldLine || ''}</span>` : ''}
                    ${this.options.showLineNumbers ? `<span class="line-number">${change.newLine || ''}</span>` : ''}
                    <span class="line-symbol">${lineSymbol}</span>
                    <code class="line-content language-${this.options.language}">${this.escapeHtml(change.content)}</code>
                    ${this.options.allowComments ? `<button class="comment-btn" data-line="${change.lineNumber}">💬</button>` : ''}
                </div>
            `;
        });

        html += '</div>';
        return html;
    }

    /**
     * Render split diff view
     * @returns {string} HTML string
     */
    renderSplit() {
        const { original, modified } = this.parseSplitDiff(this.currentDiff);

        let html = '<div class="diff-split">';
        html += '<div class="diff-split-container">';

        // Left side (original)
        html += '<div class="diff-split-pane diff-split-original">';
        html += '<div class="diff-split-header">Original</div>';
        html += '<div class="diff-split-content">';

        original.forEach(line => {
            const lineClass = line.removed ? 'diff-line-removed' : 'diff-line-context';
            html += `
                <div class="diff-line ${lineClass}" data-line="${line.lineNumber}">
                    ${this.options.showLineNumbers ? `<span class="line-number">${line.lineNumber}</span>` : ''}
                    <code class="line-content language-${this.options.language}">${this.escapeHtml(line.content)}</code>
                    ${this.options.allowComments && line.removed ? `<button class="comment-btn" data-line="${line.lineNumber}" data-side="original">💬</button>` : ''}
                </div>
            `;
        });

        html += '</div></div>';

        // Right side (modified)
        html += '<div class="diff-split-pane diff-split-modified">';
        html += '<div class="diff-split-header">Modified</div>';
        html += '<div class="diff-split-content">';

        modified.forEach(line => {
            const lineClass = line.added ? 'diff-line-added' : 'diff-line-context';
            html += `
                <div class="diff-line ${lineClass}" data-line="${line.lineNumber}">
                    ${this.options.showLineNumbers ? `<span class="line-number">${line.lineNumber}</span>` : ''}
                    <code class="line-content language-${this.options.language}">${this.escapeHtml(line.content)}</code>
                    ${this.options.allowComments && line.added ? `<button class="comment-btn" data-line="${line.lineNumber}" data-side="modified">💬</button>` : ''}
                </div>
            `;
        });

        html += '</div></div>';
        html += '</div></div>';

        return html;
    }

    /**
     * Parse unified diff format
     * @param {string} diffText - Raw diff text
     * @returns {Array} Array of change objects
     */
    parseUnifiedDiff(diffText) {
        const lines = diffText.split('\n');
        const changes = [];
        let oldLine = 0;
        let newLine = 0;

        lines.forEach((line, index) => {
            if (line.startsWith('@@')) {
                // Parse hunk header
                const match = line.match(/@@ -(\d+),?\d* \+(\d+),?\d* @@/);
                if (match) {
                    oldLine = parseInt(match[1]);
                    newLine = parseInt(match[2]);
                }
                return;
            }

            if (line.startsWith('---') || line.startsWith('+++')) {
                return; // Skip file headers
            }

            let type = 'context';
            let content = line;

            if (line.startsWith('+')) {
                type = 'add';
                content = line.substring(1);
                changes.push({
                    lineNumber: index,
                    oldLine: null,
                    newLine: newLine++,
                    type,
                    content
                });
            } else if (line.startsWith('-')) {
                type = 'remove';
                content = line.substring(1);
                changes.push({
                    lineNumber: index,
                    oldLine: oldLine++,
                    newLine: null,
                    type,
                    content
                });
            } else {
                content = line.startsWith(' ') ? line.substring(1) : line;
                changes.push({
                    lineNumber: index,
                    oldLine: oldLine++,
                    newLine: newLine++,
                    type,
                    content
                });
            }
        });

        return changes;
    }

    /**
     * Parse diff for split view
     * @param {string} diffText - Raw diff text
     * @returns {Object} Object with original and modified arrays
     */
    parseSplitDiff(diffText) {
        const lines = diffText.split('\n');
        const original = [];
        const modified = [];
        let oldLine = 1;
        let newLine = 1;

        lines.forEach(line => {
            if (line.startsWith('@@') || line.startsWith('---') || line.startsWith('+++')) {
                return;
            }

            if (line.startsWith('+')) {
                modified.push({
                    lineNumber: newLine++,
                    content: line.substring(1),
                    added: true
                });
            } else if (line.startsWith('-')) {
                original.push({
                    lineNumber: oldLine++,
                    content: line.substring(1),
                    removed: true
                });
            } else {
                const content = line.startsWith(' ') ? line.substring(1) : line;
                original.push({
                    lineNumber: oldLine++,
                    content,
                    added: false,
                    removed: false
                });
                modified.push({
                    lineNumber: newLine++,
                    content,
                    added: false,
                    removed: false
                });
            }
        });

        return { original, modified };
    }

    /**
     * Switch diff view mode
     * @param {string} mode - 'unified' or 'split'
     */
    switchMode(mode) {
        if (mode === this.options.mode) return;

        this.options.mode = mode;

        // Update tab states
        const tabs = this.container.querySelectorAll('.diff-tab');
        tabs.forEach(tab => {
            if (tab.dataset.mode === mode) {
                tab.classList.add('active');
            } else {
                tab.classList.remove('active');
            }
        });

        // Re-render
        this.render();
    }

    /**
     * Handle action button clicks
     * @param {string} action - Action name
     */
    handleAction(action) {
        switch (action) {
            case 'copy':
                this.copyDiff();
                break;
            case 'download':
                this.downloadDiff();
                break;
        }
    }

    /**
     * Copy diff to clipboard
     */
    copyDiff() {
        if (!this.currentDiff) return;

        navigator.clipboard.writeText(this.currentDiff).then(() => {
            this.showNotification('Diff copied to clipboard!', 'success');
        }).catch(err => {
            console.error('Failed to copy diff:', err);
            this.showNotification('Failed to copy diff', 'error');
        });
    }

    /**
     * Download diff as a file
     */
    downloadDiff() {
        if (!this.currentDiff) return;

        const blob = new Blob([this.currentDiff], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `diff-${Date.now()}.patch`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        this.showNotification('Diff downloaded!', 'success');
    }

    /**
     * Attach comment button handlers
     */
    attachCommentHandlers() {
        const commentBtns = this.container.querySelectorAll('.comment-btn');
        commentBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const line = btn.dataset.line;
                const side = btn.dataset.side || 'unified';
                this.showCommentInput(line, side);
            });
        });
    }

    /**
     * Show comment input for a line
     * @param {string} line - Line number
     * @param {string} side - 'original', 'modified', or 'unified'
     */
    showCommentInput(line, side) {
        // Create comment input
        const commentForm = document.createElement('div');
        commentForm.className = 'diff-comment-form';
        commentForm.innerHTML = `
            <textarea placeholder="Add a comment..." rows="3"></textarea>
            <div class="comment-actions">
                <button class="btn btn-primary btn-sm" data-action="submit">Comment</button>
                <button class="btn btn-secondary btn-sm" data-action="cancel">Cancel</button>
            </div>
        `;

        // Find the line element
        const lineElement = this.container.querySelector(`.diff-line[data-line="${line}"]${side !== 'unified' ? `[data-side="${side}"]` : ''}`);
        if (!lineElement) return;

        // Insert comment form after the line
        lineElement.insertAdjacentElement('afterend', commentForm);

        // Focus textarea
        const textarea = commentForm.querySelector('textarea');
        textarea.focus();

        // Handle actions
        commentForm.querySelector('[data-action="submit"]').addEventListener('click', () => {
            const text = textarea.value.trim();
            if (text) {
                this.addComment(line, side, text);
                commentForm.remove();
            }
        });

        commentForm.querySelector('[data-action="cancel"]').addEventListener('click', () => {
            commentForm.remove();
        });
    }

    /**
     * Add a comment
     * @param {string} line - Line number
     * @param {string} side - 'original', 'modified', or 'unified'
     * @param {string} text - Comment text
     */
    addComment(line, side, text) {
        const comment = {
            line,
            side,
            text,
            timestamp: new Date().toISOString(),
            author: 'Current User' // Could be dynamic
        };

        this.comments.push(comment);

        // Trigger custom event
        this.container.dispatchEvent(new CustomEvent('comment-added', {
            detail: comment
        }));

        this.showNotification('Comment added!', 'success');
    }

    /**
     * Escape HTML
     * @param {string} text - Text to escape
     * @returns {string} Escaped text
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Show notification
     * @param {string} message - Notification message
     * @param {string} type - Notification type
     */
    showNotification(message, type = 'info') {
        // Use global notification system if available
        if (window.showNotification) {
            window.showNotification(message, type);
        } else {
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DiffViewer;
}
