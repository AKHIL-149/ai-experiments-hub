const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { createApp, buildSystemPrompt } = require('../server');
const AudioProcessor = require('../src/AudioProcessor');
const ConversationManager = require('../src/ConversationManager');
const { tempDir, silenceConsole, ID_A, ID_B } = require('./helpers');

/** A service manager with just enough behaviour for the HTTP layer; records what was asked of it */
class FakeServices {
  constructor(options = {}) {
    this.mode = options.mode || 'local';
    this.cloud = !!options.cloud;
    this.online = options.online !== false;
    this.problem = options.problem || null;
    this.localReply = options.localReply ?? 'AI answer';
    this.cloudReply = options.cloudReply ?? 'cloud answer';
    this.cloudFails = !!options.cloudFails;
    this.llmFails = !!options.llmFails;
    this.ttsFails = !!options.ttsFails;
    this.ttsFormat = options.ttsFormat || 'wav';
    this.transcribeResult = options.transcribeResult || { text: 'hello there', duration: 5 };
    this.transcribeError = options.transcribeError || null;
    this.calls = [];
    this.weatherService = null;
    this.f1Service = null;
  }
  getMode() { return this.mode; }
  setMode(mode) { this.mode = mode; }
  modeProblem() { return this.problem; }
  isCloudAvailable() { return this.cloud; }
  isInternetAvailable() { return this.online; }
  getStatus() { return { mode: this.mode, cloud: { available: this.cloud } }; }
  getAvailableVoices() { return ['en', 'en-gb']; }
  async generateResponse(messages) {
    this.calls.push({ via: 'local', messages });
    if (this.llmFails) throw Object.assign(new Error('The local language model is not available.'), { status: 503 });
    return { response: this.localReply };
  }
  async generateResponseWithTools(messages) {
    this.calls.push({ via: 'cloud', messages });
    if (this.cloudFails) throw new Error('cloud down');
    return { response: this.cloudReply };
  }
  async transcribeAudio() {
    if (this.transcribeError) throw this.transcribeError;
    return this.transcribeResult;
  }
  async synthesizeSpeech(text, options) {
    this.calls.push({ via: 'tts', text, options });
    if (this.ttsFails) throw new Error('espeak missing');
    return { audioBuffer: Buffer.from('RIFFfakewav'), format: this.ttsFormat };
  }
}

async function startServer(serviceOptions = {}, env = {}) {
  const restoreConsole = silenceConsole();
  const dir = tempDir();
  const savedEnv = {};
  for (const [key, value] of Object.entries(env)) {
    savedEnv[key] = process.env[key];
    if (value === undefined) delete process.env[key]; else process.env[key] = value;
  }
  const services = new FakeServices(serviceOptions);
  const conversations = new ConversationManager({ storageDir: path.join(dir, 'conversations') });
  const audio = new AudioProcessor(services, { tempDir: path.join(dir, 'audio'), maxAudioSizeMB: 1 });
  const ctx = createApp({ serviceManager: services, audioProcessor: audio, conversationManager: conversations });
  const server = await new Promise((resolve) => { const s = ctx.app.listen(0, '127.0.0.1', () => resolve(s)); });
  const base = `http://127.0.0.1:${server.address().port}`;

  const request = async (method, url, body, headers = {}) => {
    const init = { method, headers: { ...headers } };
    if (body instanceof FormData) {
      init.body = body;
    } else if (typeof body === 'string') {
      init.body = body;
      init.headers['content-type'] = init.headers['content-type'] || 'application/json';
    } else if (body !== undefined) {
      init.body = JSON.stringify(body);
      init.headers['content-type'] = 'application/json';
    }
    const response = await fetch(base + url, init);
    const text = Buffer.from(await response.arrayBuffer());
    let json = null;
    try { json = JSON.parse(text.toString()); } catch (e) { /* not JSON */ }
    return { status: response.status, json, headers: response.headers, body: text };
  };

  return {
    services, conversations, dir, request, base,
    get: (url) => request('GET', url),
    post: (url, body) => request('POST', url, body),
    del: (url) => request('DELETE', url),
    stop: async () => {
      ctx.stop();
      await new Promise((resolve) => server.close(resolve));
      for (const [key, value] of Object.entries(savedEnv)) {
        if (value === undefined) delete process.env[key]; else process.env[key] = value;
      }
      restoreConsole();
      fs.rmSync(dir, { recursive: true, force: true });
    }
  };
}

