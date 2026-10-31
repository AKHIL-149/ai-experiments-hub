const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const axios = require('axios');
const F1Service = require('../src/F1Service');
const LocalLLMService = require('../src/LocalLLMService');
const ConnectivityService = require('../src/ConnectivityService');
const ServiceManager = require('../src/ServiceManager');
const OpenAIService = require('../src/OpenAIService');
const AudioProcessor = require('../src/AudioProcessor');
const WeatherService = require('../src/WeatherService');
const WebSearchService = require('../src/WebSearchService');
const { tempDir, silenceConsole } = require('./helpers');

/** Replace axios methods for the duration of a test */
function stubAxios(methods) {
  const originals = {};
  for (const [name, impl] of Object.entries(methods)) {
    originals[name] = axios[name];
    axios[name] = impl;
  }
  return () => Object.assign(axios, originals);
}

// ---------------------------------------------------------------- F1

test('F1: the race date is the published calendar date, in any server timezone', async () => {
  // A night race: 04:00 UTC on Saturday Nov 21 is Friday evening in US timezones.
  // The race is on Saturday the 21st at the circuit - that is the date to say.
  const restore = stubAxios({
    get: async () => ({ data: { MRData: { RaceTable: { Races: [{
      raceName: 'Las Vegas Grand Prix', date: '2026-11-21', time: '04:00:00Z', Circuit: { circuitName: 'Las Vegas Strip Circuit' }
    }] } } } })
  });
  const originalTZ = process.env.TZ;
  try {
    for (const tz of ['America/Chicago', 'Pacific/Auckland', 'UTC']) {
      process.env.TZ = tz;
      const race = await new F1Service().getNextRace();
      assert.equal(race.dateFormatted, 'Saturday, November 21, 2026', tz);
    }
  } finally {
    if (originalTZ === undefined) delete process.env.TZ; else process.env.TZ = originalTZ;
    restore();
  }
});

test('F1: a race with no start time still has a date; no race returns null', async () => {
  let races = [{ raceName: 'Test GP', date: '2026-03-15', Circuit: { circuitName: 'Test Circuit' } }];
  const restore = stubAxios({ get: async () => ({ data: { MRData: { RaceTable: { Races: races } } } }) });
  try {
    assert.equal((await new F1Service().getNextRace()).dateFormatted, 'Sunday, March 15, 2026');
    races = [];
    assert.equal(await new F1Service().getNextRace(), null);
  } finally { restore(); }
});

// ---------------------------------------------------------------- local LLM

test('LLM: a temperature of 0 is sent as 0 (not replaced by the default)', async () => {
  const silence = silenceConsole();
  let body;
  const restore = stubAxios({
    get: async () => ({ data: { models: [{ name: 'llama3.2:3b' }] } }),
    post: async (url, payload) => { body = payload; return { data: { message: { content: 'hi' }, eval_count: 1 } }; }
  });
  try {
    const llm = new LocalLLMService({ model: 'llama3.2:3b' });
    await llm.checkAvailability();
    await llm.generateResponse([{ role: 'user', content: 'x' }], { temperature: 0 });
    assert.equal(body.options.temperature, 0);
    await llm.generateResponse([{ role: 'user', content: 'x' }]);
    assert.equal(body.options.temperature, 0.7);
  } finally { restore(); silence(); }
});

test('LLM: the configured model must be pulled (a different tag of the same family does not count)', async () => {
  const silence = silenceConsole();
  const restore = stubAxios({ get: async () => ({ data: { models: [{ name: 'llama3.2:1b' }, { name: 'qwen3:8b' }] } }) });
  try {
    const llm = new LocalLLMService({ model: 'llama3.2:3b' });
    await llm.checkAvailability();
    assert.equal(llm.available(), false);

    const family = new LocalLLMService({ model: 'qwen3' });   // no tag means ":latest"
    await family.checkAvailability();
    assert.equal(family.available(), false);
  } finally { restore(); silence(); }
});

