const express = require('express');
const cors = require('cors');
const path = require('path');
require('dotenv').config();

const PUBLIC_DIR = path.join(__dirname, '../public');

const LIMITS = {
    temperature: { min: 0, max: 2, default: 0.7 },
    maxTokens: { min: 1, max: 8192, default: 500 }
};

function ollamaUrl() {
    return process.env.OLLAMA_API_URL || 'http://localhost:11434';
}

class HttpError extends Error {
    constructor(status, message) {
        super(message);
        this.status = status;
    }
}

function createApp() {
    const app = express();

    // The playground is a local tool: only allow same-origin pages by default
    app.use(cors({ origin: process.env.CORS_ORIGIN || false }));
    app.use(express.json({ limit: '2mb' }));
    app.use(express.static(PUBLIC_DIR));

    app.get('/', (req, res) => {
        res.sendFile(path.join(PUBLIC_DIR, 'index.html'));
    });

    // Models installed in Ollama, so the dropdowns never go stale
    app.get('/api/models', async (req, res) => {
        try {
            const response = await fetchOllama('/api/tags', { method: 'GET' }, 5000);
            const data = await response.json();
            const models = (data.models || [])
                // embedding models cannot generate text
                .filter(m => !/bert/i.test(m.details?.family || '') && !/embed/i.test(m.name))
                .map(m => ({
                    name: m.name,
                    parameterSize: m.details?.parameter_size || null,
                    sizeBytes: m.size || null
                }));
            res.json({ models });
        } catch (error) {
            res.status(502).json({ error: error.message, models: [] });
        }
    });

    app.post('/api/generate', async (req, res, next) => {
        try {
            const params = validateGenerateRequest(req.body);
            const result = await generateOllama(params);
            res.json(result);
        } catch (error) {
            next(error);
        }
    });

    // JSON errors only: no HTML pages, no stack traces or file paths
    app.use((error, req, res, next) => {
        let status = error.status || 500;
        let message = error.message;

        if (error.type === 'entity.too.large') {
            status = 413;
            message = 'Request too large (limit 2 MB)';
        } else if (error.type === 'entity.parse.failed') {
            status = 400;
            message = 'Request body is not valid JSON';
        }

        if (status >= 500) {
            console.error('Generation error:', error.message);
        }
        res.status(status).json({ error: message });
    });

    return app;
}

function validateGenerateRequest(body) {
    const { backend = 'ollama', model, prompt, temperature, maxTokens } = body || {};

    if (backend !== 'ollama') {
        throw new HttpError(400, `Unsupported backend: ${backend}`);
    }
    if (typeof prompt !== 'string' || !prompt.trim()) {
        throw new HttpError(400, 'Prompt is required');
    }
    if (typeof model !== 'string' || !model.trim()) {
        throw new HttpError(400, 'Model is required');
    }

    return {
        model: model.trim(),
        prompt,
        temperature: numberInRange('temperature', temperature, LIMITS.temperature, false),
        maxTokens: numberInRange('maxTokens', maxTokens, LIMITS.maxTokens, true)
    };
}

// Missing/null means "use the default". 0 is a real value (e.g. temperature 0).
function numberInRange(name, value, limits, integer) {
    if (value === undefined || value === null || value === '') {
        return limits.default;
    }
    const n = Number(value);
    if (!Number.isFinite(n) || (integer && !Number.isInteger(n)) || n < limits.min || n > limits.max) {
        throw new HttpError(
            400,
            `${name} must be ${integer ? 'a whole number' : 'a number'} between ${limits.min} and ${limits.max}`
        );
    }
    return n;
}

async function fetchOllama(pathname, options, timeoutMs) {
    const url = `${ollamaUrl()}${pathname}`;
    let response;
    try {
        response = await fetch(url, { ...options, signal: AbortSignal.timeout(timeoutMs) });
    } catch (error) {
        if (error.name === 'TimeoutError') {
            throw new HttpError(504, `Ollama did not respond within ${Math.round(timeoutMs / 1000)}s`);
        }
        throw new HttpError(
            502,
            `Cannot reach Ollama at ${ollamaUrl()}. Is it running? Start it with: ollama serve`
        );
    }

    if (!response.ok) {
        let detail = response.statusText;
        try {
            const body = await response.json();
            detail = body.error || detail;
        } catch (e) {
            // keep statusText
        }
        throw new HttpError(
            response.status === 404 ? 404 : 502,
            response.status === 404 && /not found/i.test(detail)
                ? `${detail}. Install it with: ollama pull <model>`
                : `Ollama error (${response.status}): ${detail}`
        );
    }
    return response;
}

async function generateOllama({ model, prompt, temperature, maxTokens }) {
    const timeoutMs = (parseInt(process.env.OLLAMA_TIMEOUT, 10) || 300) * 1000;

    const response = await fetchOllama('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            model,
            prompt,
            stream: false,
            options: { temperature, num_predict: maxTokens }
        })
    }, timeoutMs);

    const data = await response.json();
    const evalSeconds = (data.eval_duration || 0) / 1e9;

    return {
        text: data.response || '',
        model,
        truncated: data.done_reason === 'length',
        tokens: data.eval_count ?? null,
        tokensPerSecond: evalSeconds > 0 && data.eval_count ? +(data.eval_count / evalSeconds).toFixed(1) : null,
        loadSeconds: data.load_duration ? +(data.load_duration / 1e9).toFixed(2) : null
    };
}

if (require.main === module) {
    const PORT = process.env.PORT || 3000;
    // Local tool: bind to loopback unless HOST says otherwise
    const HOST = process.env.HOST || '127.0.0.1';
    createApp().listen(PORT, HOST, () => {
        console.log(`Prompt Playground running at http://localhost:${PORT}`);
        console.log(`Make sure Ollama is running at ${ollamaUrl()}`);
    });
}

module.exports = { createApp, validateGenerateRequest };
