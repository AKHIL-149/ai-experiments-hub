const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const LocalTTSService = require('../src/LocalTTSService');
const { cleanForSpeech } = LocalTTSService;
const { tempDir, writeNodeScript, silenceConsole } = require('./helpers');

// A stand-in for espeak: records its arguments and writes a tiny "wav" to the -w path
const FAKE_ESPEAK = `
const fs = require('fs');
const args = process.argv.slice(2);
if (args[0] === '--version') { console.log('fake espeak'); process.exit(0); }
fs.appendFileSync(process.env.TTS_LOG, JSON.stringify(args) + '\\n');
if (process.env.TTS_FAIL) { console.error('boom'); process.exit(1); }
fs.writeFileSync(args[args.indexOf('-w') + 1], 'RIFFfakewav');
`;

async function setup(extraEnv = {}) {
  const restore = silenceConsole();
  const dir = tempDir();
  const log = path.join(dir, 'calls.log');
  process.env.TTS_LOG = log;
  for (const [key, value] of Object.entries(extraEnv)) process.env[key] = value;
  const espeakPath = writeNodeScript(dir, 'espeak', FAKE_ESPEAK);
  const outputDir = path.join(dir, 'out');
  fs.mkdirSync(outputDir);
  const service = new LocalTTSService({ engine: 'espeak', espeakPath, outputDir });
  await service.checkAvailability();
  const calls = () => (fs.existsSync(log) ? fs.readFileSync(log, 'utf8').trim().split('\n').map(l => JSON.parse(l)) : []);
  return {
    service, calls, outputDir, dir,
    cleanup: () => { restore(); delete process.env.TTS_LOG; delete process.env.TTS_FAIL; fs.rmSync(dir, { recursive: true, force: true }); }
  };
}

test('cleanForSpeech drops markdown, links and leading bullets', () => {
  assert.equal(cleanForSpeech('- hello **world**'), 'hello world');
  assert.equal(cleanForSpeech('See https://example.com/a?b=1 now'), 'See link now');
  assert.equal(cleanForSpeech('\n- one\n- two'), 'one two');
  assert.equal(cleanForSpeech('# Title\n> quote `code`'), 'Title quote code');
  assert.equal(cleanForSpeech('a\u0000b\u001fc'), 'a b c');
  assert.equal(cleanForSpeech('***'), '');
});

test('text is passed after "--" so it can never be read as an option', async () => {
  const { service, calls, cleanup } = await setup();
  try {
    await service.synthesizeSpeech('--help', {});
    await service.synthesizeSpeech('- hello there', {});
    const [first, second] = calls();
    assert.deepEqual(first.slice(-2), ['--', '--help']);
    assert.deepEqual(second.slice(-2), ['--', 'hello there']);
  } finally { cleanup(); }
});

test('speed is a multiplier of the base words-per-minute, clamped to espeak\'s range', async () => {
  const { service, calls, cleanup } = await setup();
  try {
    const wpm = async (speed) => {
      await service.synthesizeSpeech('hello', speed === undefined ? {} : { speed });
      const args = calls().pop();
      return Number(args[args.indexOf('-s') + 1]);
    };
    assert.equal(await wpm(undefined), 175);
    assert.equal(await wpm(1.0), 175);          // used to be sent to espeak as "-s 1" (clamped to its slowest)
    assert.equal(await wpm(2), 350);
    assert.equal(await wpm(0.75), 131);
    assert.equal(await wpm(0.1), 80);           // floor
    assert.equal(await wpm(10), 450);           // ceiling
    assert.equal(await wpm('abc'), 175);        // junk -> normal speed
    assert.equal(await wpm(-2), 175);
  } finally { cleanup(); }
});