test('LLM: starting Ollama after the server is noticed on the next request', async () => {
  const silence = silenceConsole();
  let up = false;
  const restore = stubAxios({
    get: async () => { if (!up) throw new Error('ECONNREFUSED'); return { data: { models: [{ name: 'llama3.2:3b' }] } }; }
  });
  try {
    const llm = new LocalLLMService({ model: 'llama3.2:3b', recheckMs: 0 });
    await llm.checkAvailability();
    assert.equal(llm.available(), false);
    up = true;
    await llm.refreshIfStale();
    assert.equal(llm.available(), true);
  } finally { restore(); silence(); }
});

test('LLM: it does not look again more often than recheckMs', async () => {
  const silence = silenceConsole();
  let checks = 0;
  const restore = stubAxios({ get: async () => { checks++; throw new Error('down'); } });
  try {
    const llm = new LocalLLMService({ recheckMs: 60000 });
    await llm.checkAvailability();
    const before = checks;
    await llm.refreshIfStale();
    await llm.refreshIfStale();
    assert.equal(checks, before);
  } finally { restore(); silence(); }
});

test('LLM: if Ollama stops answering it is marked unavailable, so the next request looks again', async () => {
  const silence = silenceConsole();
  const restore = stubAxios({
    get: async () => ({ data: { models: [{ name: 'llama3.2:3b' }] } }),
    post: async () => { throw new Error('ECONNREFUSED'); }
  });
  try {
    const llm = new LocalLLMService({ model: 'llama3.2:3b' });
    await llm.checkAvailability();
    await assert.rejects(llm.generateResponse([{ role: 'user', content: 'x' }]), /Local LLM failed/);
    assert.equal(llm.available(), false);
  } finally { restore(); silence(); }
});

test('LLM: the unsafe Function-based math parser is gone', () => {
  assert.equal(typeof LocalLLMService.prototype.parseMathExpression, 'undefined');
});

// ---------------------------------------------------------------- connectivity

test('Connectivity: while offline it looks again in the background, but not too often', async () => {
  const silence = silenceConsole();
  let online = false;
  let checks = 0;
  const restore = stubAxios({ head: async () => { checks++; if (!online) throw new Error('offline'); return {}; } });
  try {
    const service = new ConnectivityService({ recheckMs: 50 });
    await service.ready();
    assert.equal(service.available(), false);

    service.recheckIfStale();                         // too soon: nothing happens
    await service.checkPromise;
    assert.equal(checks, 1);

    online = true;
    await new Promise(r => setTimeout(r, 80));
    service.recheckIfStale();
    await service.checkPromise;
    assert.equal(service.available(), true);
    assert.equal(checks, 2);

    service.recheckIfStale();                         // online: never rechecks
    assert.equal(checks, 2);
  } finally { restore(); silence(); }
});

test('Connectivity: "not checked yet" counts as available', () => {
  const silence = silenceConsole();
  const restore = stubAxios({ head: () => new Promise(() => {}) });
  try {
    const service = new ConnectivityService();
    assert.equal(service.available(), true);
  } finally { restore(); silence(); }
});

// ---------------------------------------------------------------- service manager

function fakeManager(overrides = {}) {
  const manager = Object.create(ServiceManager.prototype);
  Object.assign(manager, {
    mode: 'local', fallbackToCloud: true, cloudService: null,
    localWhisperService: { available: () => true },
    localTTSService: { available: () => true, getAvailableVoices: () => ['en', 'en-gb'], synthesizeSpeech: async (t, o) => ({ audioBuffer: Buffer.from('w'), format: 'wav', options: o }) },
    localLLMService: null, connectivityService: null
  }, overrides);
  return manager;
}

test('ServiceManager.modeProblem refuses modes that cannot work', () => {
  const noCloud = fakeManager();
  assert.match(noCloud.modeProblem('cloud'), /OPENAI_API_KEY/);
  assert.equal(noCloud.modeProblem('local'), null);
  assert.equal(noCloud.modeProblem('hybrid'), null);       // local is enough for hybrid

  const noWhisper = fakeManager({ localWhisperService: { available: () => false } });
  assert.match(noWhisper.modeProblem('local'), /speech recognition \(Whisper\).*is not available/);
  const nothingLocal = fakeManager({ localWhisperService: null, localTTSService: null });
  assert.match(nothingLocal.modeProblem('local'), /speech recognition \(Whisper\) and text-to-speech.*are not available/);
  assert.match(nothingLocal.modeProblem('hybrid'), /Hybrid mode needs/);

  const withCloud = fakeManager({ cloudService: {} });
  assert.equal(withCloud.modeProblem('cloud'), null);
  assert.equal(withCloud.modeProblem('hybrid'), null);
});

