const test = require('node:test');
const assert = require('node:assert/strict');
const { loadApp } = require('./frontend-harness');

const ID = 'conv_1793432160845_2d681ca6';
const post = (app, url) => app.calls.filter(c => c.method === 'POST' && c.url === url);

test('opening the page creates no conversation; the first spoken message creates one', async () => {
  const app = loadApp();
  try {
    const va = await app.start();
    assert.equal(post(app, '/api/conversations').length, 0);
    assert.equal(va.conversationId, null);

    await va.getResponse('hello');
    assert.equal(post(app, '/api/conversations').length, 1);
    assert.equal(va.conversationId, ID);
    await va.getResponse('again');
    assert.equal(post(app, '/api/conversations').length, 1, 'the same conversation is reused');
  } finally { app.cleanup(); }
});

test('voice and speed from the settings are sent with every question', async () => {
  const app = loadApp({ storage: { voiceAssistantSettings: JSON.stringify({ voice: 'fr', speed: 1.25, vadSensitivity: 0.3 }) } });
  try {
    const va = await app.start();
    await va.getResponse('hello');
    const body = post(app, '/api/command')[0].body;
    assert.deepEqual({ v: body.voice, s: body.speed, t: body.transcript, c: body.conversationId }, { v: 'fr', s: 1.25, t: 'hello', c: ID });
  } finally { app.cleanup(); }
});

test('the voice list comes from the server, and a saved voice that no longer exists falls back', async () => {
  const app = loadApp({ storage: { voiceAssistantSettings: JSON.stringify({ voice: 'alloy', speed: 1 }) } });
  try {
    const va = await app.start();
    assert.deepEqual(app.el('voiceSelect').options.map(o => o.value), ['en', 'en-gb', 'fr']);
    assert.equal(va.settings.voice, 'en');
    assert.equal(app.el('voiceSelect').value, 'en');
  } finally { app.cleanup(); }
});

test('hands-free is never restored as "on" (it needs a microphone grant the page has not asked for)', async () => {
  const app = loadApp({ storage: { voiceAssistantSettings: JSON.stringify({ voice: 'en', speed: 1, handsfree: true, vadSensitivity: 0.5 }) } });
  try {
    const va = await app.start();
    assert.equal(app.el('handsfreeToggle').checked, false);
    assert.equal(va.isHandsfreeMode, false);
    assert.equal(va.settings.handsfree, false);
    assert.equal(app.el('sensitivitySlider').value, 0.5, 'other settings are restored');
  } finally { app.cleanup(); }
});

test('settings survive corrupt or unavailable storage', async () => {
  const corrupt = loadApp({ storage: { voiceAssistantSettings: '{not json' } });
  try { assert.ok(await corrupt.start()); } finally { corrupt.cleanup(); }
});

test('push to talk: press, hold, release records and sends one recording', async () => {
  const app = loadApp();
  try {
    const va = await app.start();
    const button = app.el('recordBtn');
    button.dispatch('mousedown');
    await app.settle(5);
    assert.equal(va.isRecording, true);
    assert.equal(app.recorders[0].started, true);
    await app.settle(350);                       // hold longer than the 300 ms minimum
    button.dispatch('mouseup');
    await app.settle(60);

    assert.equal(app.recorders[0].stopped, true);
    assert.equal(va.isRecording, false);
    assert.equal(post(app, '/api/transcribe').length, 1);
    assert.deepEqual(app.messages(), ['You: what time is it', 'Assistant: It is noon.']);
    assert.equal(app.played.length, 1, 'the spoken answer is played');
    assert.equal(va.isProcessing, false);
  } finally { app.cleanup(); }
});

test('releasing before the microphone is ready records nothing and leaves the microphone off', async () => {
  const app = loadApp({ micDelay: 80 });
  try {
    const va = await app.start();
    const button = app.el('recordBtn');
    button.dispatch('mousedown');
    await app.settle(10);
    button.dispatch('mouseup');                  // let go while the mic is still opening
    await app.settle(150);

    assert.equal(va.isRecording, false, 'not stuck on "Listening"');
    assert.equal(app.recorders.every(r => !r.started), true, 'no recording was started');
    assert.equal(app.streams.length, 1);
    assert.equal(app.streams[0].tracks[0].readyState, 'ended', 'the microphone was released');
    assert.equal(post(app, '/api/transcribe').length, 0);
  } finally { app.cleanup(); }
});

test('pressing again while the microphone opens still records', async () => {
  const app = loadApp({ micDelay: 80 });
  try {
    const va = await app.start();
    const button = app.el('recordBtn');
    button.dispatch('mousedown');
    await app.settle(10);
    button.dispatch('mouseup');
    button.dispatch('mousedown');                // changed their mind before the mic opened
    await app.settle(150);
    assert.equal(va.isRecording, true);
    button.dispatch('mouseup');
    await app.settle(10);
    assert.equal(va.isRecording, false);
  } finally { app.cleanup(); }
});

