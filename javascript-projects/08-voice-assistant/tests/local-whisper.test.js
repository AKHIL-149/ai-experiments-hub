const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const LocalWhisperService = require('../src/LocalWhisperService');
const { cleanTranscript } = LocalWhisperService;
const { tempDir, writeNodeScript, silenceConsole } = require('./helpers');

// Stand-in for ffmpeg: behaviour chosen by FAKE_FFMPEG ("speech" | "silent" | "fail"); reports a loudest-sample level like volumedetect
const FAKE_FFMPEG = `
const fs = require('fs');
const args = process.argv.slice(2);
fs.appendFileSync(process.env.FAKE_LOG, 'ffmpeg ' + JSON.stringify(args) + '\\n');
const mode = process.env.FAKE_FFMPEG || 'speech';
if (mode === 'fail') { console.error('[in#0] EBML header parsing failed\\nError opening input file /secret/path/audio.webm'); process.exit(1); }
console.error('[Parsed_volumedetect_0] max_volume: ' + (mode === 'silent' ? '-91.0' : '-12.3') + ' dB');
fs.writeFileSync(args[args.length - 1], 'RIFFfakewav');
`;

// Stand-in for whisper-cli: writes "<file>.txt"; records start/end so concurrency can be measured
const FAKE_WHISPER = `
const fs = require('fs');
const args = process.argv.slice(2);
if (args[0] === '--help') process.exit(0);
const file = args[args.indexOf('-f') + 1];
fs.appendFileSync(process.env.FAKE_LOG, 'whisper-start ' + Date.now() + '\\n');
setTimeout(() => {
  if (process.env.FAKE_WHISPER_FAIL) { console.error('model error'); process.exit(3); }
  if (process.env.FAKE_WHISPER_TEXT !== undefined && process.env.FAKE_WHISPER_TEXT !== '__none__') {
    fs.writeFileSync(file + '.txt', process.env.FAKE_WHISPER_TEXT + '\\n');
  }
  fs.appendFileSync(process.env.FAKE_LOG, 'whisper-end ' + Date.now() + '\\n');
}, Number(process.env.FAKE_WHISPER_MS || 0));
`;

async function setup(env = {}, options = {}) {
  const restore = silenceConsole();
  const dir = tempDir();
  const log = path.join(dir, 'calls.log');
  Object.assign(process.env, { FAKE_LOG: log, FAKE_FFMPEG: 'speech', FAKE_WHISPER_TEXT: 'What time is it?', FAKE_WHISPER_MS: '0' }, env);
  const ffmpegPath = options.ffmpegPath || writeNodeScript(dir, 'ffmpeg', FAKE_FFMPEG);
  const whisperPath = writeNodeScript(dir, 'whisper-cli', FAKE_WHISPER);
  const modelPath = path.join(dir, 'model.bin');
  fs.writeFileSync(modelPath, 'model');
  const service = new LocalWhisperService({ whisperPath, modelPath, ffmpegPath, ...options.service });
  await service.checkAvailability();
  const lines = () => (fs.existsSync(log) ? fs.readFileSync(log, 'utf8').trim().split('\n') : []);
  const tmpLeftovers = () => fs.readdirSync(os.tmpdir()).filter(f => f.startsWith('whisper_'));
  return {
    service, lines, tmpLeftovers, dir,
    cleanup: () => {
      restore();
      for (const key of ['FAKE_LOG', 'FAKE_FFMPEG', 'FAKE_WHISPER_TEXT', 'FAKE_WHISPER_MS', 'FAKE_WHISPER_FAIL']) delete process.env[key];
      fs.rmSync(dir, { recursive: true, force: true });
    }
  };
}

test('cleanTranscript removes sound descriptions and keeps the words', () => {
  assert.equal(cleanTranscript('[BLANK_AUDIO]'), '');
  assert.equal(cleanTranscript('(airplane engine roaring)'), '');
  assert.equal(cleanTranscript('(eerie music)'), '');
  assert.equal(cleanTranscript('*music*'), '');
  assert.equal(cleanTranscript('♪ la la ♪'), 'la la');
  assert.equal(cleanTranscript(' What time is it? (coughs)'), 'What time is it?');
  assert.equal(cleanTranscript('hi [pause] there'), 'hi there');
  assert.equal(cleanTranscript(''), '');
  assert.equal(cleanTranscript(undefined), '');
});

test('speech is converted, transcribed and returned', async () => {
  const { service, lines, tmpLeftovers, cleanup } = await setup();
  const before = tmpLeftovers();
  try {
    const result = await service.transcribeAudio(Buffer.from('fake webm bytes'));
    assert.equal(result.text, 'What time is it?');
    assert.equal(result.noSpeech, false);
    assert.ok(result.duration >= 0);
    assert.ok(lines().some(l => l.startsWith('ffmpeg')));
    assert.ok(lines().some(l => l.startsWith('whisper-start')));
    assert.deepEqual(tmpLeftovers(), before, 'temp files are removed');
  } finally { cleanup(); }
});

test('ffmpeg gets the input path as an argument (no shell), 16 kHz mono wav', async () => {
  const { service, lines, cleanup } = await setup();
  try {
    await service.transcribeAudio(Buffer.from('x'));
    const args = JSON.parse(lines().find(l => l.startsWith('ffmpeg')).slice(7));
    assert.deepEqual(args.slice(0, 2), ['-nostdin', '-hide_banner']);
    assert.ok(args.includes('volumedetect'));
    assert.deepEqual(args.slice(args.indexOf('-ar'), args.indexOf('-ar') + 4), ['-ar', '16000', '-ac', '1']);
  } finally { cleanup(); }
});