function audioForm(content = 'audio bytes', extra = {}) {
  const form = new FormData();
  form.append('audio', new Blob([content]), 'recording.webm');
  for (const [key, value] of Object.entries(extra)) form.append(key, value);
  return form;
}

// ------------------------------------------------------------------ commands

test('POST /api/command: a recognised command is answered without the AI', async () => {
  const s = await startServer();
  try {
    const { status, json } = await s.post('/api/command', { transcript: 'What time is it?' });
    assert.equal(status, 200);
    assert.equal(json.commandRecognized, true);
    assert.match(json.response, /^The current time is /);
    assert.equal(s.services.calls.filter(c => c.via === 'local' || c.via === 'cloud').length, 0);
    assert.equal(json.audioFormat, 'wav');
    assert.equal(Buffer.from(json.audio, 'base64').toString(), 'RIFFfakewav');
  } finally { await s.stop(); }
});

test('POST /api/command: anything else goes to the AI with the date and the conversation so far', async () => {
  const s = await startServer();
  try {
    const { conversationId } = (await s.post('/api/conversations', {})).json;
    await s.post('/api/command', { transcript: 'tell me about volcanoes', conversationId });
    const { json } = await s.post('/api/command', { transcript: 'how hot is lava', conversationId });
    assert.equal(json.commandRecognized, false);
    assert.equal(json.response, 'AI answer');

    const messages = s.services.calls.filter(c => c.via === 'local').pop().messages;
    assert.equal(messages[0].role, 'system');
    assert.match(messages[0].content, /Current date and time:/);
    assert.match(messages[0].content, /do not have internet access/);   // no tools in local mode
    assert.deepEqual(messages.slice(1).map(m => m.content), ['tell me about volcanoes', 'AI answer', 'how hot is lava']);
  } finally { await s.stop(); }
});

test('POST /api/command: local mode never sends anything to the cloud, even with a key configured', async () => {
  const s = await startServer({ mode: 'local', cloud: true });
  try {
    const { json } = await s.post('/api/command', { transcript: 'who painted the mona lisa' });
    assert.equal(json.response, 'AI answer');
    assert.deepEqual(s.services.calls.filter(c => c.via !== 'tts').map(c => c.via), ['local']);
  } finally { await s.stop(); }
});

test('POST /api/command: cloud and hybrid modes use the cloud with tools, and fall back to local if it fails', async () => {
  for (const mode of ['cloud', 'hybrid']) {
    const s = await startServer({ mode, cloud: true });
    try {
      const { json } = await s.post('/api/command', { transcript: 'who painted the mona lisa' });
      assert.equal(json.response, 'cloud answer', mode);
      assert.match(s.services.calls.find(c => c.via === 'cloud').messages[0].content, /use your tools/);
      s.services.cloudFails = true;
      const second = await s.post('/api/command', { transcript: 'and who sculpted david' });
      assert.equal(second.json.response, 'AI answer', `${mode} falls back to local`);
    } finally { await s.stop(); }
  }
});

test('POST /api/command: offline means no cloud attempt', async () => {
  const s = await startServer({ mode: 'hybrid', cloud: true, online: false });
  try {
    const { json } = await s.post('/api/command', { transcript: 'who painted the mona lisa' });
    assert.equal(json.response, 'AI answer');
    assert.equal(s.services.calls.some(c => c.via === 'cloud'), false);
    assert.match(s.services.calls.find(c => c.via === 'local').messages[0].content, /do not have internet access/);
  } finally { await s.stop(); }
});

test('POST /api/command: a command that declines the request hands it to the AI', async () => {
  const s = await startServer();
  try {
    const { json } = await s.post('/api/command', { transcript: 'what is python 3' });
    assert.equal(json.commandRecognized, false);
    assert.equal(json.response, 'AI answer');
  } finally { await s.stop(); }
});

