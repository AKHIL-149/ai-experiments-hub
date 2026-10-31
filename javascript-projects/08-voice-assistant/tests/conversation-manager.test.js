const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const ConversationManager = require('../src/ConversationManager');
const { tempDir, silenceConsole, ID_A, ID_B } = require('./helpers');

function setup(options = {}) {
  const restore = silenceConsole();
  const dir = tempDir();
  const manager = new ConversationManager({ storageDir: dir, ...options });
  return { dir, manager, cleanup: () => { restore(); fs.rmSync(dir, { recursive: true, force: true }); } };
}

test('isValidId accepts only the shape the manager generates', () => {
  assert.equal(ConversationManager.isValidId(ID_A), true);
  for (const bad of ['', 'conv_1_2', '../../package', 'conv_1793432160845_2d681ca6/../x', 'conv_1793432160845_2D681CA6',
    'conv_1793432160845_2d681ca6.json', 'x conv_1793432160845_2d681ca6', null, undefined, 42, {}, ['conv_1793432160845_2d681ca6']]) {
    assert.equal(ConversationManager.isValidId(bad), false, String(bad));
  }
  const { manager, cleanup } = setup();
  try {
    assert.equal(ConversationManager.isValidId(manager.createConversation().conversationId), true);
  } finally { cleanup(); }
});

test('an id with path parts can never reach a file outside the storage directory', () => {
  const { dir, manager, cleanup } = setup();
  try {
    const outside = path.join(dir, '..', `outside-${process.pid}.json`);
    fs.writeFileSync(outside, JSON.stringify({ messages: [], metadata: {} }));
    const traversal = `../outside-${process.pid}`;

    assert.equal(manager.deleteConversation(traversal), false);
    assert.equal(fs.existsSync(outside), true, 'file outside storage must survive');
    assert.equal(manager.getConversation(traversal), null);
    assert.equal(manager.clearMessages(traversal), false);
    assert.throws(() => manager.getConversationFilePath(traversal), /Invalid conversation id/);
    assert.throws(() => manager.addMessage(traversal, 'user', 'x'), /Invalid conversation id/);
    assert.throws(() => manager.createConversation('u', traversal), /Invalid conversation id/);
    fs.rmSync(outside);
  } finally { cleanup(); }
});

test('addMessage recreates a conversation whose id the client still holds', () => {
  const { manager, cleanup } = setup();
  try {
    manager.addMessage(ID_A, 'user', 'hello');
    manager.addMessage(ID_A, 'assistant', 'hi');
    assert.deepEqual(manager.getHistory(ID_A).map(m => m.content), ['hello', 'hi']);
    assert.equal(manager.getConversationInfo(ID_A).messageCount, 2);
  } finally { cleanup(); }
});

test('deleteConversation reports whether anything was deleted', () => {
  const { dir, manager, cleanup } = setup();
  try {
    const { conversationId } = manager.createConversation();
    assert.equal(manager.deleteConversation(conversationId), true);
    assert.equal(fs.existsSync(path.join(dir, `${conversationId}.json`)), false);
    assert.equal(manager.deleteConversation(conversationId), false);   // already gone
    assert.equal(manager.deleteConversation(ID_B), false);              // never existed
  } finally { cleanup(); }
});

test('conversations survive a restart (new manager, same directory)', () => {
  const { dir, manager, cleanup } = setup();
  try {
    manager.addMessage(ID_A, 'user', 'remember me');
    const second = new ConversationManager({ storageDir: dir });
    assert.deepEqual(second.getHistory(ID_A).map(m => m.content), ['remember me']);
  } finally { cleanup(); }
});

test('saving leaves no temp files and a crash cannot leave half a file', () => {
  const { dir, manager, cleanup } = setup();
  try {
    manager.addMessage(ID_A, 'user', 'x');
    assert.deepEqual(fs.readdirSync(dir), [`${ID_A}.json`]);
    JSON.parse(fs.readFileSync(path.join(dir, `${ID_A}.json`), 'utf8'));
  } finally { cleanup(); }
});

test('a file that is not a conversation is ignored, not trusted', () => {
  const { dir, manager, cleanup } = setup();
  try {
    fs.writeFileSync(path.join(dir, `${ID_A}.json`), JSON.stringify({ decoy: true }));
    fs.writeFileSync(path.join(dir, `${ID_B}.json`), '{ not json');
    fs.writeFileSync(path.join(dir, 'package.json'), '{}');
    fs.writeFileSync(path.join(dir, `${ID_A}.json.123.tmp`), '{}');

    assert.equal(manager.getConversation(ID_A), null);
    assert.equal(manager.getConversation(ID_B), null);
    assert.deepEqual(manager.listConversations(), []);
    assert.equal(manager.getStats().conversationCount, 2);   // the two id-shaped files; stray names are not counted
  } finally { cleanup(); }
});

