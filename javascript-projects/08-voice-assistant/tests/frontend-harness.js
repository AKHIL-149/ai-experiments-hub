/**
 * Runs the real public/app.js in a Node vm with a very small fake browser: DOM elements that
 * record listeners, a microphone whose readiness the test controls, a MediaRecorder, localStorage,
 * Audio, and a fetch that answers from a route table. Enough to test the page's behaviour
 * without a browser.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

class FakeElement {
  constructor(tag = 'div') {
    this.tagName = tag.toUpperCase();
    this.listeners = {};
    this.children = [];
    this.classes = new Set();
    this.classList = {
      add: (...c) => c.forEach(x => this.classes.add(x)),
      remove: (...c) => c.forEach(x => this.classes.delete(x)),
      contains: (c) => this.classes.has(c),
      toggle: (c) => (this.classes.has(c) ? this.classes.delete(c) : this.classes.add(c))
    };
    this.style = {};
    this.dataset = {};
    this.textContent = '';
    this.value = '';
    this.checked = false;
    this.options = [];
    this.scrollTop = 0;
    this.scrollHeight = 0;
    this.className = '';
    this.isContentEditable = false;
    this._queries = {};
  }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  dispatch(type, event = {}) {
    const e = { preventDefault() { this.defaultPrevented = true; }, defaultPrevented: false, target: this, ...event };
    (this.listeners[type] || []).forEach(fn => fn(e));
    return e;
  }
  appendChild(child) {
    this.children.push(child);
    if (this.tagName === 'SELECT') {
      this.options.push(child);
      if (this.options.length === 1) this.value = child.value;
    }
    return child;
  }
  set innerHTML(html) { this.children = []; this.options = []; this._html = html; }
  get innerHTML() { return this._html || ''; }
  remove() {}
  focus() { this.ownerDocument.activeElement = this; }
  blur() { this.ownerDocument.activeElement = this.ownerDocument.body; }
  querySelector(selector) {
    if (selector === '.message-placeholder') return null;
    if (!this._queries[selector]) {
      this._queries[selector] = new FakeElement('span');
      this._queries[selector].ownerDocument = this.ownerDocument;
    }
    return this._queries[selector];
  }
  querySelectorAll() { return []; }
}

/**
 * @param {Object} options
 *   routes   - { 'METHOD /path': (body) => ({ status, json, blob }) } overrides for the fake server
 *   micDelay - ms before getUserMedia resolves
 *   storage  - initial localStorage contents
 */
