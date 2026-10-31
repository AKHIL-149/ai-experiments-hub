const fs = require('fs');
const os = require('os');
const path = require('path');

/** A fresh empty directory under the system temp dir */
function tempDir(prefix = 'voice-assistant-test-') {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

/** Write an executable shell script (stand-in for ffmpeg, whisper, espeak ...) */
function writeScript(dir, name, body) {
  const file = path.join(dir, name);
  fs.writeFileSync(file, `#!/bin/sh\n${body}\n`);
  fs.chmodSync(file, 0o755);
  return file;
}

/** Write an executable Node script (a stand-in that can do real logic) */
function writeNodeScript(dir, name, code) {
  const file = path.join(dir, name);
  fs.writeFileSync(file, `#!/usr/bin/env node\n${code}\n`);
  fs.chmodSync(file, 0o755);
  return file;
}

/**
 * Mute console output for the whole test process. The services log a lot, and some of it comes
 * from background checks that finish after a test has returned. Node's test runner receives
 * its results over the same stdout, so a stray console.log can corrupt that stream and fail an
 * unrelated test file ("Unable to deserialize cloned data") - rarely, which makes it flaky.
 * Tests that need to look at output replace console.* themselves.
 */
for (const level of ['log', 'info', 'warn', 'debug']) {
  console[level] = () => {};
}

/** Quiet console output while a test runs (kept for tests that spy on or restore the console) */
function silenceConsole() {
  const originals = {};
  for (const level of ['log', 'warn', 'error']) {
    originals[level] = console[level];
    console[level] = () => {};
  }
  return () => Object.assign(console, originals);
}

const ID_A = 'conv_1793432160845_2d681ca6';
const ID_B = 'conv_1793432160846_2d681ca7';

module.exports = { tempDir, writeScript, writeNodeScript, silenceConsole, ID_A, ID_B };