test('ServiceManager: unavailable services are 503s with a useful message', async () => {
  const silence = silenceConsole();
  try {
    const stt = fakeManager({ localWhisperService: { available: () => false } });
    await assert.rejects(stt.transcribeAudio('x'), (e) => e.status === 503 && /speech recognition/.test(e.message));

    const tts = fakeManager({ localTTSService: { available: () => false } });
    await assert.rejects(tts.synthesizeSpeech('x'), (e) => e.status === 503 && /text-to-speech/.test(e.message));

    const noLLM = fakeManager({ localLLMService: { available: () => false, model: 'llama3.2:3b', refreshIfStale: async () => {} } });
    await assert.rejects(noLLM.generateResponse([]), (e) => e.status === 503 && /Start Ollama and pull llama3.2:3b/.test(e.message));

    const cloudOnly = fakeManager({ mode: 'cloud' });
    await assert.rejects(cloudOnly.generateResponse([]), (e) => e.status === 503 && /OPENAI_API_KEY/.test(e.message));
    await assert.rejects(cloudOnly.generateResponseWithTools([]), (e) => e.status === 503);
  } finally { silence(); }
});

test('ServiceManager: a local LLM failure in local mode is a 503, with no cloud fallback', async () => {
  const silence = silenceConsole();
  try {
    let cloudCalled = false;
    const manager = fakeManager({
      cloudService: { generateResponse: async () => { cloudCalled = true; return { response: 'cloud' }; } },
      localLLMService: { available: () => true, refreshIfStale: async () => {}, generateResponse: async () => { throw new Error('down'); } }
    });
    await assert.rejects(manager.generateResponse([]), (e) => e.status === 503);
    assert.equal(cloudCalled, false);

    manager.mode = 'hybrid';
    assert.equal((await manager.generateResponse([])).response, 'cloud');
  } finally { silence(); }
});

test('ServiceManager: the local LLM is refreshed before use (Ollama started late)', async () => {
  const silence = silenceConsole();
  try {
    let available = false;
    const manager = fakeManager({
      localLLMService: {
        available: () => available,
        refreshIfStale: async () => { available = true; },
        generateResponse: async () => ({ response: 'local answer' })
      }
    });
    assert.equal((await manager.generateResponse([])).response, 'local answer');
  } finally { silence(); }
});

test('ServiceManager: cloud voice names are not passed to the local engine', async () => {
  const silence = silenceConsole();
  try {
    const manager = fakeManager();
    assert.equal((await manager.synthesizeSpeech('hi', { voice: 'alloy', speed: 1.5 })).options.voice, undefined);
    assert.equal((await manager.synthesizeSpeech('hi', { voice: 'en-gb', speed: 1.5 })).options.voice, 'en-gb');
    assert.equal((await manager.synthesizeSpeech('hi', { voice: 'en-gb', speed: 1.5 })).options.speed, 1.5);
  } finally { silence(); }
});

test('ServiceManager.setMode rejects unknown modes; getStatus reports the mode', () => {
  const silence = silenceConsole();
  try {
    const manager = fakeManager({
      localWhisperService: { available: () => true, getInfo: () => ({}) },
      localTTSService: { available: () => true, getInfo: () => ({}), getAvailableVoices: () => [] },
      webSearchService: { available: () => true, getInfo: () => ({}) },
      weatherService: { available: () => true, getInfo: () => ({}) }
    });
    assert.throws(() => manager.setMode('turbo'), /Invalid mode/);
    manager.setMode('hybrid');
    assert.equal(manager.getStatus().mode, 'hybrid');
  } finally { silence(); }
});