test('the voice option is passed through', async () => {
  const { service, calls, cleanup } = await setup();
  try {
    await service.synthesizeSpeech('hello', { voice: 'en-gb' });
    await service.synthesizeSpeech('hello', {});
    const [a, b] = calls();
    assert.equal(a[a.indexOf('-v') + 1], 'en-gb');
    assert.equal(b[b.indexOf('-v') + 1], 'en');
  } finally { cleanup(); }
});

test('returns the audio as wav and removes its temp file', async () => {
  const { service, outputDir, cleanup } = await setup();
  try {
    const result = await service.synthesizeSpeech('hello', {});
    assert.equal(result.format, 'wav');
    assert.equal(result.audioBuffer.toString(), 'RIFFfakewav');
    assert.deepEqual(fs.readdirSync(outputDir), []);
  } finally { cleanup(); }
});

test('text with nothing to say is refused', async () => {
  const { service, calls, cleanup } = await setup();
  try {
    await assert.rejects(service.synthesizeSpeech('***', {}), /nothing to say/);
    await assert.rejects(service.synthesizeSpeech('   ', {}), /nothing to say/);
    assert.equal(calls().length, 0);
  } finally { cleanup(); }
});

test('parallel requests use different files', async () => {
  const { service, calls, outputDir, cleanup } = await setup();
  try {
    await Promise.all(Array.from({ length: 8 }, (_, i) => service.synthesizeSpeech(`line ${i}`, {})));
    const paths = calls().map(args => args[args.indexOf('-w') + 1]);
    assert.equal(new Set(paths).size, 8);
    assert.deepEqual(fs.readdirSync(outputDir), []);
  } finally { cleanup(); }
});

test('an engine failure rejects and leaves nothing behind', async () => {
  const { service, outputDir, cleanup } = await setup({ TTS_FAIL: '1' });
  try {
    await assert.rejects(service.synthesizeSpeech('hello', {}), /espeak failed/);
    assert.deepEqual(fs.readdirSync(outputDir), []);
  } finally { cleanup(); }
});

test('a missing engine reports itself unavailable', async () => {
  const restore = silenceConsole();
  try {
    const service = new LocalTTSService({ engine: 'espeak', espeakPath: '/nonexistent/espeak' });
    await service.checkAvailability();
    assert.equal(service.available(), false);
    await assert.rejects(service.synthesizeSpeech('hello'), /not available/);
    const unknown = new LocalTTSService({ engine: 'nonsense' });
    await unknown.checkAvailability();
    assert.equal(unknown.available(), false);
  } finally { restore(); }
});

test('festival: text cannot break out of the Scheme string', async () => {
  const restore = silenceConsole();
  const dir = tempDir();
  try {
    const stdinLog = path.join(dir, 'stdin.txt');
    process.env.FESTIVAL_STDIN = stdinLog;
    const festivalPath = writeNodeScript(dir, 'festival', `
      const fs = require('fs');
      if (process.argv[2] === '--version') process.exit(0);
      let input = '';
      process.stdin.on('data', d => input += d);
      process.stdin.on('end', () => {
        fs.writeFileSync(process.env.FESTIVAL_STDIN, input);
        const out = input.match(/utt\\.save\\.wave \\(utt\\.synth \\(Utterance Text ".*"\\)\\) "([^"]+)"/s);
        fs.writeFileSync(out[1], 'RIFFfake');
      });
    `);
    const service = new LocalTTSService({ engine: 'festival', festivalPath, outputDir: dir });
    await service.checkAvailability();

    const attack = 'a\\") (system "touch /tmp/pwned") (Utterance Text "b';   // a\") (system "touch ...") ...
    await service.synthesizeSpeech(attack, {});

    const scheme = fs.readFileSync(stdinLog, 'utf8');
    // every quote and backslash from the text is escaped, so the string literal is never closed early
    assert.ok(scheme.includes('Text "a\\\\\\") (system \\"touch /tmp/pwned\\") (Utterance Text \\"b"'), scheme);
  } finally {
    delete process.env.FESTIVAL_STDIN;
    restore();
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