test('a file path input works as well as a buffer, and is left in place', async () => {
  const { service, dir, cleanup } = await setup();
  try {
    const input = path.join(dir, 'recording.webm');
    fs.writeFileSync(input, 'x');
    const result = await service.transcribeAudio(input);
    assert.equal(result.text, 'What time is it?');
    assert.equal(fs.existsSync(input), true);
  } finally { cleanup(); }
});

test('silence never reaches whisper (it would invent words like "you")', async () => {
  const { service, lines, cleanup } = await setup({ FAKE_FFMPEG: 'silent', FAKE_WHISPER_TEXT: 'you' });
  try {
    const result = await service.transcribeAudio(Buffer.from('x'));
    assert.deepEqual({ text: result.text, noSpeech: result.noSpeech }, { text: '', noSpeech: true });
    assert.equal(lines().some(l => l.startsWith('whisper')), false);
  } finally { cleanup(); }
});

test('whisper output that is only sound descriptions means no speech', async () => {
  for (const text of ['(airplane engine roaring)', '[BLANK_AUDIO]', '(eerie music)', '']) {
    const { service, cleanup } = await setup({ FAKE_WHISPER_TEXT: text });
    try {
      const result = await service.transcribeAudio(Buffer.from('x'));
      assert.equal(result.noSpeech, true, JSON.stringify(text));
      assert.equal(result.text, '');
    } finally { cleanup(); }
  }
});

test('audio ffmpeg cannot read is a 400 with a friendly message that leaks no internals', async () => {
  const { service, tmpLeftovers, cleanup } = await setup({ FAKE_FFMPEG: 'fail' });
  const before = tmpLeftovers();
  try {
    await assert.rejects(service.transcribeAudio(Buffer.from('junk')), (error) => {
      assert.equal(error.status, 400);
      assert.equal(error.message, 'That recording could not be read as audio');
      assert.doesNotMatch(error.message, /secret|EBML/);
      return true;
    });
    assert.deepEqual(tmpLeftovers(), before);
  } finally { cleanup(); }
});

test('ffmpeg not installed is a 503 that says how to fix it', async () => {
  const { service, cleanup } = await setup({}, { ffmpegPath: '/nonexistent/ffmpeg' });
  try {
    await assert.rejects(service.transcribeAudio(Buffer.from('x')), (error) => {
      assert.equal(error.status, 503);
      assert.match(error.message, /ffmpeg is not installed.*FFMPEG_PATH/);
      return true;
    });
  } finally { cleanup(); }
});

test('whisper producing no output file at all is a failure, not "no speech"', async () => {
  const { service, cleanup } = await setup({ FAKE_WHISPER_TEXT: '__none__' });
  try {
    await assert.rejects(service.transcribeAudio(Buffer.from('x')), /No transcription output file created/);
  } finally { cleanup(); }
});

test('whisper failing is an error, and temp files are still removed', async () => {
  const { service, tmpLeftovers, cleanup } = await setup({ FAKE_WHISPER_FAIL: '1' });
  const before = tmpLeftovers();
  try {
    await assert.rejects(service.transcribeAudio(Buffer.from('x')), /Whisper failed \(exit code 3\)/);
    assert.deepEqual(tmpLeftovers(), before);
  } finally { cleanup(); }
});

test('only maxConcurrent transcriptions run at once; the rest wait their turn', async () => {
  const { service, lines, cleanup } = await setup({ FAKE_WHISPER_MS: '250' }, { service: { maxConcurrent: 2 } });
  try {
    const results = await Promise.all(Array.from({ length: 6 }, () => service.transcribeAudio(Buffer.from('x'))));
    assert.equal(results.every(r => r.text === 'What time is it?'), true);

    let running = 0;
    let peak = 0;
    for (const line of lines().filter(l => l.startsWith('whisper'))) {
      running += line.startsWith('whisper-start') ? 1 : -1;
      peak = Math.max(peak, running);
    }
    assert.equal(peak, 2);
    assert.equal(service.running, 0);
    assert.equal(service.waiting.length, 0);
  } finally { cleanup(); }
});

test('a failed transcription still frees its slot', async () => {
  const { service, cleanup } = await setup({ FAKE_FFMPEG: 'fail' }, { service: { maxConcurrent: 1 } });
  try {
    for (let i = 0; i < 3; i++) {
      await assert.rejects(service.transcribeAudio(Buffer.from('x')));
    }
    assert.equal(service.running, 0);
  } finally { cleanup(); }
});

test('invalid input types and an unavailable service are refused', async () => {
  const { service, cleanup } = await setup();
  try {
    await assert.rejects(service.transcribeAudio(42), /Invalid audio input/);
    await assert.rejects(service.transcribeAudio(null), /Invalid audio input/);
    service.isAvailable = false;
    await assert.rejects(service.transcribeAudio(Buffer.from('x')), /not available/);
  } finally { cleanup(); }
});

test('a missing model file makes the service unavailable', async () => {
  const restore = silenceConsole();
  try {
    const service = new LocalWhisperService({ whisperPath: process.execPath, modelPath: '/nonexistent/model.bin' });
    await service.checkAvailability();
    assert.equal(service.available(), false);
  } finally { restore(); }
});