test('ServiceManager: the local LLM exists whatever mode the server started in', () => {
  const silence = silenceConsole();
  const restore = stubAxios({ get: async () => ({ data: { models: [] } }), head: async () => ({}) });
  try {
    const manager = new ServiceManager({ mode: 'cloud', whisperPath: '/nonexistent', whisperModelPath: '/nonexistent', ttsEngine: 'nonsense' });
    assert.ok(manager.localLLMService, 'switching to local later must not find it missing');
  } finally { restore(); silence(); }
});

// ---------------------------------------------------------------- OpenAI wrapper (SDK faked)

/** The real SDK reads (and so opens and closes) the upload stream; a fake has to as well */
function drain(stream) {
  stream.on('error', () => {});
  stream.resume();
}
function drainAndWait(stream) {
  return new Promise((resolve) => { stream.on('error', resolve); stream.on('close', resolve); stream.resume(); });
}

function fakeOpenAI(handlers) {
  const service = new OpenAIService('sk-test-not-real');
  service.openai = handlers;
  return service;
}

test('OpenAI: failures are 502s that keep the helpful message', async () => {
  const silence = silenceConsole();
  try {
    const service = fakeOpenAI({
      chat: { completions: { create: async () => { throw new Error('401 Incorrect API key'); } } },
      audio: { speech: { create: async () => { throw new Error('rate limited'); } }, transcriptions: { create: async ({ file }) => { drain(file); throw new Error('bad audio'); } } }
    });
    await assert.rejects(service.generateResponse([]), (e) => e.status === 502 && /401 Incorrect API key/.test(e.message));
    await assert.rejects(service.generateResponseWithTools([]), (e) => e.status === 502);
    await assert.rejects(service.synthesizeSpeech('hi'), (e) => e.status === 502 && /rate limited/.test(e.message));
    await assert.rejects(service.transcribeAudio('/nonexistent.webm'), (e) => e.status === 502);
  } finally { silence(); }
});

test('OpenAI: transcribing a buffer leaves no temp file behind, even on failure', async () => {
  const silence = silenceConsole();
  const cache = path.join(__dirname, '../data/audio-cache');
  fs.mkdirSync(cache, { recursive: true });
  const leftovers = () => fs.readdirSync(cache).filter(f => f.startsWith('temp_'));
  const before = leftovers();
  try {
    const ok = fakeOpenAI({ audio: { transcriptions: { create: async ({ file }) => { await drainAndWait(file); return { text: ' hello ' }; } } } });
    assert.equal((await ok.transcribeAudio(Buffer.from('x'))).text, 'hello');
    const failing = fakeOpenAI({ audio: { transcriptions: { create: async ({ file }) => { drain(file); throw new Error('nope'); } } } });
    await assert.rejects(failing.transcribeAudio(Buffer.from('x')));
    assert.deepEqual(leftovers(), before);
  } finally { silence(); }
});

test('OpenAI: speech text is cut at the 4096 character limit', async () => {
  const silence = silenceConsole();
  try {
    let input;
    const service = fakeOpenAI({ audio: { speech: { create: async (args) => { input = args.input; return { arrayBuffer: async () => new ArrayBuffer(4) }; } } } });
    await service.synthesizeSpeech('x'.repeat(5000));
    assert.equal(input.length, 4096);
    await assert.rejects(service.synthesizeSpeech('   '), /Text is required/);
  } finally { silence(); }
});

test('OpenAI tool calling: runs the requested tools and feeds the results back', async () => {
  const silence = silenceConsole();
  try {
    const calls = [];
    const service = new OpenAIService('sk-test-not-real', {
      weatherService: { available: () => true, getCurrentWeather: async (loc) => ({ tempF: 70, description: 'clear', location: loc, feelsLikeF: 71, humidity: 40 }) },
      f1Service: { getNextRace: async () => ({ raceName: 'Test GP', circuit: 'Circuit', dateFormatted: 'Sunday' }) },
      webSearchService: { available: () => true, search: async (q) => [{ title: 'T', url: 'u', content: `result for ${q}` }] }
    });
    service.openai = { chat: { completions: { create: async (args) => {
      calls.push(args);
      if (calls.length === 1) {
        return { usage: {}, choices: [{ message: { role: 'assistant', content: null, tool_calls: [
          { id: 'c1', function: { name: 'get_weather', arguments: '{"location":"Austin"}' } },
          { id: 'c2', function: { name: 'web_search', arguments: '{"query":"f1"}' } },
          { id: 'c3', function: { name: 'nope', arguments: '' } }
        ] } }] };
      }
      return { usage: {}, choices: [{ message: { content: 'final answer' } }] };
    } } } };

    const result = await service.generateResponseWithTools([{ role: 'user', content: 'q' }]);
    assert.equal(result.response, 'final answer');
    assert.deepEqual(result.usedTools, ['get_weather', 'web_search', 'nope']);
    const toolMessages = calls[1].messages.filter(m => m.role === 'tool');
    assert.equal(toolMessages.length, 3);
    assert.match(toolMessages[0].content, /70°F and clear in Austin/);
    assert.match(toolMessages[1].content, /result for f1/);
    assert.equal(toolMessages[2].content, 'Unknown tool: nope');
  } finally { silence(); }
});