test('pressing twice while the microphone opens opens it once', async () => {
  const app = loadApp({ micDelay: 80 });
  try {
    const va = await app.start();
    const button = app.el('recordBtn');
    button.dispatch('mousedown');
    button.dispatch('mousedown');
    button.dispatch('touchstart');
    await app.settle(150);
    assert.equal(app.streams.length, 1, 'one microphone stream');
    assert.equal(app.recorders.length, 1, 'one recorder');
    assert.equal(va.isRecording, true);
    button.dispatch('mouseup');
    await app.settle(10);
  } finally { app.cleanup(); }
});

test('the pointer leaving the button, and touch release, also stop', async () => {
  const app = loadApp();
  try {
    const va = await app.start();
    const button = app.el('recordBtn');
    button.dispatch('mousedown'); await app.settle(5);
    button.dispatch('mouseleave'); await app.settle(5);
    assert.equal(va.isRecording, false);
    button.dispatch('touchstart'); await app.settle(5);
    assert.equal(va.isRecording, true);
    button.dispatch('touchend'); await app.settle(5);
    assert.equal(va.isRecording, false);
  } finally { app.cleanup(); }
});

test('the recorder uses a type the browser supports (Safari has no webm)', async () => {
  const app = loadApp({ supportedTypes: ['audio/mp4'] });
  try {
    const va = await app.start();
    await va.startRecording();
    assert.equal(app.recorders[0].mimeType, 'audio/mp4');
    await va.startRecording();
    assert.equal(app.recorders.length, 1, 'a second start while recording is ignored');
  } finally { app.cleanup(); }
});

test('Space: records from the page, but never while a control has focus', async () => {
  const app = loadApp();
  try {
    const va = await app.start();
    let started = 0;
    va.startRecording = async () => { started++; };
    const press = () => app.document.dispatch('keydown', { code: 'Space', key: ' ' });

    for (const id of ['speedSelect', 'voiceSelect', 'serviceModeSelect', 'handsfreeToggle', 'closeSettingsBtn', 'sensitivitySlider']) {
      app.el(id).focus();
      const event = press();
      assert.equal(event.defaultPrevented, false, `${id} keeps its own Space behaviour`);
    }
    assert.equal(started, 0);

    app.document.activeElement = app.document.body;
    const event = press();
    assert.equal(started, 1);
    assert.equal(event.defaultPrevented, true);

    va.stopRecording = () => { started = -100; };
    app.document.dispatch('keyup', { code: 'Space', key: ' ' });
    assert.equal(started, -100, 'releasing Space stops');
  } finally { app.cleanup(); }
});

test('Space does nothing while an answer is being prepared, or in hands-free mode', async () => {
  const app = loadApp();
  try {
    const va = await app.start();
    let started = 0;
    va.startRecording = async () => { started++; };
    va.isProcessing = true;
    app.document.dispatch('keydown', { code: 'Space', key: ' ' });
    va.isProcessing = false;
    va.isHandsfreeMode = true;
    app.document.dispatch('keydown', { code: 'Space', key: ' ' });
    app.document.dispatch('keydown', { code: 'Space', key: ' ', repeat: true });
    assert.equal(started, 0);
  } finally { app.cleanup(); }
});

test('hands-free ignores "speech" while the assistant is working or talking', async () => {
  const app = loadApp();
  try {
    const va = await app.start();
    let started = 0;
    va.startRecording = async () => { started++; };
    va.isProcessing = true; va.handleVADSpeechStart();
    va.isProcessing = false; va.isPlaying = true; va.handleVADSpeechStart();
    assert.equal(started, 0);
    va.isPlaying = false; va.handleVADSpeechStart();
    assert.equal(started, 1);
  } finally { app.cleanup(); }
});