function loadApp(options = {}) {
  const calls = [];                       // every fetch: { method, url, body }
  const recorders = [];
  const streams = [];
  const played = [];
  const storage = { ...(options.storage || {}) };
  const timeouts = [];

  const document = new FakeElement('document');
  document.ownerDocument = document;
  document.body = new FakeElement('body');
  document.body.ownerDocument = document;
  document.activeElement = document.body;
  const elements = {};
  document.getElementById = (id) => {
    if (!elements[id]) {
      const tag = /Select$/.test(id) ? 'select' : /Toggle$|Slider$/.test(id) ? 'input' : /Btn$/.test(id) ? 'button' : 'div';
      elements[id] = new FakeElement(tag);
      elements[id].ownerDocument = document;
      elements[id].id = id;
    }
    return elements[id];
  };
  document.createElement = (tag) => { const el = new FakeElement(tag); el.ownerDocument = document; return el; };
  const domReady = [];
  const origAdd = document.addEventListener.bind(document);
  document.addEventListener = (type, fn) => { if (type === 'DOMContentLoaded') domReady.push(fn); else origAdd(type, fn); };

  const defaultRoutes = {
    'GET /api/health': () => ({ json: { status: 'ok', services: { mode: 'local', cloud: { available: false }, local: {} } } }),
    'GET /api/voices': () => ({ json: { voices: ['en', 'en-gb', 'fr'] } }),
    'POST /api/conversations': () => ({ json: { success: true, conversationId: 'conv_1793432160845_2d681ca6' } }),
    'POST /api/transcribe': () => ({ json: { transcript: 'what time is it', noSpeech: false } }),
    'POST /api/command': () => ({ json: { response: 'It is noon.', audio: Buffer.from('RIFFfake').toString('base64'), audioFormat: 'wav', timer: null } }),
    'POST /api/synthesize': () => ({ blob: new Blob(['RIFFfake']) }),
    'POST /api/service/mode': (body) => ({ json: { mode: body.mode, status: { mode: body.mode } } })
  };
  const routes = { ...defaultRoutes, ...(options.routes || {}) };

  const fetch = async (url, init = {}) => {
    const method = init.method || 'GET';
    let body = init.body;
    if (typeof body === 'string') { try { body = JSON.parse(body); } catch (e) { /* keep */ } }
    calls.push({ method, url, body });
    const handler = routes[`${method} ${url}`];
    if (!handler) return { ok: false, status: 404, json: async () => ({ error: 'no route' }) };
    const result = await handler(body);
    const status = result.status || 200;
    return {
      ok: status < 400, status,
      json: async () => { if (result.json === undefined) throw new Error('not json'); return result.json; },
      blob: async () => result.blob
    };
  };

  class FakeMediaRecorder {
    constructor(stream, opts) { this.stream = stream; this.mimeType = (opts && opts.mimeType) || ''; this.started = false; this.stopped = false; recorders.push(this); }
    static isTypeSupported(type) { return (options.supportedTypes || ['audio/webm']).includes(type); }
    start() { this.started = true; }
    stop() {
      this.stopped = true;
      setTimeout(() => {
        if (this.ondataavailable) this.ondataavailable({ data: new Blob([Buffer.alloc(options.recordingBytes ?? 4000)]) });
        if (this.onstop) this.onstop();
      }, 0);
    }
  }

  class FakeAudio {
    constructor(src) { this.src = src; played.push(this); }
    play() { setTimeout(() => this.onended && this.onended(), 0); return Promise.resolve(); }
  }

  const makeStream = () => {
    const track = { readyState: 'live', stop() { this.readyState = 'ended'; } };
    const stream = { tracks: [track], getTracks() { return this.tracks; } };
    streams.push(stream);
    return stream;
  };

  const context = {
    document, console: { log() {}, warn() {}, error() {} },
    navigator: { mediaDevices: { getUserMedia: async () => { await new Promise(r => setTimeout(r, options.micDelay || 0)); return makeStream(); } } },
    MediaRecorder: FakeMediaRecorder, Blob, FormData, URL: { createObjectURL: () => 'blob:fake', revokeObjectURL() {} },
    Audio: FakeAudio, fetch, atob: (s) => Buffer.from(s, 'base64').toString('binary'),
    localStorage: {
      getItem: (k) => (k in storage ? storage[k] : null),
      setItem: (k, v) => { storage[k] = String(v); },
      removeItem: (k) => { delete storage[k]; },
      clear: () => { for (const k of Object.keys(storage)) delete storage[k]; }
    },
    setTimeout: (fn, ms) => { const h = setTimeout(fn, ms); timeouts.push(h); return h; }, clearTimeout, setInterval, clearInterval,
    requestAnimationFrame: () => 0, cancelAnimationFrame() {},
    AudioContext: class { constructor() { throw new Error('no audio in tests'); } },
    Uint8Array, Date, Math, JSON, Promise, Array, Object, Set, Number, String, parseFloat, parseInt, isFinite, Error, Buffer
  };
  context.window = context;
  context.window.addEventListener = () => {};
  context.window.dispatchEvent = () => {};
  context.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init && init.detail; } };

  vm.createContext(context);
  const source = fs.readFileSync(path.join(__dirname, '../public/app.js'), 'utf8');
  vm.runInContext(`${source}\n;window.VoiceAssistant = VoiceAssistant;`, context);

  const app = {
    context, document, calls, recorders, streams, played, storage, elements,
    el: (id) => document.getElementById(id),
    async start() {
      domReady.forEach(fn => fn());
      await app.settle();
      return context.window.voiceAssistant;
    },
    /** Let pending promises and 0 ms timers run */
    settle: (ms = 30) => new Promise(r => setTimeout(r, ms)),
    messages: () => document.getElementById('conversationBox').children.map(m => m.children.map(c => c.textContent).join(': ')),
    cleanup() { timeouts.forEach(clearTimeout); }
  };
  return app;
}

module.exports = { loadApp };