test('OpenAI tools: a failing tool becomes text for the model, never an exception', async () => {
  const service = new OpenAIService('sk-test-not-real', {
    f1Service: { getNextRace: async () => { throw new Error('api down'); } }
  });
  assert.equal(await service._executeTool('get_f1_schedule', {}), 'Tool "get_f1_schedule" failed: api down');
  assert.equal(await service._executeTool('web_search', { query: 'x' }), 'Web search is not configured on this server.');
});

// ---------------------------------------------------------------- audio processor

function audioProcessorWith(serviceManager, options = {}) {
  const dir = tempDir();
  return { dir, processor: new AudioProcessor(serviceManager, { tempDir: dir, maxAudioSizeMB: 1, ...options }) };
}

test('AudioProcessor: transcription result, no-speech flag and temp-file cleanup', async () => {
  const silence = silenceConsole();
  const seen = [];
  const manager = { transcribeAudio: async (file) => { seen.push(file); assert.ok(fs.existsSync(file)); return { text: seen.length === 1 ? ' hello ' : '', duration: 5 }; } };
  const { dir, processor } = audioProcessorWith(manager);
  try {
    const spoken = await processor.processAudioInput(Buffer.from('x'));
    assert.deepEqual({ t: spoken.transcript, c: spoken.confidence, n: spoken.noSpeech }, { t: 'hello', c: 1, n: false });
    const quiet = await processor.processAudioInput(Buffer.from('x'));
    assert.deepEqual({ t: quiet.transcript, c: quiet.confidence, n: quiet.noSpeech }, { t: '', c: 0, n: true });
    assert.deepEqual(fs.readdirSync(dir), []);
    assert.notEqual(seen[0], seen[1], 'each request gets its own file');
  } finally { silence(); fs.rmSync(dir, { recursive: true, force: true }); }
});

test('AudioProcessor: errors with a status keep it and their message; others are wrapped', async () => {
  const silence = silenceConsole();
  let failure;
  const { dir, processor } = audioProcessorWith({ transcribeAudio: async () => { throw failure; } });
  try {
    failure = Object.assign(new Error('That recording could not be read as audio'), { status: 400 });
    await assert.rejects(processor.processAudioInput(Buffer.from('x')), (e) => e.status === 400 && e.message === 'That recording could not be read as audio');

    failure = new Error('disk full');
    await assert.rejects(processor.processAudioInput(Buffer.from('x')), (e) => e.status === undefined && e.message === 'Failed to process audio: disk full');
    assert.deepEqual(fs.readdirSync(dir), [], 'temp file removed after a failure');
  } finally { silence(); fs.rmSync(dir, { recursive: true, force: true }); }
});

test('AudioProcessor: oversize audio is a 413', async () => {
  const silence = silenceConsole();
  const { dir, processor } = audioProcessorWith({ transcribeAudio: async () => ({ text: 'x' }) });
  try {
    await assert.rejects(processor.processAudioInput(Buffer.alloc(2 * 1024 * 1024)), (e) => e.status === 413 && /too large/.test(e.message));
  } finally { silence(); fs.rmSync(dir, { recursive: true, force: true }); }
});