test('POST /api/command: a recognised command that declines the request is answered by the AI instead', async () => {
  const restore = silenceConsole();
  const dir = tempDir();
  const services = new FakeServices();
  const handler = {
    parseCommand: async () => ({ command: 'calculate', handler: 'calculate', parameters: {}, confidence: 0.9, name: 'Calc' }),
    executeCommand: async () => ({ success: false, fallThrough: true, response: '', data: null }),
    listCommands: () => ({})
  };
  const ctx = createApp({
    serviceManager: services, commandHandler: handler,
    audioProcessor: new AudioProcessor(services, { tempDir: path.join(dir, 'audio') }),
    conversationManager: new ConversationManager({ storageDir: path.join(dir, 'conversations') })
  });
  const server = await new Promise((resolve) => { const s = ctx.app.listen(0, '127.0.0.1', () => resolve(s)); });
  try {
    const response = await fetch(`http://127.0.0.1:${server.address().port}/api/command`, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ transcript: 'anything' })
    });
    const json = await response.json();
    assert.equal(response.status, 200);
    assert.equal(json.commandRecognized, false);
    assert.equal(json.response, 'AI answer');
  } finally {
    ctx.stop();
    await new Promise((resolve) => server.close(resolve));
    restore();
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('POST /api/command: a timer set by voice is returned to the page', async () => {
  const s = await startServer();
  try {
    const { json } = await s.post('/api/command', { transcript: 'set a timer for 90 seconds' });
    assert.equal(json.commandRecognized, true);
    assert.equal(json.timer.duration, 90);
    assert.ok(typeof json.timer.id === 'string' && json.timer.endTime > Date.now());
    assert.equal((await s.post('/api/command', { transcript: 'what time is it' })).json.timer, null);
  } finally { await s.stop(); }
});

test('POST /api/command: validation', async () => {
  const s = await startServer();
  try {
    const cases = [
      [{}, 400, /Transcript is required/],
      [{ transcript: '' }, 400, /Transcript is required/],
      [{ transcript: '   ' }, 400, /Transcript is required/],
      [{ transcript: 123 }, 400, /Transcript is required/],
      [{ transcript: ['a'] }, 400, /Transcript is required/],
      [{ transcript: 'x'.repeat(2001) }, 400, /too long/],
      [{ transcript: 'hi', conversationId: '../../x' }, 400, /Invalid conversation id/],
      [{ transcript: 'hi', conversationId: 42 }, 400, /Invalid conversation id/],
      [{ transcript: 'hi', speed: 99 }, 400, /Speed must be/],
      [{ transcript: 'hi', speed: 'fast' }, 400, /Speed must be/],
      [{ transcript: 'hi', voice: 'x'.repeat(50) }, 400, /Voice must be/],
      [{ transcript: 'hi', voice: { a: 1 } }, 400, /Voice must be/]
    ];
    for (const [body, status, message] of cases) {
      const response = await s.post('/api/command', body);
      assert.equal(response.status, status, JSON.stringify(body).slice(0, 60));
      assert.match(response.json.error, message);
    }
    assert.equal((await s.post('/api/command', { transcript: 'hi', speed: 1.5, voice: 'en' })).status, 200);
  } finally { await s.stop(); }
});

test('POST /api/command: the voice and speed the page chose reach the speech engine', async () => {
  const s = await startServer();
  try {
    await s.post('/api/command', { transcript: 'tell me a joke', voice: 'en-gb', speed: 1.25 });
    assert.deepEqual(s.services.calls.find(c => c.via === 'tts').options, { voice: 'en-gb', speed: 1.25 });
  } finally { await s.stop(); }
});

test('POST /api/command: if only the voice fails, the text answer is still returned', async () => {
  const s = await startServer({ ttsFails: true });
  try {
    const { status, json } = await s.post('/api/command', { transcript: 'tell me a joke' });
    assert.equal(status, 200);
    assert.ok(json.response);
    assert.equal(json.audio, null);
    assert.match(json.audioError, /Voice output is unavailable/);
  } finally { await s.stop(); }
});

test('POST /api/command: failures are reported with their status, and nothing is saved for a failed exchange', async () => {
  const s = await startServer({ llmFails: true });
  try {
    const { conversationId } = (await s.post('/api/conversations', {})).json;
    const failed = await s.post('/api/command', { transcript: 'tell me about volcanoes', conversationId });
    assert.equal(failed.status, 503);
    assert.match(failed.json.error, /local language model/);
    assert.equal(s.conversations.getHistory(conversationId).length, 0, 'no dangling user message');

    s.services.llmFails = false;
    await s.post('/api/command', { transcript: 'tell me about volcanoes', conversationId });
    assert.deepEqual(s.conversations.getHistory(conversationId).map(m => m.role), ['user', 'assistant']);
  } finally { await s.stop(); }
});

test('POST /api/command: an empty AI answer is an error, not silence', async () => {
  const s = await startServer({ localReply: '   ' });
  try {
    const { status, json } = await s.post('/api/command', { transcript: 'tell me about volcanoes' });
    assert.equal(status, 502);
    assert.match(json.error, /did not produce an answer/);
  } finally { await s.stop(); }
});

test('POST /api/command: unexpected errors do not leak details', async () => {
  const s = await startServer();
  try {
    s.services.generateResponse = async () => { throw new Error('ENOENT /Users/secret/path'); };
    const { status, json } = await s.post('/api/command', { transcript: 'tell me about volcanoes' });
    assert.equal(status, 500);
    assert.equal(json.error, 'Something went wrong on the server');
    assert.doesNotMatch(JSON.stringify(json), /secret/);
  } finally { await s.stop(); }
});

test('POST /api/command: a conversation id the server no longer has is recreated', async () => {
  const s = await startServer();
  try {
    const { status, json } = await s.post('/api/command', { transcript: 'hello', conversationId: ID_A });
    assert.equal(status, 200);
    assert.equal(json.conversationId, ID_A);
    assert.equal(s.conversations.getHistory(ID_A).length, 2);
  } finally { await s.stop(); }
});

// ------------------------------------------------------------------ transcribe / synthesize

test('POST /api/transcribe: returns the transcript; silence is a normal answer with noSpeech', async () => {
  const s = await startServer();
  try {
    const spoken = await s.request('POST', '/api/transcribe', audioForm());
    assert.equal(spoken.status, 200);
    assert.deepEqual({ t: spoken.json.transcript, n: spoken.json.noSpeech }, { t: 'hello there', n: false });

    s.services.transcribeResult = { text: '', duration: 1 };
    const quiet = await s.request('POST', '/api/transcribe', audioForm());
    assert.equal(quiet.status, 200);
    assert.deepEqual({ t: quiet.json.transcript, n: quiet.json.noSpeech }, { t: '', n: true });
  } finally { await s.stop(); }
});

test('POST /api/transcribe: bad uploads get the right status', async () => {
  const s = await startServer();
  try {
    assert.equal((await s.request('POST', '/api/transcribe', new FormData())).status, 400);
    assert.equal((await s.request('POST', '/api/transcribe', audioForm(''))).status, 400);          // empty file

    const tooBig = await s.request('POST', '/api/transcribe', audioForm(Buffer.alloc(26 * 1024 * 1024)));
    assert.equal(tooBig.status, 413);
    assert.match(tooBig.json.error, /too large/);

    for (const language of ['--help', 'english', 'e', 'EN', 'en;rm']) {
      const response = await s.request('POST', '/api/transcribe', audioForm('x', { language }));
      assert.equal(response.status, 400, language);
      assert.match(response.json.error, /Language must be/);
    }
    assert.equal((await s.request('POST', '/api/transcribe', audioForm('x', { language: 'en' }))).status, 200);
    assert.equal((await s.request('POST', '/api/transcribe', audioForm('x', { language: 'auto' }))).status, 200);

    s.services.transcribeError = Object.assign(new Error('That recording could not be read as audio'), { status: 400 });
    const unreadable = await s.request('POST', '/api/transcribe', audioForm('x'));
    assert.equal(unreadable.status, 400);
    assert.equal(unreadable.json.error, 'That recording could not be read as audio');
  } finally { await s.stop(); }
});

test('POST /api/synthesize: audio with its real content type', async () => {
  for (const [format, type] of [['wav', 'audio/wav'], ['mp3', 'audio/mpeg']]) {
    const s = await startServer({ ttsFormat: format });
    try {
      const response = await s.post('/api/synthesize', { text: 'hello', speed: 1.5, voice: 'en-gb' });
      assert.equal(response.status, 200);
      assert.equal(response.headers.get('content-type'), type);
      assert.equal(response.body.toString(), 'RIFFfakewav');
      assert.deepEqual(s.services.calls.find(c => c.via === 'tts').options, { voice: 'en-gb', speed: 1.5 });
    } finally { await s.stop(); }
  }
});

test('POST /api/synthesize: validation', async () => {
  const s = await startServer();
  try {
    for (const [body, message] of [
      [{}, /Text is required/], [{ text: '' }, /Text is required/], [{ text: '  ' }, /Text is required/],
      [{ text: { a: 1 } }, /Text is required/], [{ text: 5 }, /Text is required/],
      [{ text: 'x'.repeat(4097) }, /too long/], [{ text: 'hi', speed: 0 }, /Speed must be/], [{ text: 'hi', speed: 5 }, /Speed must be/]
    ]) {
      const response = await s.post('/api/synthesize', body);
      assert.equal(response.status, 400, JSON.stringify(body).slice(0, 50));
      assert.match(response.json.error, message);
    }
    assert.equal((await s.post('/api/synthesize', { text: 'x'.repeat(4096) })).status, 200);
    assert.equal((await s.post('/api/synthesize', { text: 'hi' })).status, 200);       // no speed: normal
  } finally { await s.stop(); }
});

// ------------------------------------------------------------------ conversations

test('conversations: create, list, get, clear, delete', async () => {
  const s = await startServer();
  try {
    const created = await s.post('/api/conversations', { userId: 'alice' });
    assert.equal(created.status, 200);
    const id = created.json.conversationId;
    assert.ok(ConversationManager.isValidId(id));

    await s.post('/api/command', { transcript: 'hello', conversationId: id });
    const got = await s.get(`/api/conversations/${id}`);
    assert.equal(got.json.conversation.userId, 'alice');
    assert.equal(got.json.messages.length, 2);
    assert.equal((await s.get(`/api/conversations/${id}?limit=1`)).json.messages.length, 1);

    assert.equal((await s.get('/api/conversations')).json.conversations.length, 1);

    assert.equal((await s.post(`/api/conversations/${id}/clear`)).status, 200);
    assert.equal((await s.get(`/api/conversations/${id}`)).json.messages.length, 0);

    assert.equal((await s.del(`/api/conversations/${id}`)).status, 200);
    assert.equal((await s.get(`/api/conversations/${id}`)).status, 404);
    assert.equal((await s.del(`/api/conversations/${id}`)).status, 404);
  } finally { await s.stop(); }
});

test('conversations: /stats is its own route (not read as an id)', async () => {
  const s = await startServer();
  try {
    await s.post('/api/command', { transcript: 'hello', conversationId: ID_A });
    await s.post('/api/command', { transcript: 'hello', conversationId: ID_B });
    const { status, json } = await s.get('/api/conversations/stats');
    assert.equal(status, 200);
    assert.equal(json.success, true);
    assert.equal(json.stats.conversationCount, 2);
    assert.equal(json.stats.totalMessages, 4);
  } finally { await s.stop(); }
});

test('conversations: unknown is 404, malformed is 400, and nothing outside the storage directory is touched', async () => {
  const s = await startServer();
  try {
    assert.equal((await s.get(`/api/conversations/${ID_A}`)).status, 404);
    assert.equal((await s.post(`/api/conversations/${ID_A}/clear`)).status, 404);
    assert.equal((await s.del(`/api/conversations/${ID_A}`)).status, 404);

    const decoy = path.join(s.dir, 'decoy.json');
    fs.writeFileSync(decoy, JSON.stringify({ messages: [], metadata: {} }));
    const traversal = encodeURIComponent('../decoy');
    for (const request of [() => s.get(`/api/conversations/${traversal}`), () => s.del(`/api/conversations/${traversal}`),
      () => s.post(`/api/conversations/${traversal}/clear`), () => s.get('/api/conversations/not-an-id')]) {
      const response = await request();
      assert.equal(response.status, 400);
      assert.match(response.json.error, /Invalid conversation id/);
    }
    assert.equal(fs.existsSync(decoy), true, 'the file outside the storage directory is still there');
  } finally { await s.stop(); }
});

test('conversations: limits are clamped and userId must be a string', async () => {
  const s = await startServer();
  try {
    for (const id of [ID_A, ID_B, 'conv_1793432160003_cccccccc']) await s.post('/api/command', { transcript: 'hi', conversationId: id });
    assert.equal((await s.get('/api/conversations?limit=2')).json.conversations.length, 2);
    assert.equal((await s.get('/api/conversations?limit=-1')).json.conversations.length, 3);
    assert.equal((await s.get('/api/conversations?limit=abc')).json.conversations.length, 3);
    assert.equal((await s.get('/api/conversations?limit=0')).json.conversations.length, 3);
    assert.equal((await s.post('/api/conversations', { userId: { a: 1 } })).status, 400);
    assert.equal((await s.post('/api/conversations', {})).status, 200);
  } finally { await s.stop(); }
});

// ------------------------------------------------------------------ service mode

test('service mode: valid switch, invalid mode, and a mode that cannot work', async () => {
  const s = await startServer({ mode: 'local' });
  try {
    const ok = await s.post('/api/service/mode', { mode: 'hybrid' });
    assert.equal(ok.status, 200);
    assert.equal(ok.json.mode, 'hybrid');

    for (const mode of ['turbo', '', 5, null, undefined]) {
      assert.equal((await s.post('/api/service/mode', { mode })).status, 400, String(mode));
    }

    s.services.problem = 'Cloud mode needs an OpenAI API key.';
    const refused = await s.post('/api/service/mode', { mode: 'cloud' });
    assert.equal(refused.status, 409);
    assert.match(refused.json.error, /needs an OpenAI API key/);
    assert.equal(s.services.getMode(), 'hybrid', 'the mode did not change');
    assert.equal((await s.get('/api/service/status')).json.mode, 'hybrid');
  } finally { await s.stop(); }
});

// ------------------------------------------------------------------ misc

test('GET /api/health, /api/voices, /api/commands, and the page', async () => {
  const s = await startServer();
  try {
    const health = await s.get('/api/health');
    assert.equal(health.status, 200);
    assert.equal(health.json.status, 'ok');
    assert.deepEqual((await s.get('/api/voices')).json.voices, ['en', 'en-gb']);

    const commands = (await s.get('/api/commands')).json.commands;
    assert.ok(commands.length >= 9);
    assert.ok(commands.every(c => c.id && c.name && Array.isArray(c.examples)));

    const page = await s.request('GET', '/');
    assert.equal(page.status, 200);
    assert.match(page.body.toString(), /<title>Voice Assistant/);
    assert.equal((await s.request('GET', '/app.js')).status, 200);
  } finally { await s.stop(); }
});

test('errors: malformed JSON is a 400, unknown API routes a JSON 404, none leak internals', async () => {
  const s = await startServer();
  try {
    const bad = await s.request('POST', '/api/command', '{bad json');
    assert.equal(bad.status, 400);
    assert.equal(bad.json.error, 'Request body is not valid JSON');

    const missing = await s.get('/api/nope');
    assert.equal(missing.status, 404);
    assert.deepEqual(missing.json, { error: 'Not found' });

    const huge = await s.request('POST', '/api/command', JSON.stringify({ transcript: 'x'.repeat(200000) }));
    assert.equal(huge.status, 413);
  } finally { await s.stop(); }
});

test('CORS is closed by default and opens only for listed origins', async () => {
  const closed = await startServer({}, { ALLOWED_ORIGINS: undefined });
  try {
    const response = await closed.request('GET', '/api/conversations', undefined, { Origin: 'http://evil.example' });
    assert.equal(response.headers.get('access-control-allow-origin'), null);
    const preflight = await closed.request('OPTIONS', '/api/conversations/' + ID_A, undefined, {
      Origin: 'http://evil.example', 'Access-Control-Request-Method': 'DELETE'
    });
    assert.equal(preflight.headers.get('access-control-allow-methods'), null);
  } finally { await closed.stop(); }

  const listed = await startServer({}, { ALLOWED_ORIGINS: 'http://localhost:3000, http://localhost:4000' });
  try {
    const good = await listed.request('GET', '/api/conversations', undefined, { Origin: 'http://localhost:4000' });
    assert.equal(good.headers.get('access-control-allow-origin'), 'http://localhost:4000');
    const bad = await listed.request('GET', '/api/conversations', undefined, { Origin: 'http://evil.example' });
    assert.equal(bad.headers.get('access-control-allow-origin'), null);
  } finally { await listed.stop(); }

  const open = await startServer({}, { ALLOWED_ORIGINS: '*' });
  try {
    const response = await open.request('GET', '/api/conversations', undefined, { Origin: 'http://anything.example' });
    assert.equal(response.headers.get('access-control-allow-origin'), '*');
  } finally { await open.stop(); }
});

test('rate limit: too many requests in a window are refused with 429 and Retry-After', async () => {
  const s = await startServer({}, { RATE_LIMIT_MAX_REQUESTS: '3', RATE_LIMIT_WINDOW_MS: '60000' });
  try {
    for (let i = 0; i < 3; i++) {
      assert.equal((await s.post('/api/command', { transcript: 'hello' })).status, 200);
    }
    const limited = await s.post('/api/command', { transcript: 'hello' });
    assert.equal(limited.status, 429);
    assert.match(limited.json.error, /Too many requests/);
    assert.ok(Number(limited.headers.get('retry-after')) >= 1);

    // the limit covers the endpoints that call paid services, and only those
    assert.equal((await s.post('/api/synthesize', { text: 'hi' })).status, 429);
    assert.equal((await s.request('POST', '/api/transcribe', audioForm())).status, 429);
    assert.equal((await s.get('/api/health')).status, 200);
    assert.equal((await s.get('/api/conversations')).status, 200);
  } finally { await s.stop(); }
});

test('rate limit: a new window starts once the old one has passed', async () => {
  const s = await startServer({}, { RATE_LIMIT_MAX_REQUESTS: '1', RATE_LIMIT_WINDOW_MS: '150' });
  try {
    assert.equal((await s.post('/api/command', { transcript: 'hello' })).status, 200);
    assert.equal((await s.post('/api/command', { transcript: 'hello' })).status, 429);
    await new Promise(r => setTimeout(r, 200));
    assert.equal((await s.post('/api/command', { transcript: 'hello' })).status, 200);
  } finally { await s.stop(); }
});

test('rate limit: unset or invalid settings fall back to 60 per minute', async () => {
  const s = await startServer({}, { RATE_LIMIT_MAX_REQUESTS: 'lots', RATE_LIMIT_WINDOW_MS: '' });
  try {
    for (let i = 0; i < 60; i++) {
      assert.equal((await s.post('/api/synthesize', { text: 'hi' })).status, 200);
    }
    assert.equal((await s.post('/api/synthesize', { text: 'hi' })).status, 429);
  } finally { await s.stop(); }
});

test('buildSystemPrompt: tells the model the date and whether it has tools', () => {
  const withTools = buildSystemPrompt(true);
  const without = buildSystemPrompt(false);
  assert.match(withTools, /Current date and time: \w+day, /);
  assert.match(withTools, /use your tools/);
  assert.match(without, /do not have internet access/);
  assert.doesNotMatch(without, /use your tools/);
});

test('the server module can be required without starting anything', () => {
  assert.equal(typeof createApp, 'function');
});

test('start(): listens on loopback only unless HOST says otherwise', async () => {
  const axios = require('axios');
  const { start } = require('../server');
  const restoreConsole = silenceConsole();
  const dir = tempDir();
  const originalHead = axios.head;
  const originalGet = axios.get;
  axios.head = async () => ({});
  axios.get = async () => ({ data: { models: [] } });
  const env = {
    PORT: '0', HOST: undefined, SERVICE_MODE: 'local', OPENAI_API_KEY: '', ALLOWED_ORIGINS: '',
    WHISPER_CPP_PATH: '/nonexistent/whisper', WHISPER_MODEL_PATH: '/nonexistent/model.bin', TTS_ENGINE: 'nonsense',
    CONVERSATIONS_DIR: path.join(dir, 'conversations'), AUDIO_TEMP_DIR: path.join(dir, 'audio')
  };
  const saved = {};
  for (const [key, value] of Object.entries(env)) { saved[key] = process.env[key]; if (value === undefined) delete process.env[key]; else process.env[key] = value; }

  const listen = async () => {
    const server = start();
    await new Promise((resolve) => server.once('listening', resolve));
    const { address } = server.address();
    await new Promise((resolve) => server.close(resolve));
    return address;
  };
  try {
    assert.equal(await listen(), '127.0.0.1');
    process.env.HOST = '0.0.0.0';
    assert.equal(await listen(), '0.0.0.0');
  } finally {
    for (const [key, value] of Object.entries(saved)) { if (value === undefined) delete process.env[key]; else process.env[key] = value; }
    axios.head = originalHead;
    axios.get = originalGet;
    restoreConsole();
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
