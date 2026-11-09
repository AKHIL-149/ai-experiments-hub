// Sign-in page. Everything the server sends is shown with textContent, never as HTML.
(function () {
    'use strict';
    const $ = (id) => document.getElementById(id);
    let mode = 'signin';
    let config = { registration: true, guests: true, guest_ttl_hours: 24, guest_max_videos: 3, min_password: 8 };

    // Only same-site paths are followed after sign-in ("/login?next=//evil.example" must not redirect away)
    function nextUrl() {
        const next = new URLSearchParams(location.search).get('next') || '/';
        return /^\/(?![\/\\])/.test(next) ? next : '/';
    }

    function showError(message) {
        const box = $('login-error');
        box.textContent = message || '';
        box.hidden = !message;
    }

    function setMode(newMode) {
        mode = newMode;
        const register = mode === 'register';
        $('tab-signin').classList.toggle('active', !register);
        $('tab-register').classList.toggle('active', register);
        $('tab-signin').setAttribute('aria-selected', String(!register));
        $('tab-register').setAttribute('aria-selected', String(register));
        $('name-row').hidden = !register;
        $('password-hint').hidden = !register;
        $('password').autocomplete = register ? 'new-password' : 'current-password';
        $('submit').textContent = register ? 'Create account' : 'Sign in';
        showError('');
    }

    async function post(path, body) {
        const response = await fetch(path, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {}),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const detail = data.detail;
            throw new Error(typeof detail === 'string' ? detail : 'Something went wrong, please try again');
        }
        return data;
    }

    async function submit(event) {
        event.preventDefault();
        showError('');
        const button = $('submit');
        button.disabled = true;
        try {
            await post(mode === 'register' ? '/api/auth/register' : '/api/auth/login', {
                username: $('username').value,
                password: $('password').value,
                display_name: $('display-name').value || null,
            });
            location.replace(nextUrl());
        } catch (error) {
            showError(error.message);
            button.disabled = false;
        }
    }

    async function guest() {
        showError('');
        $('guest-btn').disabled = true;
        try {
            await post('/api/auth/guest');
            location.replace(nextUrl());
        } catch (error) {
            showError(error.message);
            $('guest-btn').disabled = false;
        }
    }

    async function start() {
        try {
            const response = await fetch('/api/auth/config', { credentials: 'same-origin' });
            if (response.ok) config = await response.json();
        } catch (e) { /* the defaults are fine */ }

        // Already signed in (or login is switched off): go straight to the app
        try {
            const me = await fetch('/api/auth/me', { credentials: 'same-origin' });
            if (me.ok) { location.replace(nextUrl()); return; }
        } catch (e) { /* show the form */ }

        $('tab-register').hidden = !config.registration;
        $('password-hint').textContent = 'At least ' + config.min_password + ' characters.';
        if (config.guests) {
            $('guest-box').hidden = false;
            $('guest-note').textContent = 'Guests can keep ' + config.guest_max_videos + ' videos; they are deleted after '
                + config.guest_ttl_hours + ' hours unless you create an account.';
        }
        $('tab-signin').addEventListener('click', () => setMode('signin'));
        $('tab-register').addEventListener('click', () => setMode('register'));
        $('login-form').addEventListener('submit', submit);
        $('guest-btn').addEventListener('click', guest);
    }

    start();
})();