test('AudioProcessor: validateAudioFormat', () => {
  const { dir, processor } = audioProcessorWith({});
  try {
    assert.equal(processor.validateAudioFormat('not a buffer').valid, false);
    assert.equal(processor.validateAudioFormat(Buffer.alloc(0)).error, 'Audio data is empty');
    assert.match(processor.validateAudioFormat(Buffer.alloc(2 * 1024 * 1024)).error, /too large/);
    assert.equal(processor.validateAudioFormat(Buffer.from('x')).valid, true);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});

test('AudioProcessor: speech synthesis input and output', async () => {
  const silence = silenceConsole();
  const { dir, processor } = audioProcessorWith({ synthesizeSpeech: async (text, o) => ({ audioBuffer: Buffer.from(text), format: 'wav' }) });
  try {
    const result = await processor.generateAudioResponse('hi', { speed: 1 });
    assert.equal(result.format, 'wav');
    await assert.rejects(processor.generateAudioResponse('  '), (e) => e.status === 400);
    await assert.rejects(processor.generateAudioResponse({}), (e) => e.status === 400);
    assert.throws(() => new AudioProcessor(null), /required/);
  } finally { silence(); fs.rmSync(dir, { recursive: true, force: true }); }
});

test('AudioProcessor: old temp files are removed, recent ones kept', () => {
  const silence = silenceConsole();
  const { dir, processor } = audioProcessorWith({});
  try {
    fs.writeFileSync(path.join(dir, 'old.webm'), 'x');
    fs.writeFileSync(path.join(dir, 'new.webm'), 'x');
    const longAgo = new Date(Date.now() - 2 * 3600 * 1000);
    fs.utimesSync(path.join(dir, 'old.webm'), longAgo, longAgo);
    processor.cleanupOldFiles(3600000);
    assert.deepEqual(fs.readdirSync(dir), ['new.webm']);
    assert.equal(processor.getTempDirStats().fileCount, 1);
  } finally { silence(); fs.rmSync(dir, { recursive: true, force: true }); }
});

// ---------------------------------------------------------------- weather and search backends

test('Weather: wttr.in is asked for the named place (encoded) and the answer is shaped for speech', async () => {
  let url;
  const restore = stubAxios({ get: async (u) => { url = u; return { data: { current_condition: [{ temp_F: '73', FeelsLikeF: '75', humidity: '70', weatherDesc: [{ value: 'Overcast ' }] }] } }; } });
  try {
    const weather = await new WeatherService({ defaultLocation: 'Houston,TX,US' }).getCurrentWeather('São Paulo, Brazil');
    assert.equal(url, `https://wttr.in/${encodeURIComponent('São Paulo, Brazil')}`);
    assert.deepEqual(weather, { location: 'São Paulo, Brazil', description: 'overcast', tempF: 73, feelsLikeF: 75, humidity: 70 });

    const fallback = await new WeatherService({ defaultLocation: 'Houston,TX,US' }).getCurrentWeather(null);
    assert.equal(fallback.location, 'Houston, TX, US');
    await assert.rejects(new WeatherService().getCurrentWeather(null), /No location/);
  } finally { restore(); }
});

test('Weather: a wttr.in reply without conditions is an error', async () => {
  const restore = stubAxios({ get: async () => ({ data: {} }) });
  try {
    await assert.rejects(new WeatherService().getCurrentWeather('Nowhere'), /no current conditions/);
  } finally { restore(); }
});

test('Web search: DuckDuckGo results are shaped and limited', async () => {
  const restore = stubAxios({ get: async () => ({ data: {
    AbstractText: 'Abstract', Heading: 'Head', AbstractURL: 'http://a',
    RelatedTopics: [{ Text: 'A - one', FirstURL: 'u1' }, { Text: 'B - two', FirstURL: 'u2' }, { Text: 'C - three', FirstURL: 'u3' }, { NoText: true }]
  } }) });
  try {
    const results = await new WebSearchService().search('q', 3);
    assert.equal(results.length, 3);
    assert.deepEqual(results[0], { title: 'Head', url: 'http://a', content: 'Abstract' });
    assert.equal(results[1].title, 'A');
    assert.deepEqual(await new WebSearchService().search('q', 3).then(r => r.length), 3);
  } finally { restore(); }
});
