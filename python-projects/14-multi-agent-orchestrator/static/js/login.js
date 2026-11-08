(function () {
    'use strict';
    const STORE_KEY = 'orchestrator.session';
    const $ = id => document.getElementById(id);

    // Only same-site paths: /login?next=//evil.example must not send you away after signing in
    function safeNext() {
        const next = new URLSearchParams(location.search).get('next') || '/dashboard';
        return /^\/(?![\/\\])/.test(next) && !next.startsWith('/login') ? next : '/dashboard';
    }

    function finish(session) {
        try { localStorage.setItem(STORE_KEY, JSON.stringify(session)); } catch (e) {
            showError('si-error', 'This browser blocks storage, so it cannot stay signed in.'); return;
        }
        location.replace(safeNext());
    }

    // Already signed in on this device? Go straight on.
    try {
        const existing = JSON.parse(localStorage.getItem(STORE_KEY));
        if (existing && existing.access_token) {
            fetch('/api/auth/me', { headers: { Authorization: 'Bearer ' + existing.access_token } })
                .then(response => { if (response.ok) location.replace(safeNext()); else localStorage.removeItem(STORE_KEY); })
                .catch(() => {});
        }
    } catch (e) { /* no storage */ }

    const reason = new URLSearchParams(location.search).get('reason');
    const notices = {
        signed_out: 'You were signed out on this device.',
        expired: 'Your sign-in expired. Please sign in again.',
    };
    if (notices[reason]) { $('notice').textContent = notices[reason]; $('notice').hidden = false; }

    function showError(id, text) { $(id).textContent = text; }

    async function post(path, body) {
        const response = await fetch(path, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined,
        });
        let data = null;
        try { data = await response.json(); } catch (e) { /* no body */ }
        if (!response.ok) {
            let detail = data && data.detail;
            if (Array.isArray(detail)) detail = 'Please check what you entered';
            throw new Error(detail || 'Something went wrong (' + response.status + ')');
        }
        return data;
    }

    function submitting(form, work) {
        form.addEventListener('submit', async event => {
            event.preventDefault();
            const button = form.querySelector('button[type=submit]');
            button.disabled = true;
            try { await work(); } finally { button.disabled = false; }
        });
    }

    submitting($('form-signin'), async () => {
        showError('si-error', '');
        try {
            finish(await post('/api/auth/login', { username: $('si-username').value, password: $('si-password').value }));
        } catch (e) { showError('si-error', e.message); }
    });

    submitting($('form-register'), async () => {
        showError('rg-error', '');
        try {
            finish(await post('/api/auth/register', {
                username: $('rg-username').value, password: $('rg-password').value, email: $('rg-email').value.trim() || null,
            }));
        } catch (e) { showError('rg-error', e.message); }
    });

    $('guest-btn').addEventListener('click', async event => {
        const button = event.currentTarget;
        button.disabled = true;
        try { finish(await post('/api/auth/guest')); }
        catch (e) { showError(!$('form-signin').hidden ? 'si-error' : 'rg-error', e.message); }
        finally { button.disabled = false; }
    });

    function selectTab(name) {
        const signin = name === 'signin';
        $('form-signin').hidden = !signin; $('form-register').hidden = signin;
        $('tab-signin').classList.toggle('active', signin); $('tab-register').classList.toggle('active', !signin);
        $('tab-signin').setAttribute('aria-selected', String(signin)); $('tab-register').setAttribute('aria-selected', String(!signin));
        (signin ? $('si-username') : $('rg-username')).focus();
    }
    $('tab-signin').addEventListener('click', () => selectTab('signin'));
    $('tab-register').addEventListener('click', () => selectTab('register'));
})();
