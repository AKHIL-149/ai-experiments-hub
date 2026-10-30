// Runs the real Express app against a fake Ollama over real HTTP (no mocks of fetch).
const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const path = require('node:path');

let fakeOllama, ollamaRequests, ollamaBehavior;
let appServer, base;

function startFakeOllama() {
    return new Promise(resolve => {
        fakeOllama = http.createServer((req, res) => {
            let body = '';
            req.on('data', c => (body += c));
            req.on('end', () => {
                ollamaRequests.push({ url: req.url, method: req.method, body: body ? JSON.parse(body) : null });
                ollamaBehavior(req, res);
            });
        });
        fakeOllama.listen(0, '127.0.0.1', () => resolve(fakeOllama.address().port));
    });
}

const json = (res, status, obj) => {
    res.writeHead(status, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(obj));
};

const okGenerate = (res, extra = {}) => json(res, 200, {
    response: 'hello world', done_reason: 'stop',
    eval_count: 50, eval_duration: 1e9, load_duration: 2e8, ...extra
});

test.before(async () => {
    ollamaRequests = [];
    const port = await startFakeOllama();
    process.env.OLLAMA_API_URL = `http://127.0.0.1:${port}`;
    const { createApp } = require('../src/server');
    await new Promise(resolve => {
        appServer = createApp().listen(0, '127.0.0.1', resolve);
    });
    base = `http://127.0.0.1:${appServer.address().port}`;
});

test.after(() => {
    appServer.close();
    fakeOllama.close();
});

test.beforeEach(() => {
    ollamaRequests = [];
    ollamaBehavior = (req, res) => okGenerate(res);
});