test('a recording with no speech says so and does not ask the assistant anything', async () => {
  const app = loadApp({ routes: { 'POST /api/transcribe': () => ({ json: { transcript: '', noSpeech: true } }) } });
  try {
    const va = await app.start();
    app.el('recordBtn').dispatch('mousedown'); await app.settle(350);
    app.el('recordBtn').dispatch('mouseup'); await app.settle(60);
    assert.equal(post(app, '/api/command').length, 0);
    assert.match(app.messages().join('\n'), /didn't catch any speech/);
    assert.equal(va.isProcessing, false);
  } finally { app.cleanup(); }
});

test('too short a recording is not sent', async () => {
  const app = loadApp({ recordingBytes: 100 });
  try {
    await app.start();
    app.el('recordBtn').dispatch('mousedown'); await app.settle(5);
    app.el('recordBtn').dispatch('mouseup'); await app.settle(60);
    assert.equal(post(app, '/api/transcribe').length, 0);
    assert.match(app.messages().join('\n'), /Recording too short/);
  } finally { app.cleanup(); }
});

test('server errors are shown with their message, even when the body is not JSON', async () => {
  const app = loadApp({ routes: {
    'POST /api/transcribe': () => ({ status: 400, json: { error: 'That recording could not be read as audio' } }),
    'POST /api/command': () => ({ status: 502 })          // no JSON body
  } });
  try {
    const va = await app.start();
    await assert.rejects(va.transcribeAudio(new Blob(['x'])), /That recording could not be read as audio/);
    await assert.rejects(va.getResponse('hi'), /Failed to get response/);
  } finally { app.cleanup(); }
});

test('if only the voice is missing the text answer is still shown', async () => {
  const app = loadApp({ routes: { 'POST /api/command': () => ({ json: { response: 'Text only.', audio: null, audioError: 'Voice output is unavailable right now' } }) } });
  try {
    await app.start();
    app.el('recordBtn').dispatch('mousedown'); await app.settle(350);
    app.el('recordBtn').dispatch('mouseup'); await app.settle(60);
    assert.deepEqual(app.messages().slice(0, 2), ['You: what time is it', 'Assistant: Text only.']);
    assert.match(app.messages()[2], /Voice output is unavailable/);
    assert.equal(app.played.length, 0);
  } finally { app.cleanup(); }
});

test('changing to a mode the server refuses shows why and re-reads the real mode', async () => {
  const app = loadApp({ routes: { 'POST /api/service/mode': () => ({ status: 409, json: { error: 'Cloud mode needs an OpenAI API key.' } }) } });
  try {
    const va = await app.start();
    const healthBefore = app.calls.filter(c => c.url === '/api/health').length;
    await va.changeServiceMode('cloud');
    assert.match(app.messages().join('\n'), /Cloud mode needs an OpenAI API key\./);
    assert.equal(app.calls.filter(c => c.url === '/api/health').length, healthBefore + 1);
  } finally { app.cleanup(); }
});

// ------------------------------------------------------------------ timers

test('a timer set by voice is started, saved and fires an alert (message + spoken)', async () => {
  const app = loadApp();
  try {
    const va = await app.start();
    va.startTimer({ id: 't1', endTime: Date.now() + 60, label: null });
    assert.equal(va.timers.length, 1);
    assert.equal(JSON.parse(app.storage.voiceAssistantTimers).length, 1);
    va.startTimer({ id: 't1', endTime: Date.now() + 60 });
    assert.equal(va.timers.length, 1, 'the same timer is not started twice');

    await app.settle(200);
    assert.equal(va.timers.length, 0);
    assert.equal(JSON.parse(app.storage.voiceAssistantTimers).length, 0);
    assert.match(app.messages().join('\n'), /⏰ Time's up! Your timer has finished\./);
    assert.equal(post(app, '/api/synthesize').length, 1);
    assert.equal(app.played.length, 1);
  } finally { app.cleanup(); }
});

test('a reminder timer says what it was for', async () => {
  const app = loadApp();
  try {
    const va = await app.start();
    va.startTimer({ id: 't2', endTime: Date.now() + 20, label: 'call mom' });
    await app.settle(150);
    assert.match(app.messages().join('\n'), /⏰ Time to call mom!/);
    assert.equal(post(app, '/api/synthesize')[0].body.text, 'Time to call mom!');
  } finally { app.cleanup(); }
});

test('timers survive a reload; one that ran out meanwhile fires straight away', async () => {
  const saved = JSON.stringify([
    { id: 'soon', endTime: Date.now() + 5000, label: null },
    { id: 'late', endTime: Date.now() - 1000, label: 'stir the soup' },
    { id: 'junk', endTime: 'never' }, null, 'x'
  ]);
  const app = loadApp({ storage: { voiceAssistantTimers: saved } });
  try {
    const va = await app.start();
    await app.settle(100);
    assert.deepEqual(Array.from(va.timers, t => t.id), ['soon']);
    assert.match(app.messages().join('\n'), /Time to stir the soup!/);
  } finally { app.cleanup(); }
});

test('corrupt saved timers are ignored', async () => {
  const app = loadApp({ storage: { voiceAssistantTimers: '{not json' } });
  try {
    const va = await app.start();
    assert.equal(va.timers.length, 0);
  } finally { app.cleanup(); }
});

test('a command that sets a timer starts it in the page', async () => {
  const app = loadApp({ routes: { 'POST /api/command': () => ({ json: {
    response: 'Timer set for 1 minute.', audio: null, timer: { id: 'abc', duration: 60, endTime: Date.now() + 60000, label: null }
  } }) } });
  try {
    const va = await app.start();
    app.el('recordBtn').dispatch('mousedown'); await app.settle(350);
    app.el('recordBtn').dispatch('mouseup'); await app.settle(60);
    assert.deepEqual(Array.from(va.timers, t => t.id), ['abc']);
  } finally { app.cleanup(); }
});
