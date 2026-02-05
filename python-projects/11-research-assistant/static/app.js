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
        } else {
            this.showAuthView();
        }

        this.setupEventListeners();
    }

    setupEventListeners() {
        // Auth events
        document.getElementById('login-btn').addEventListener('click', () => this.handleLogin());
        document.getElementById('register-btn').addEventListener('click', () => this.handleRegister());
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
                // Auto-login after registration
                await this.handleLogin();
            } else {
                const error = await response.json();
                this.showError(error.detail || 'Registration failed');
            }
        } catch (error) {
            console.error('Registration error:', error);
            this.showError('Registration failed. Please try again.');
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
                <div class="research-item-query">${research.query}</div>
                <div class="research-item-meta">
                    ${research.status} • ${this.formatDate(research.created_at)}
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
            max_sources: parseInt(document.getElementById('max-sources').value),
            citation_style: document.getElementById('citation-style').value
        };

        // Show progress
        document.getElementById('research-progress').style.display = 'block';
        document.getElementById('start-research-btn').disabled = true;

        try {
            const response = await fetch('/api/research', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify(request)
            });

            if (response.ok) {
                this.currentResearch = await response.json();

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
            document.getElementById('research-progress').style.display = 'none';
            document.getElementById('start-research-btn').disabled = false;
            document.getElementById('research-query').value = '';
        }
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

                item.innerHTML = `
                    <div class="finding-text">${findingText}</div>
                    <div class="finding-meta">
                        <span><strong>Type:</strong> ${findingType}</span>
                        <span><strong>Confidence:</strong> ${(confidence * 100).toFixed(0)}%</span>
                        <span><strong>Sources:</strong> ${numSources}</span>
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
            item.innerHTML = `
                <div class="source-title">${index + 1}. ${source.title}</div>
                ${source.url ? `<a href="${source.url}" target="_blank" class="source-url">${source.url}</a>` : ''}
                <span class="source-type">${source.type}</span>
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

        // Parse summary with markdown-style formatting
        const formatted = summaryText
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
                `/api/research/${this.currentResearch.query_id}/download?format=${format}`,
                { credentials: 'include' }
            );

            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `research_${this.currentResearch.query_id}.${format === 'markdown' ? 'md' : format}`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            }
        } catch (error) {
            console.error('Download failed:', error);
            alert('Download failed. Please try again.');
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
        document.getElementById('username-display').textContent = this.currentUser.username;
        this.showView('empty-view');
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
        const views = ['new-research-view', 'results-view', 'empty-view'];
        views.forEach(id => {
            document.getElementById(id).style.display = id === viewId ? 'block' : 'none';
        });
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
