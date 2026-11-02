/**
 * Research Assistant Frontend Application
 */

class ResearchApp {
    constructor() {
        this.currentUser = null;
        this.currentResearch = null;
        this.researchList = [];

        this.init();
    }

    async init() {
        // Check if user is already logged in
        const user = await this.checkAuth();

        if (user) {
            this.currentUser = user;
            this.showMainView();
            await this.loadResearchList();
            this.loadDocuments();
        } else {
            this.showAuthView();
        }

        this.setupEventListeners();
    }

    setupEventListeners() {
        // Auth events
        document.getElementById('login-btn').addEventListener('click', () => this.handleLogin());
        document.getElementById('register-btn').addEventListener('click', () => this.handleRegister());
        document.getElementById('guest-login-btn').addEventListener('click', () => this.handleGuestLogin());
        document.getElementById('logout-btn').addEventListener('click', () => this.handleLogout());

        document.getElementById('show-register').addEventListener('click', (e) => {
            e.preventDefault();
            this.showRegisterForm();
        });

        document.getElementById('show-login').addEventListener('click', (e) => {
            e.preventDefault();
            this.showLoginForm();
        });

        // Research events
        document.getElementById('new-research-btn').addEventListener('click', () => this.showNewResearch());
        document.getElementById('new-research-empty-btn').addEventListener('click', () => this.showNewResearch());
        document.getElementById('start-research-btn').addEventListener('click', () => this.handleStartResearch());

        // Document events
        document.getElementById('manage-documents-btn').addEventListener('click', () => this.showDocumentsView());
        document.getElementById('document-upload-btn').addEventListener('click', () => {
            document.getElementById('document-file-input').click();
        });
        document.getElementById('document-file-input').addEventListener('change', (e) => {
            if (e.target.files.length > 0) this.handleDocumentUpload(e.target.files[0]);
        });

        // Download events
        document.getElementById('download-markdown-btn').addEventListener('click', () => this.downloadReport('markdown'));
        document.getElementById('download-html-btn').addEventListener('click', () => this.downloadReport('html'));
        document.getElementById('download-json-btn').addEventListener('click', () => this.downloadReport('json'));

        // Enter key handlers
        document.getElementById('login-password').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.handleLogin();
        });

        document.getElementById('register-password').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.handleRegister();
        });
    }

    // Auth Methods

    async checkAuth() {
        try {
            const response = await fetch('/api/auth/me', {
                credentials: 'include'
            });

            if (response.ok) {
                return await response.json();
            }

            return null;
        } catch (error) {
            console.error('Auth check failed:', error);
            return null;
        }
    }

    async handleLogin() {
        const username = document.getElementById('login-username').value;
        const password = document.getElementById('login-password').value;

        if (!username || !password) {
            this.showError('Please enter username and password');
            return;
        }

        await this.loginWithCredentials(username, password);
    }

    async loginWithCredentials(username, password) {
        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ username, password })
            });

            if (response.ok) {
                const user = await response.json();
                this.currentUser = user;
                this.showMainView();
                await this.loadResearchList();
            } else {
                const error = await response.json();
                this.showError(error.detail || 'Login failed');
            }
        } catch (error) {
            console.error('Login error:', error);
            this.showError('Login failed. Please try again.');
        }
    }

    async handleRegister() {
        const username = document.getElementById('register-username').value;
        const email = document.getElementById('register-email').value;
        const password = document.getElementById('register-password').value;

        if (!username || !email || !password) {
            this.showError('Please fill in all fields');
            return;
        }

        try {
            const response = await fetch('/api/auth/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, email, password })
            });

            if (response.ok) {
                // Auto-login after registration. Was calling handleLogin(),
                // which reads document.getElementById('login-username'/
                // 'login-password') - the LOGIN form's fields, not this
                // (register) form's. Since the user just registered, not
                // logged in, those fields are empty, so handleLogin()
                // always failed with "Please enter username and password"
                // right after a successful registration - the account was
                // created either way, the user just had no way to know
                // that and had to switch to Login and re-type everything.
                await this.loginWithCredentials(username, password);
            } else {
                const error = await response.json();
                this.showError(error.detail || 'Registration failed');
            }
        } catch (error) {
            console.error('Registration error:', error);
            this.showError('Registration failed. Please try again.');
        }
    }

    async handleGuestLogin() {
        try {
            const response = await fetch('/api/auth/guest', {
                method: 'POST',
                credentials: 'include'
            });

            if (response.ok) {
                const user = await response.json();
                this.currentUser = user;
                this.showMainView();
                await this.loadResearchList();
            } else {
                const error = await response.json();
                this.showError(error.detail || 'Could not create guest session');
            }
        } catch (error) {
            console.error('Guest login error:', error);
            this.showError('Guest login failed. Please try again.');
        }
    }

    async handleLogout() {
        try {
            await fetch('/api/auth/logout', {
                method: 'POST',
                credentials: 'include'
            });

            this.currentUser = null;
            this.currentResearch = null;
            this.researchList = [];
            this.showAuthView();
        } catch (error) {
            console.error('Logout error:', error);
        }
    }

    // Research Methods

    async loadResearchList() {
        try {
            const response = await fetch('/api/research?limit=50', {
                credentials: 'include'
            });

            if (response.ok) {
                const data = await response.json();
                this.researchList = data.queries;
                this.renderResearchList();

                if (this.researchList.length === 0) {
                    this.showView('empty-view');
                }
            }
        } catch (error) {
            console.error('Failed to load research list:', error);
        }
    }

    renderResearchList() {
        const container = document.getElementById('research-list');
        container.innerHTML = '';

        this.researchList.forEach(research => {
            const item = document.createElement('div');
            item.className = 'research-item';
            if (this.currentResearch && this.currentResearch.query_id === research.query_id) {
                item.classList.add('active');
            }

            item.innerHTML = `
                <div class="research-item-query">${this.escapeHtml(research.query)}</div>
                <div class="research-item-meta">
                    ${this.escapeHtml(research.status)} • ${this.formatDate(research.created_at)}
                </div>
            `;

            item.addEventListener('click', () => this.loadResearch(research.query_id));
            container.appendChild(item);
        });
    }

    async loadResearch(queryId) {
        this.showLoading(true);

        try {
            const response = await fetch(`/api/research/${queryId}`, {
                credentials: 'include'
            });

            if (response.ok) {
                this.currentResearch = await response.json();
                this.renderResults();
                this.renderResearchList(); // Update active state
            } else {
                alert('Could not open this research.');
            }
        } catch (error) {
            console.error('Failed to load research:', error);
        } finally {
            this.showLoading(false);
        }
    }

    async handleStartResearch() {
        const query = document.getElementById('research-query').value.trim();

        if (!query) {
            alert('Please enter a research question');
            return;
        }

        const request = {
            query: query,
            search_web: document.getElementById('source-web').checked,
            search_arxiv: document.getElementById('source-arxiv').checked,
            search_documents: document.getElementById('source-documents').checked,
            max_sources: this.readMaxSources(),
            citation_style: document.getElementById('citation-style').value,
            request_id: this.newRequestId()
        };

        if (!request.search_web && !request.search_arxiv && !request.search_documents) {
            alert('Choose at least one source to search');
            return;
        }

        // Show progress
        document.getElementById('research-progress').style.display = 'block';
        document.getElementById('start-research-btn').disabled = true;
        this.showProgress({ step: 0, total: 6, message: 'Starting' });
        const stopPolling = this.pollProgress(request.request_id);

        try {
            const response = await fetch('/api/research', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify(request)
            });

            if (response.ok) {
                this.currentResearch = await response.json();
                document.getElementById('research-query').value = '';

                // Reload research list
                await this.loadResearchList();

                // Show results
                this.renderResults();
            } else {
                const error = await response.json();
                alert('Research failed: ' + (error.detail || 'Unknown error'));
            }
        } catch (error) {
            console.error('Research error:', error);
            alert('Research failed. Please try again.');
        } finally {
            stopPolling();
            document.getElementById('research-progress').style.display = 'none';
            document.getElementById('start-research-btn').disabled = false;
        }
    }

    readMaxSources() {
        const value = parseInt(document.getElementById('max-sources').value, 10);
        // An empty or out-of-range box sent null or 500 and failed with a validation error
        return Number.isFinite(value) ? Math.min(50, Math.max(1, value)) : 20;
    }

    newRequestId() {
        if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
        return 'r' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
    }

    /** The bar and the line under it showed "Initializing..." for the whole run: nothing updated them */
    showProgress(progress) {
        const percent = Math.round(((progress.step || 0) / (progress.total || 6)) * 100);
        document.getElementById('progress-fill').style.width = `${percent}%`;
        document.getElementById('progress-status').textContent =
            `Step ${Math.max(progress.step || 0, 1)} of ${progress.total || 6}: ${progress.message || ''}`;
    }

    /** Ask the server how far the run has got, once a second; returns a function that stops it */
    pollProgress(requestId) {
        let stopped = false;
        const tick = async () => {
            if (stopped) return;
            try {
                const response = await fetch(`/api/research/progress/${requestId}`, { credentials: 'include' });
                if (response.ok && !stopped) this.showProgress(await response.json());
            } catch (error) {
                // the next tick tries again
            }
            if (!stopped) setTimeout(tick, 1000);
        };
        setTimeout(tick, 400);
        return () => { stopped = true; };
    }

    renderResults() {
        if (!this.currentResearch) return;

        this.showView('results-view');

        // Header
        document.getElementById('results-query').textContent = this.currentResearch.query;

        // Meta
        const confidence = this.currentResearch.confidence || this.currentResearch.avg_confidence || 0;
        if (confidence && !isNaN(confidence)) {
            document.getElementById('results-confidence').textContent =
                `Confidence: ${(confidence * 100).toFixed(0)}%`;
        } else {
            document.getElementById('results-confidence').textContent = `Confidence: N/A`;
        }

        document.getElementById('results-sources').textContent =
            `${this.currentResearch.sources.length} Sources`;

        if (this.currentResearch.processing_time) {
            document.getElementById('results-time').textContent =
                `${this.currentResearch.processing_time.toFixed(1)}s`;
        }

        // Anything that went wrong without stopping the research (a search that failed, sources set aside)
        let warningsBox = document.getElementById('results-warnings');
        if (!warningsBox) {
            warningsBox = document.createElement('div');
            warningsBox.id = 'results-warnings';
            warningsBox.className = 'results-warnings';
            document.querySelector('.results-meta').after(warningsBox);
        }
        const warnings = [...(this.currentResearch.warnings || [])];
        if (this.currentResearch.status === 'failed') {
            warnings.unshift(this.currentResearch.error_message || 'This research did not finish.');
        }
        warningsBox.innerHTML = warnings.map(w => `<p>⚠ ${this.escapeHtml(w)}</p>`).join('');
        warningsBox.style.display = warnings.length ? 'block' : 'none';

        // Summary (with formatted structure)
        this.renderFormattedSummary(this.currentResearch.summary);

        // Findings
        const findingsContainer = document.getElementById('results-findings');
        findingsContainer.innerHTML = '';

        if (this.currentResearch.findings && this.currentResearch.findings.length > 0) {
            this.currentResearch.findings.forEach(finding => {
                const item = document.createElement('div');
                item.className = 'finding-item';
                const findingText = finding.finding_text || finding.text || 'No text';
                const findingType = finding.finding_type || finding.type || 'unknown';
                const numSources = finding.num_sources || finding.sources || 0;
                const confidence = finding.confidence || 0;

                // Finding text is written by the model from web pages: escaped, or a page could
                // put markup in it that ran in this one
                item.innerHTML = `
                    <div class="finding-text">${this.escapeHtml(findingText)}</div>
                    <div class="finding-meta">
                        <span><strong>Type:</strong> ${this.escapeHtml(findingType)}</span>
                        <span><strong>Confidence:</strong> ${(confidence * 100).toFixed(0)}%</span>
                        <span><strong>Sources:</strong> ${Number(numSources) || 0}</span>
                    </div>
                `;
                findingsContainer.appendChild(item);
            });
        } else {
            findingsContainer.innerHTML = '<p>No findings available.</p>';
        }

        // Sources
        const sourcesContainer = document.getElementById('results-sources-list');
        sourcesContainer.innerHTML = '';

        this.currentResearch.sources.forEach((source, index) => {
            const item = document.createElement('div');
            item.className = 'source-item';
            // Titles and addresses come from web search results. A "javascript:" address is shown as
            // text, not made a link.
            const safeUrl = this.safeUrl(source.url);
            item.innerHTML = `
                <div class="source-title">${index + 1}. ${this.escapeHtml(source.title)}</div>
                ${safeUrl
                    ? `<a href="${this.escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer" class="source-url">${this.escapeHtml(safeUrl)}</a>`
                    : (source.url ? `<span class="source-url">${this.escapeHtml(source.url)}</span>` : '')}
                <span class="source-type">${this.escapeHtml(source.type || source.source_type || 'unknown')}</span>
            `;
            sourcesContainer.appendChild(item);
        });

        // Citations
        const citationsContainer = document.getElementById('results-citations');
        citationsContainer.innerHTML = '';

        if (this.currentResearch.citations && this.currentResearch.citations.length > 0) {
            this.currentResearch.citations.forEach((citation, index) => {
                const item = document.createElement('div');
                item.className = 'citation-item';
                item.textContent = `${index + 1}. ${citation}`;
                citationsContainer.appendChild(item);
            });
        } else {
            citationsContainer.innerHTML = '<p>No citations available.</p>';
        }
    }

    renderFormattedSummary(summaryText) {
        const container = document.getElementById('results-summary');
        if (!summaryText) {
            container.innerHTML = '<p>No summary available.</p>';
            return;
        }

        // Parse summary with markdown-style formatting. Escaped first: the summary is model output
        // built from web pages, and went into innerHTML as it came.
        const formatted = this.escapeHtml(summaryText)
            // Bold headers (lines starting with **)
            .replace(/^\*\*(.+?)\*\*/gm, '<h3>$1</h3>')
            // Bold inline text
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            // Convert source references to styled spans
            .replace(/\(source[s]?:?\s*(\d+(?:,\s*\d+)*)\)/gi, '<span class="source-ref">(Sources: $1)</span>')
            .replace(/\(source[s]?:?\s*(\d+)\)/gi, '<span class="source-ref">(Source: $1)</span>')
            // Paragraphs
            .split('\n\n')
            .map(para => para.trim())
            .filter(para => para.length > 0)
            .map(para => {
                if (para.startsWith('<h3>')) {
                    return para;
                }
                return `<p>${para}</p>`;
            })
            .join('\n');

        container.innerHTML = formatted;
    }

    async downloadReport(format) {
        if (!this.currentResearch) return;

        try {
            const response = await fetch(
                `/api/research/${this.currentResearch.query_id}/download?format=${encodeURIComponent(format)}`,
                { credentials: 'include' }
            );

            if (!response.ok) {
                // A failed download used to do nothing at all
                let detail = 'Download failed.';
                try { detail = (await response.json()).detail || detail; } catch (e) { /* not JSON */ }
                alert(detail);
                return;
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const extensions = { markdown: 'md', html: 'html', json: 'json', pdf: 'pdf', docx: 'docx' };
            a.download = `research_${this.currentResearch.query_id}.${extensions[format] || format}`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } catch (error) {
            console.error('Download failed:', error);
            alert('Download failed. Please try again.');
        }
    }

    /** The report formats the server can really make (PDF needs a system library) */
    async loadExportFormats() {
        const actions = document.querySelector('.results-actions');
        try {
            const response = await fetch('/api/export-formats', { credentials: 'include' });
            if (!response.ok) return;
            const { formats } = await response.json();
            const labels = { pdf: 'Download PDF', docx: 'Download DOCX' };
            ['pdf', 'docx'].forEach(format => {
                if (!formats.includes(format) || document.getElementById(`download-${format}-btn`)) return;
                const button = document.createElement('button');
                button.id = `download-${format}-btn`;
                button.className = 'action-btn';
                button.textContent = labels[format];
                button.addEventListener('click', () => this.downloadReport(format));
                actions.appendChild(button);
            });
        } catch (error) {
            console.error('Could not load export formats:', error);
        }
    }

    // UI Methods

    showAuthView() {
        document.getElementById('auth-view').style.display = 'flex';
        document.getElementById('main-view').style.display = 'none';
        this.showLoginForm();
    }

    showMainView() {
        document.getElementById('auth-view').style.display = 'none';
        document.getElementById('main-view').style.display = 'block';
        const label = this.currentUser.username + (this.currentUser.is_guest ? ' (Guest)' : '');
        document.getElementById('username-display').textContent = label;
        this.showView('empty-view');
        this.loadExportFormats();
    }

    showLoginForm() {
        document.getElementById('login-form').style.display = 'block';
        document.getElementById('register-form').style.display = 'none';
        document.getElementById('auth-error').style.display = 'none';
    }

    showRegisterForm() {
        document.getElementById('login-form').style.display = 'none';
        document.getElementById('register-form').style.display = 'block';
        document.getElementById('auth-error').style.display = 'none';
    }

    showError(message) {
        const errorDiv = document.getElementById('auth-error');
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
    }

    showNewResearch() {
        this.showView('new-research-view');
        this.currentResearch = null;
        this.renderResearchList();
    }

    showView(viewId) {
        const views = ['new-research-view', 'results-view', 'empty-view', 'documents-view'];
        views.forEach(id => {
            document.getElementById(id).style.display = id === viewId ? 'block' : 'none';
        });
    }

    // Document Methods (My Documents / RAG)

    showDocumentsView() {
        this.showView('documents-view');
        this.loadDocuments();
    }

    async loadDocuments() {
        try {
            const response = await fetch('/api/documents', { credentials: 'include' });
            if (!response.ok) throw new Error('Failed to load documents');
            const data = await response.json();
            this.renderDocuments(data.documents);
            this.updateDocumentsHint(data.documents);
        } catch (error) {
            console.error('Failed to load documents:', error);
        }
    }

    updateDocumentsHint(documents) {
        const hint = document.getElementById('source-documents-hint');
        const readyCount = documents.filter(d => d.status === 'ready').length;
        hint.textContent = readyCount > 0 ? `(${readyCount} ready)` : '';
    }

    renderDocuments(documents) {
        const container = document.getElementById('documents-list');

        if (documents.length === 0) {
            container.innerHTML = '<p class="empty-hint">No documents uploaded yet.</p>';
            return;
        }

        container.innerHTML = documents.map(doc => {
            const sizeKb = (doc.file_size_bytes / 1024).toFixed(1);
            let statusLabel = doc.status;
            if (doc.status === 'ready') statusLabel = `ready · ${doc.chunk_count} chunks`;
            if (doc.status === 'failed') statusLabel = `failed${doc.error_message ? ': ' + this.escapeHtml(doc.error_message) : ''}`;

            return `
                <div class="document-item document-status-${doc.status}">
                    <div class="document-info">
                        <span class="document-filename">${this.escapeHtml(doc.filename)}</span>
                        <span class="document-meta">${sizeKb} KB · ${statusLabel} · ${this.formatDate(doc.uploaded_at)}</span>
                    </div>
                    <button class="action-btn document-delete-btn" data-id="${this.escapeHtml(doc.id)}">Delete</button>
                </div>
            `;
        }).join('');

        container.querySelectorAll('.document-delete-btn').forEach(btn => {
            btn.addEventListener('click', () => this.handleDeleteDocument(btn.dataset.id));
        });
    }

    async handleDocumentUpload(file) {
        const statusEl = document.getElementById('document-upload-status');
        statusEl.textContent = `Uploading ${file.name}...`;

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/api/documents', {
                method: 'POST',
                credentials: 'include',
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                statusEl.textContent = `Upload failed: ${data.detail || 'Unknown error'}`;
                return;
            }

            statusEl.textContent = data.status === 'ready'
                ? `${file.name} uploaded and ready to search.`
                : `${file.name} uploaded, but processing failed: ${data.error_message || ''}`;

            await this.loadDocuments();
        } catch (error) {
            statusEl.textContent = `Upload failed: ${error.message}`;
        } finally {
            document.getElementById('document-file-input').value = '';
        }
    }

    async handleDeleteDocument(documentId) {
        if (!confirm('Delete this document? This cannot be undone.')) return;

        try {
            const response = await fetch(`/api/documents/${documentId}`, {
                method: 'DELETE',
                credentials: 'include'
            });
            if (!response.ok) throw new Error('Failed to delete document');
            await this.loadDocuments();
        } catch (error) {
            alert(`Failed to delete document: ${error.message}`);
        }
    }

    /** Text for HTML: also the quotes, so it is safe inside an attribute value too */
    escapeHtml(text) {
        return String(text == null ? '' : text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    /** The address if it is a web address, else null (no "javascript:" or "data:" links) */
    safeUrl(url) {
        if (!url) return null;
        try {
            const parsed = new URL(url, window.location.href);
            return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : null;
        } catch (e) {
            return null;
        }
    }

    showLoading(show) {
        document.getElementById('loading-overlay').style.display = show ? 'flex' : 'none';
    }

    formatDate(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const diff = now - date;
        const hours = Math.floor(diff / (1000 * 60 * 60));
        const days = Math.floor(hours / 24);

        if (hours < 1) return 'Just now';
        if (hours < 24) return `${hours}h ago`;
        if (days < 7) return `${days}d ago`;

        return date.toLocaleDateString();
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new ResearchApp();
});
