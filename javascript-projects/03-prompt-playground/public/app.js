class PromptPlayground {
    constructor() {
        this.savedPrompts = this.loadSavedPrompts();
        this.initializeElements();
        this.attachEventListeners();
        this.renderSavedPrompts();
        this.loadModels();
    }

    // Fill both dropdowns from the models actually installed in Ollama
    async loadModels() {
        const notice = document.getElementById('modelsNotice');
        try {
            const response = await fetch('/api/models');
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not load models');
            if (data.models.length === 0) {
                throw new Error('No models installed. Run: ollama pull llama3.2');
            }

            const options = data.models.map(m => {
                const size = m.parameterSize ? ` (${m.parameterSize})` : '';
                return `<option value="ollama:${this.escapeHtml(m.name)}">${this.escapeHtml(m.name)}${size}</option>`;
            }).join('');

            const preferred = data.models.find(m => m.name.startsWith('llama3.2')) || data.models[0];
            this.model1Select.innerHTML = options;
            this.model1Select.value = `ollama:${preferred.name}`;
            this.model2Select.innerHTML = '<option value="">None (single model)</option>' + options;
            notice.style.display = 'none';
        } catch (error) {
            notice.textContent = `${error.message} (showing default model list)`;
            notice.style.display = 'block';
        }
    }

    // "ollama:llama3.2:3b" -> backend "ollama", model "llama3.2:3b" (only the first colon separates)
    splitModel(modelStr) {
        const index = modelStr.indexOf(':');
        return [modelStr.slice(0, index), modelStr.slice(index + 1)];
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
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
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
        const maxTokens = parseInt(this.maxTokensInput.value, 10);

        if (!Number.isFinite(temperature) || temperature < 0 || temperature > 2) {
            alert('Temperature must be a number between 0 and 2');
            return;
        }
        if (!Number.isInteger(maxTokens) || maxTokens < 1 || maxTokens > 8192) {
            alert('Max tokens must be a whole number between 1 and 8192');
            return;
        }

        this.showLoading();
        this.clearResults();

        try {
            // One at a time: running both at once makes them compete for the same
            // GPU/CPU, which would distort the timings being compared
            await this.generateWithModel(prompt, model1, temperature, maxTokens, 1);
            if (model2) {
                this.setLoadingText('Generating output 2 of 2...');
                await this.generateWithModel(prompt, model2, temperature, maxTokens, 2);
            }
        } catch (error) {
            this.showError(error.message);
        } finally {
            this.hideLoading();
        }
    }

    async generateWithModel(prompt, modelStr, temperature, maxTokens, outputNum) {
        const [backend, model] = this.splitModel(modelStr);
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

        let data;
        try {
            data = await response.json();
        } catch (e) {
            throw new Error(`Server returned an unexpected response (${response.status})`);
        }
        if (!response.ok) {
            throw new Error(data.error || 'Generation failed');
        }
        return data;
    }

    displayResult(outputNum, result, model, elapsed) {
        const modelName = document.getElementById(`modelName${outputNum}`);
        const output = document.getElementById(`output${outputNum}`);
        const meta = document.getElementById(`meta${outputNum}`);
        const text = result.text;

        modelName.textContent = model.replace(':', ' - ');

        if (!text.trim()) {
            output.innerHTML = '<div class="error">The model returned no text. ' +
                (result.truncated
                    ? 'It likely used all its tokens on hidden reasoning; raise Max Tokens.'
                    : 'Try a different prompt or model.') + '</div>';
        } else {
            output.textContent = text;
        }

        const words = text.trim() ? text.trim().split(/\s+/).length : 0;
        const parts = [`<span>Generated in ${elapsed}s</span>`];
        if (result.tokens != null) {
            parts.push(`<span>${result.tokens} tokens</span>`);
        }
        if (result.tokensPerSecond != null) {
            parts.push(`<span>${result.tokensPerSecond} tokens/s</span>`);
        }
        parts.push(`<span>${words} words</span>`, `<span>${text.length} characters</span>`);
        if (result.truncated) {
            parts.push('<span class="truncated">Stopped at the Max Tokens limit</span>');
        }
        meta.innerHTML = parts.join('');
    }

    displayError(outputNum, message) {
        const output = document.getElementById(`output${outputNum}`);
        output.innerHTML = `<div class="error">Error: ${this.escapeHtml(message)}</div>`;
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
        this.setLoadingText('Generating...');
        this.loadingOverlay.style.display = 'flex';
        this.generateBtn.disabled = true;
    }

    setLoadingText(text) {
        this.loadingOverlay.querySelector('p').textContent = text;
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

        if (this.savedPrompts.some(p => p.text === prompt)) {
            alert('This prompt is already saved');
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
        // Storage can be blocked or hold corrupt data; never let that break the whole page
        try {
            const saved = JSON.parse(localStorage.getItem('savedPrompts') || '[]');
            return Array.isArray(saved) ? saved.filter(p => p && typeof p.text === 'string') : [];
        } catch (e) {
            return [];
        }
    }

    saveSavedPrompts() {
        try {
            localStorage.setItem('savedPrompts', JSON.stringify(this.savedPrompts));
        } catch (e) {
            alert('Could not save: browser storage is unavailable');
        }
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
