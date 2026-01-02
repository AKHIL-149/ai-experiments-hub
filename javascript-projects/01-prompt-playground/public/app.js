class PromptPlayground {
    constructor() {
        this.savedPrompts = this.loadSavedPrompts();
        this.initializeElements();
        this.attachEventListeners();
        this.renderSavedPrompts();
    }

    initializeElements() {
        this.promptInput = document.getElementById('prompt');
        this.model1Select = document.getElementById('model1');
        this.model2Select = document.getElementById('model2');
        this.temperatureInput = document.getElementById('temperature');
        this.maxTokensInput = document.getElementById('maxTokens');
        this.generateBtn = document.getElementById('generateBtn');
        this.savePromptBtn = document.getElementById('savePromptBtn');
        this.clearBtn = document.getElementById('clearBtn');
        this.loadingOverlay = document.getElementById('loadingOverlay');
        this.result1Panel = document.getElementById('result1');
        this.result2Panel = document.getElementById('result2');
    }

    attachEventListeners() {
        this.generateBtn.addEventListener('click', () => this.handleGenerate());
        this.savePromptBtn.addEventListener('click', () => this.handleSavePrompt());
        this.clearBtn.addEventListener('click' , () => this.handleClear());
        this.model2Select.addEventListener('change', () => this.toggleResult2Panel());

        this.promptInput.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'Enter') {
                this.handleGenerate();
            }
        });
    }

    toggleResult2Panel() {
        const isComparing = this.model2Select.value !== '';
        this.result2Panel.style.display = isComparing ? 'block' : 'none';
    }

    async handleGenerate() {
        const prompt = this.promptInput.value.trim();
        if (!prompt) {
            alert('Please enter a prompt');
            return;
        }

        const model1 = this.model1Select.value;
        const model2 = this.model2Select.value;
        const temperature = parseFloat(this.temperatureInput.value);
        const maxTokens = parseInt(this.maxTokensInput.value);

        this.showLoading();
        this.clearResults();

        try {
            const promises = [
                this.generateWithModel(prompt, model1, temperature, maxTokens, 1)
            ];

            if (model2) {
                promises.push(
                    this.generateWithModel(prompt, model2, temperature, maxTokens, 2)
                );
            }

            await Promise.all(promises);
        } catch (error) {
            this.showError(error.message);
        } finally {
            this.hideLoading();
        }
    }

    async generateWithModel(prompt, modelStr, temperature, maxTokens, outputNum) {
        const [backend, model] = modelStr.split(':');
        const startTime = Date.now();

        try {
            let result;
            if (backend === 'ollama') {
                result = await this.callOllama(prompt, model, temperature, maxTokens);
            } else {
                throw new Error(`Backend ${backend} not yet implemented`);
            }

            const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);
            this.displayResult(outputNum, result, modelStr, elapsed);
        } catch (error) {
            this.displayError(outputNum, error.message);
        }
    }

    async callOllama(prompt, model, temperature, maxTokens) {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                backend: 'ollama',
                model,
                prompt,
                temperature,
                maxTokens
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Generation failed');
        }

        const data = await response.json();
        return data.text;
    }

    displayResult(outputNum, text, model, elapsed) {
        const modelName = document.getElementById(`modelName${outputNum}`);
        const output = document.getElementById(`output${outputNum}`);
        const meta = document.getElementById(`meta${outputNum}`);

        modelName.textContent = model.replace(':', ' - ');
        output.textContent = text;
        meta.innerHTML = `
            <span>Generated in ${elapsed}s</span>
            <span>${text.split(/\s+/).length} words</span>
            <span>${text.length} characters</span>
        `;
    }

    displayError(outputNum, message) {
        const output = document.getElementById(`output${outputNum}`);
        output.innerHTML = `<div class="error">Error: ${message}</div>`;
    }

    clearResults() {
        for (let i = 1; i <= 2; i++) {
            const output = document.getElementById(`output${i}`);
            const meta = document.getElementById(`meta${i}`);
            output.innerHTML = '<p class="placeholder">Generating...</p>';
            meta.innerHTML = '';
        }
    }

    showError(message) {
        alert(`Error: ${message}`);
    }

    showLoading() {
        this.loadingOverlay.style.display = 'flex';
        this.generateBtn.disabled = true;
    }

    hideLoading() {
        this.loadingOverlay.style.display = 'none';
        this.generateBtn.disabled = false;
    }

    handleSavePrompt() {
        const prompt = this.promptInput.value.trim();
        if (!prompt) {
            alert('Please enter a prompt to save');
            return;
        }

        const savedPrompt = {
            id: Date.now(),
            text: prompt,
            timestamp: new Date().toISOString()
        };

        this.savedPrompts.unshift(savedPrompt);
        this.saveSavedPrompts();
        this.renderSavedPrompts();

        alert('Prompt saved!');
    }

    handleClear() {
        this.promptInput.value = '';
        this.clearResults();
        for (let i = 1; i <= 2; i++) {
            const output = document.getElementById(`output${i}`);
            output.innerHTML = '<p class="placeholder">Results will appear here...</p>';
        }
    }

    loadSavedPrompts() {
        const saved = localStorage.getItem('savedPrompts');
        return saved ? JSON.parse(saved) : [];
    }

    saveSavedPrompts() {
        localStorage.setItem('savedPrompts', JSON.stringify(this.savedPrompts));
    }

    renderSavedPrompts() {
        const container = document.getElementById('savedPromptsList');

        if (this.savedPrompts.length === 0) {
            container.innerHTML = '<p class="placeholder">No saved prompts yet</p>';
            return;
        }

        container.innerHTML = this.savedPrompts.map(prompt => `
            <div class="saved-prompt-item">
                <div class="saved-prompt-content">
                    <div class="saved-prompt-text">${this.escapeHtml(prompt.text)}</div>
                    <div class="saved-prompt-date">${new Date(prompt.timestamp).toLocaleString()}</div>
                </div>
                <div class="saved-prompt-actions">
                    <button class="btn-secondary" onclick="app.loadPrompt(${prompt.id})">Load</button>
                    <button class="btn-delete" onclick="app.deletePrompt(${prompt.id})">Delete</button>
                </div>
            </div>
        `).join('');
    }

    loadPrompt(id) {
        const prompt = this.savedPrompts.find(p => p.id === id);
        if (prompt) {
            this.promptInput.value = prompt.text;
            this.promptInput.focus();
        }
    }

    deletePrompt(id) {
        if (!confirm('Delete this prompt?')) return;

        this.savedPrompts = this.savedPrompts.filter(p => p.id !== id);
        this.saveSavedPrompts();
        this.renderSavedPrompts();
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

const app = new PromptPlayground();