const post = (body, raw) => fetch(`${base}/api/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: raw !== undefined ? raw : JSON.stringify(body)
});

test('generate returns text plus speed metadata', async () => {
    const res = await post({ model: 'llama3.2', prompt: 'hi' });
    assert.equal(res.status, 200);
    const data = await res.json();
    assert.deepEqual(
        { text: data.text, truncated: data.truncated, tokens: data.tokens, tps: data.tokensPerSecond, load: data.loadSeconds },
        { text: 'hello world', truncated: false, tokens: 50, tps: 50, load: 0.2 }
    );
});

test('temperature 0 and small values are sent to Ollama unchanged', async () => {
    await post({ model: 'm', prompt: 'hi', temperature: 0, maxTokens: 1 });
    const sent = ollamaRequests.find(r => r.url === '/api/generate').body;
    assert.equal(sent.options.temperature, 0);
    assert.equal(sent.options.num_predict, 1);
    assert.equal(sent.stream, false);
});

test('defaults apply when temperature/maxTokens are missing, null or empty', async () => {
    for (const extra of [{}, { temperature: null, maxTokens: null }, { temperature: '', maxTokens: '' }]) {
        ollamaRequests = [];
        await post({ model: 'm', prompt: 'hi', ...extra });
        const sent = ollamaRequests[0].body;
        assert.equal(sent.options.temperature, 0.7);
        assert.equal(sent.options.num_predict, 500);
    }
});

test('model names containing colons are passed through intact', async () => {
    await post({ model: 'llama3.2:3b', prompt: 'hi' });
    assert.equal(ollamaRequests[0].body.model, 'llama3.2:3b');
});

test('truncation is reported', async () => {
    ollamaBehavior = (req, res) => okGenerate(res, { done_reason: 'length' });
    const data = await (await post({ model: 'm', prompt: 'hi' })).json();
    assert.equal(data.truncated, true);
});

test('empty model output is returned as empty text, not an error', async () => {
    ollamaBehavior = (req, res) => okGenerate(res, { response: '' });
    const res = await post({ model: 'm', prompt: 'hi' });
    assert.equal(res.status, 200);
    assert.equal((await res.json()).text, '');
});

const invalid = [
    ['missing prompt', { model: 'm' }, 'Prompt is required'],
    ['blank prompt', { model: 'm', prompt: '   ' }, 'Prompt is required'],
    ['non-string prompt', { model: 'm', prompt: 5 }, 'Prompt is required'],
    ['missing model', { prompt: 'hi' }, 'Model is required'],
    ['unsupported backend', { backend: 'openai', model: 'm', prompt: 'hi' }, 'Unsupported backend'],
    ['temperature too high', { model: 'm', prompt: 'hi', temperature: 2.5 }, 'temperature'],
    ['temperature negative', { model: 'm', prompt: 'hi', temperature: -0.1 }, 'temperature'],
    ['temperature NaN', { model: 'm', prompt: 'hi', temperature: 'abc' }, 'temperature'],
    ['maxTokens zero', { model: 'm', prompt: 'hi', maxTokens: 0 }, 'maxTokens'],
    ['maxTokens fractional', { model: 'm', prompt: 'hi', maxTokens: 2.5 }, 'maxTokens'],
    ['maxTokens too large', { model: 'm', prompt: 'hi', maxTokens: 99999 }, 'maxTokens']
];
for (const [name, body, expected] of invalid) {
    test(`400 for ${name}`, async () => {
        const res = await post(body);
        assert.equal(res.status, 400);
        assert.match((await res.json()).error, new RegExp(expected));
        assert.equal(ollamaRequests.length, 0, 'must not reach Ollama');
    });
}

test('malformed JSON gives a JSON 400 without a stack trace', async () => {
    const res = await post(null, 'not json');
    assert.equal(res.status, 400);
    const text = await res.text();
    assert.deepEqual(JSON.parse(text), { error: 'Request body is not valid JSON' });
    assert.ok(!text.includes('node_modules') && !text.includes('/Users/'));
});

test('oversized body gives a JSON 413', async () => {
    const res = await post({ model: 'm', prompt: 'x'.repeat(3 * 1024 * 1024) });
    assert.equal(res.status, 413);
    assert.match((await res.json()).error, /too large/i);
});

test('missing model maps to 404 with a pull hint', async () => {
    ollamaBehavior = (req, res) => json(res, 404, { error: "model 'zz' not found" });
    const res = await post({ model: 'zz', prompt: 'hi' });
    assert.equal(res.status, 404);
    assert.match((await res.json()).error, /ollama pull/);
});

test('other Ollama failures keep the upstream message', async () => {
    ollamaBehavior = (req, res) => json(res, 500, { error: 'out of memory' });
    const res = await post({ model: 'm', prompt: 'hi' });
    assert.equal(res.status, 502);
    assert.match((await res.json()).error, /500.*out of memory/);
});

test('/api/models lists installed models and drops embedding models', async () => {
    ollamaBehavior = (req, res) => json(res, 200, {
        models: [
            { name: 'llama3.2:3b', size: 1, details: { family: 'llama', parameter_size: '3.2B' } },
            { name: 'nomic-embed-text:latest', size: 1, details: { family: 'nomic-bert' } },
            { name: 'qwen3:8b', size: 1, details: { family: 'qwen3', parameter_size: '8B' } }
        ]
    });
    const data = await (await fetch(`${base}/api/models`)).json();
    assert.deepEqual(data.models.map(m => m.name), ['llama3.2:3b', 'qwen3:8b']);
    assert.equal(data.models[0].parameterSize, '3.2B');
});

test('serves the UI regardless of working directory', async () => {
    // Express resolves a relative static root when the app is created, so build a
    // fresh app while the process is somewhere else entirely
    const { createApp } = require('../src/server');
    const cwd = process.cwd();
    process.chdir('/');
    let other;
    try {
        other = createApp();
    } finally {
        process.chdir(cwd);
    }
    const server = await new Promise(resolve => {
        const s = other.listen(0, '127.0.0.1', () => resolve(s));
    });
    try {
        const url = `http://127.0.0.1:${server.address().port}`;
        for (const file of ['/', '/app.js', '/styles.css']) {
            assert.equal((await fetch(url + file)).status, 200, file);
        }
    } finally {
        server.close();
    }
});

test('no CORS headers for foreign origins', async () => {
    const res = await fetch(`${base}/api/models`, { headers: { Origin: 'http://evil.example' } });
    assert.equal(res.headers.get('access-control-allow-origin'), null);
});

test('unreachable Ollama gives a friendly 502 (separate app instance)', async () => {
    const saved = process.env.OLLAMA_API_URL;
    process.env.OLLAMA_API_URL = 'http://127.0.0.1:9';
    try {
        const res = await post({ model: 'm', prompt: 'hi' });
        assert.equal(res.status, 502);
        assert.match((await res.json()).error, /Cannot reach Ollama.*ollama serve/);
    } finally {
        process.env.OLLAMA_API_URL = saved;
    }
});