test('listConversations: newest first, limit honoured, bad limits fall back', () => {
  const { manager, cleanup } = setup();
  try {
    manager.addMessage('conv_1793432160001_aaaaaaaa', 'user', 'old');
    manager.addMessage('conv_1793432160002_bbbbbbbb', 'user', 'new');
    manager.activeConversations.get('conv_1793432160001_aaaaaaaa').metadata.lastActivity = '2020-01-01T00:00:00.000Z';

    assert.deepEqual(manager.listConversations().map(c => c.conversationId),
      ['conv_1793432160002_bbbbbbbb', 'conv_1793432160001_aaaaaaaa']);
    assert.equal(manager.listConversations(1).length, 1);
    assert.equal(manager.listConversations(-3).length, 2);
    assert.equal(manager.listConversations(0).length, 2);
    assert.equal(manager.listConversations('abc').length, 2);
  } finally { cleanup(); }
});

test('history limit and context window', () => {
  const { manager, cleanup } = setup({ contextWindow: 3 });
  try {
    for (let i = 1; i <= 6; i++) manager.addMessage(ID_A, i % 2 ? 'user' : 'assistant', `m${i}`);
    assert.deepEqual(manager.getHistory(ID_A, 2).map(m => m.content), ['m5', 'm6']);
    assert.equal(manager.getHistory(ID_A, -1).length, 6);
    assert.equal(manager.getHistory(ID_A, 'abc').length, 6);
    assert.deepEqual(manager.getContext(ID_A), [
      { role: 'assistant', content: 'm4' }, { role: 'user', content: 'm5' }, { role: 'assistant', content: 'm6' }
    ]);
  } finally { cleanup(); }
});

test('old messages are trimmed beyond maxConversationLength', () => {
  const { manager, cleanup } = setup({ maxConversationLength: 4 });
  try {
    for (let i = 1; i <= 7; i++) manager.addMessage(ID_A, 'user', `m${i}`);
    assert.deepEqual(manager.getHistory(ID_A).map(m => m.content), ['m4', 'm5', 'm6', 'm7']);
  } finally { cleanup(); }
});

test('clearMessages empties a conversation but keeps it', () => {
  const { manager, cleanup } = setup();
  try {
    manager.addMessage(ID_A, 'user', 'x');
    assert.equal(manager.clearMessages(ID_A), true);
    assert.equal(manager.getConversationInfo(ID_A).messageCount, 0);
    assert.equal(manager.clearMessages(ID_B), false);
  } finally { cleanup(); }
});

test('userId is stored as a short string only', () => {
  const { manager, cleanup } = setup();
  try {
    const a = manager.createConversation({ a: 1 }).conversationId;
    const b = manager.createConversation('x'.repeat(500)).conversationId;
    const c = manager.createConversation('  alice ').conversationId;
    assert.equal(manager.getConversationInfo(a).userId, 'default');
    assert.equal(manager.getConversationInfo(b).userId.length, 64);
    assert.equal(manager.getConversationInfo(c).userId, 'alice');
  } finally { cleanup(); }
});

test('cleanupOldConversations deletes only old conversation files', () => {
  const { dir, manager, cleanup } = setup();
  try {
    manager.addMessage(ID_A, 'user', 'old');
    manager.addMessage(ID_B, 'user', 'fresh');
    fs.writeFileSync(path.join(dir, 'notes.json'), '{}');
    const longAgo = new Date(Date.now() - 10 * 24 * 3600 * 1000);
    fs.utimesSync(path.join(dir, `${ID_A}.json`), longAgo, longAgo);
    fs.utimesSync(path.join(dir, 'notes.json'), longAgo, longAgo);

    assert.equal(manager.cleanupOldConversations(7 * 24 * 3600 * 1000), 1);
    assert.equal(fs.existsSync(path.join(dir, `${ID_A}.json`)), false);
    assert.equal(fs.existsSync(path.join(dir, `${ID_B}.json`)), true);
    assert.equal(fs.existsSync(path.join(dir, 'notes.json')), true, 'stray files are not ours to delete');
  } finally { cleanup(); }
});

test('unloadInactive drops idle conversations from memory but not from disk', () => {
  const { manager, cleanup } = setup();
  try {
    manager.addMessage(ID_A, 'user', 'x');
    manager.activeConversations.get(ID_A).metadata.lastActivity = new Date(Date.now() - 3600 * 1000).toISOString();
    assert.equal(manager.unloadInactive(30 * 60 * 1000), 1);
    assert.equal(manager.activeConversations.size, 0);
    assert.equal(manager.getHistory(ID_A).length, 1);   // reloaded from disk
  } finally { cleanup(); }
});
