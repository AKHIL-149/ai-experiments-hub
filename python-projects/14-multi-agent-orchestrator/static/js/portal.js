/*
 * Sign-in portal for the dashboard: keeps the device signed in, adds the token to API calls, shows who
 * is online right now (live, over a WebSocket) and lets you manage your devices.
 *
 * Tokens live in this browser's localStorage, so every device/browser has its own sign-in.
 */
(function () {
    'use strict';

    const STORE_KEY = 'orchestrator.session';

    // ---- helpers ---------------------------------------------------------------------------
    window.esc = function (value) {
        return String(value === null || value === undefined ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    };

    function el(tag, props, children) {
        const node = document.createElement(tag);
        Object.entries(props || {}).forEach(([key, value]) => {
            if (key === 'class') node.className = value;
            else if (key === 'text') node.textContent = value;
            else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
            else node.setAttribute(key, value);
        });
        (children || []).forEach(child => child && node.appendChild(child));
        return node;
    }

    function put(parent, ...nodes) {
        nodes.forEach(node => node && parent.append(node));
        return parent;
    }

    function load() {
        try { return JSON.parse(localStorage.getItem(STORE_KEY)); } catch (e) { return null; }
    }
    function save(session) {
        try { localStorage.setItem(STORE_KEY, JSON.stringify(session)); } catch (e) { /* private mode */ }
    }
    function clear() {
        try { localStorage.removeItem(STORE_KEY); } catch (e) { /* ignore */ }
    }

    let session = load();

    function goToLogin(reason) {
        clear();
        const next = location.pathname + location.search;
        const params = new URLSearchParams({ next });
        if (reason) params.set('reason', reason);
        location.replace('/login?' + params.toString());
    }

    if (!session || !session.access_token) {
        goToLogin();
        return;
    }

    // ---- authenticated fetch -----------------------------------------------------------------
    const nativeFetch = window.fetch.bind(window);
    const PUBLIC = ['/api/auth/login', '/api/auth/register', '/api/auth/guest', '/api/auth/refresh'];
    let refreshing = null;

    function isApiCall(input) {
        const url = new URL(typeof input === 'string' ? input : input.url, location.href);
        return url.origin === location.origin && url.pathname.startsWith('/api/') && !PUBLIC.includes(url.pathname);
    }

    function refreshTokens() {
        if (!refreshing) {
            refreshing = nativeFetch('/api/auth/refresh', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: session.refresh_token }),
            }).then(async response => {
                if (!response.ok) throw new Error('refresh failed');
                const data = await response.json();
                session = Object.assign({}, session, data);
                save(session);
                return session.access_token;
            }).finally(() => { refreshing = null; });
        }
        return refreshing;
    }

    window.fetch = async function (input, init) {
        if (!isApiCall(input)) return nativeFetch(input, init);

        const send = token => {
            const headers = new Headers((init && init.headers) || (typeof input !== 'string' ? input.headers : undefined));
            headers.set('Authorization', 'Bearer ' + token);
            return nativeFetch(input, Object.assign({}, init, { headers }));
        };

        let response = await send(session.access_token);
        if (response.status === 401) {
            try {
                response = await send(await refreshTokens());
            } catch (e) {
                goToLogin('expired');
                return response;
            }
            if (response.status === 401) goToLogin('expired');
        }
        return response;
    };

    // ---- live presence -----------------------------------------------------------------------
    const state = { online: [], activity: [], me: session.user || null, socket: null, retry: 0, connected: false };
    let ui = null;

    function connectPresence() {
        const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
        const socket = new WebSocket(scheme + '://' + location.host + '/api/ws/presence');
        state.socket = socket;
        let pingTimer = null;

        socket.addEventListener('open', async () => {
            // the token goes in the first message, not in the URL
            let token = session.access_token;
            try { token = await refreshTokens(); } catch (e) { /* use the current one */ }
            socket.send(JSON.stringify({ type: 'auth', token }));
        });

        socket.addEventListener('message', event => {
            let message;
            try { message = JSON.parse(event.data); } catch (e) { return; }
            if (message.type === 'session_revoked') { goToLogin('signed_out'); return; }
            if (message.type === 'pong') return;
            if (message.type === 'ready') {
                state.connected = true; state.retry = 0; state.me = message.me;
                pingTimer = setInterval(() => socket.readyState === 1 && socket.send('{"type":"ping"}'), 20000);
            }
            if (message.online) {
                state.online = message.online;
                state.activity = message.activity || state.activity;
            }
            if (message.type === 'activity' && message.event && message.event.username !== (state.me || {}).username) toast(describe(message.event));
            render();
        });

        socket.addEventListener('close', event => {
            clearInterval(pingTimer);
            state.connected = false;
            render();
            if (event.code === 4401) { goToLogin('signed_out'); return; }
            state.retry = Math.min(state.retry + 1, 6);
            setTimeout(connectPresence, Math.min(15000, 1000 * Math.pow(2, state.retry)));
        });
    }

    function describe(event) {
        const who = event.username + (event.is_guest ? ' (guest)' : '');
        return {
            online: who + ' is online',
            offline: who + ' went offline',
            joined: who + ' created an account',
            guest: who + ' joined as a guest',
        }[event.kind] || (who + ' ' + event.kind);
    }

    // ---- interface ---------------------------------------------------------------------------
    function toast(text) {
        if (!ui) return;
        const item = el('div', { class: 'portal-toast', text });
        ui.toasts.appendChild(item);
        setTimeout(() => item.remove(), 4000);
    }

    function relativeTime(iso) {
        const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
        if (seconds < 60) return 'just now';
        if (seconds < 3600) return Math.round(seconds / 60) + ' min ago';
        if (seconds < 86400) return Math.round(seconds / 3600) + ' h ago';
        return Math.round(seconds / 86400) + ' d ago';
    }

    function badge(text, kind) { return el('span', { class: 'portal-badge ' + (kind || ''), text }); }

    async function api(path, options) {
        const response = await fetch(path, options);
        if (!response.ok) {
            let detail = 'Request failed (' + response.status + ')';
            try { detail = (await response.json()).detail || detail; } catch (e) { /* not JSON */ }
            throw new Error(typeof detail === 'string' ? detail : 'Please check what you entered');
        }
        return response.status === 204 ? null : response.json();
    }

    async function signOut() {
        try { await api('/api/auth/logout', { method: 'POST' }); } catch (e) { /* already ended */ }
        goToLogin();
    }

    function renderDevices(container) {
        api('/api/auth/sessions').then(devices => {
            container.replaceChildren(...devices.map(device => el('li', {}, [
                el('span', { class: 'portal-device', text: device.device || 'Unknown device' }),
                device.current ? badge('this device', 'self') : null,
                el('span', { class: 'portal-muted', text: relativeTime(device.last_seen_at) }),
                device.current ? null : el('button', {
                    class: 'portal-link', text: 'Sign out',
                    onclick: async () => { await api('/api/auth/sessions/' + device.id, { method: 'DELETE' }); renderDevices(container); },
                }),
            ])));
        }).catch(() => container.replaceChildren(el('li', { class: 'portal-muted', text: 'Could not load devices' })));
    }

    function guestUpgradeForm() {
        const username = el('input', { placeholder: 'Choose a username', autocomplete: 'username', maxlength: 30 });
        const password = el('input', { placeholder: 'Choose a password', type: 'password', autocomplete: 'new-password' });
        const error = el('div', { class: 'portal-error', role: 'alert' });
        const form = el('form', { class: 'portal-upgrade' }, [
            el('p', { class: 'portal-muted', text: 'You are a guest: this account is removed after a day without use. Create an account to keep your tasks.' }),
            username, password, error,
            el('button', { type: 'submit', class: 'portal-primary', text: 'Create account' }),
        ]);
        form.addEventListener('submit', async event => {
            event.preventDefault();
            error.textContent = '';
            try {
                const result = await api('/api/auth/guest/upgrade', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: username.value, password: password.value }),
                });
                session.user = result.user; save(session); state.me = result.user;
                render(true);
            } catch (e) { error.textContent = e.message; }
        });
        return form;
    }

    function buildUi() {
        const bar = el('div', { id: 'portal-bar', class: 'portal-bar' });
        const live = el('button', { class: 'portal-live', type: 'button', 'aria-haspopup': 'true' });
        const chip = el('button', { class: 'portal-chip', type: 'button', 'aria-haspopup': 'true' });
        const panel = el('div', { class: 'portal-panel', hidden: '' });
        const toasts = el('div', { class: 'portal-toasts', 'aria-live': 'polite' });
        bar.append(live, chip, panel);
        document.body.prepend(bar);
        document.body.append(toasts);

        const toggle = () => { panel.hidden = !panel.hidden; if (!panel.hidden) render(true); };
        live.addEventListener('click', toggle);
        chip.addEventListener('click', toggle);
        document.addEventListener('click', event => { if (!bar.contains(event.target)) panel.hidden = true; });
        document.addEventListener('keydown', event => { if (event.key === 'Escape') panel.hidden = true; });
        return { bar, live, chip, panel, toasts };
    }

    function render(rebuildPanel) {
        if (!ui) return;
        const me = state.me || {};
        ui.live.className = 'portal-live' + (state.connected ? ' is-live' : '');
        ui.live.textContent = '';
        put(ui.live, el('span', { class: 'portal-dot' }),
            document.createTextNode(state.connected ? state.online.length + ' online' : 'reconnecting…'));
        ui.chip.textContent = '';
        put(ui.chip, el('span', { class: 'portal-avatar', text: (me.username || '?').charAt(0).toUpperCase() }),
            el('span', { text: me.username || '' }), me.is_guest ? badge('Guest', 'guest') : null);

        if (ui.panel.hidden) return;
        // keep the sections that do not change with presence (devices, forms) while the panel is open
        let online = ui.panel.querySelector('.portal-online');
        if (!online || rebuildPanel) {
            ui.panel.textContent = '';
            const devices = el('ul', { class: 'portal-list portal-devices' });
            put(ui.panel,
                el('h4', { text: 'Online now' }), el('ul', { class: 'portal-list portal-online' }),
                el('h4', { text: 'Live activity' }), el('ul', { class: 'portal-list portal-activity' }),
                el('h4', { text: 'Your devices' }), devices,
                el('button', { class: 'portal-link', text: 'Sign out other devices', onclick: async () => {
                    await api('/api/auth/sessions/revoke-others', { method: 'POST' }); renderDevices(devices); } }),
                me.is_guest ? guestUpgradeForm() : null,
                el('button', { class: 'portal-signout', text: 'Sign out', onclick: signOut }));
            renderDevices(devices);
            online = ui.panel.querySelector('.portal-online');
        }
        online.replaceChildren(...state.online.map(user => el('li', {}, [
            el('span', { class: 'portal-dot is-on' }),
            el('span', { text: user.username }),
            user.is_guest ? badge('Guest', 'guest') : null,
            user.id === me.id ? badge('you', 'self') : null,
            user.devices > 1 ? el('span', { class: 'portal-muted', text: user.devices + ' devices' }) : null,
        ])));
        ui.panel.querySelector('.portal-activity').replaceChildren(
            ...state.activity.slice().reverse().slice(0, 8).map(event => el('li', {}, [
                el('span', { text: describe(event) }),
                el('span', { class: 'portal-muted', text: relativeTime(event.at) }),
            ])));
    }

    window.Portal = { session: () => session, signOut, state };

    document.addEventListener('DOMContentLoaded', () => {
        ui = buildUi();
        render();
        connectPresence();
        // confirm the sign-in is still good (an expired one goes back to the login page)
        api('/api/auth/me').then(me => { state.me = me; render(); }).catch(() => {});
    });
})();
