/*
 * Workflow tracker: lists your workflows with live progress and shows, step by step, which agent ran each
 * one and what it produced. Everything is set as text, never parsed as HTML, because step results
 * are text written by a language model.
 */
(function () {
    'use strict';

    const FILTERS = [['', 'All'], ['running', 'Running'], ['pending', 'Pending'], ['completed', 'Completed'], ['failed', 'Failed'], ['cancelled', 'Cancelled']];
    const FAST_POLL_MS = 3000;
    const SLOW_POLL_MS = 12000;
    const LONG_TEXT = 700;

    const state = {
        filter: '',
        selected: null,
        workflows: [],
        listKey: '',
        detail: null,
        detailKey: '',
        notice: '',
        busy: false,
        ui: {},          // per workflow: { stepId: { more, raw } } so a refresh does not collapse what you opened
    };

    const $ = id => document.getElementById(id);

    // ---- small helpers ----------------------------------------------------------------------
    function h(tag, props, ...children) {
        const node = document.createElement(tag);
        Object.entries(props || {}).forEach(([key, value]) => {
            if (value === null || value === undefined || value === false) return;
            if (key === 'class') node.className = value;
            else if (key === 'text') node.textContent = value;
            else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
            else node.setAttribute(key, value === true ? '' : value);
        });
        children.flat().forEach(child => {
            if (child === null || child === undefined || child === false) return;
            node.append(child.nodeType ? child : document.createTextNode(String(child)));
        });
        return node;
    }

    function duration(seconds) {
        if (seconds === null || seconds === undefined) return '–';
        if (seconds < 60) return (seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)) + 's';
        const minutes = Math.floor(seconds / 60);
        if (minutes < 60) return minutes + 'm ' + String(Math.round(seconds % 60)).padStart(2, '0') + 's';
        return Math.floor(minutes / 60) + 'h ' + String(minutes % 60).padStart(2, '0') + 'm';
    }

    function when(iso) {
        if (!iso) return '–';
        const date = new Date(iso);
        if (isNaN(date)) return '–';
        const ago = Math.round((Date.now() - date.getTime()) / 1000);
        if (ago >= 0 && ago < 60) return 'just now';
        if (ago >= 0 && ago < 3600) return Math.round(ago / 60) + ' min ago';
        return date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    }

    function badge(status) { return h('span', { class: 'tk-badge ' + status, text: status }); }

    function progressBar(progress, large) {
        return h('div', { class: 'tk-bar' + (large ? ' large' : '') + (progress.failed ? ' has-failed' : ''), role: 'progressbar',
            'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': Math.round(progress.percentage) },
            h('span', { style: 'width:' + Math.max(0, Math.min(100, progress.percentage)) + '%' }));
    }

    async function api(path, options) {
        const response = await fetch(path, options);
        if (!response.ok) {
            let detail = 'Request failed (' + response.status + ')';
            try { const body = await response.json(); if (typeof body.detail === 'string') detail = body.detail; } catch (e) { /* not JSON */ }
            const error = new Error(detail); error.status = response.status; throw error;
        }
        return response.json();
    }

    async function copy(text, button) {
        try { await navigator.clipboard.writeText(text); } catch (e) {
            const area = h('textarea', { style: 'position:fixed;opacity:0' }); area.value = text; document.body.append(area); area.select();
            try { document.execCommand('copy'); } catch (err) { /* ignore */ } area.remove();
        }
        const original = button.textContent; button.textContent = 'Copied'; setTimeout(() => { button.textContent = original; }, 1200);
    }

    const stepUi = (workflowId, stepId) => {
        state.ui[workflowId] = state.ui[workflowId] || {};
        return (state.ui[workflowId][stepId] = state.ui[workflowId][stepId] || { more: false, raw: false });
    };

    // ---- formatted text (markdown) ------------------------------------------------------------
    function inlineNodes(tokens) {
        return tokens.map(token => {
            if (token.t === 'code') return h('code', { text: token.v });
            if (token.t === 'strong') return h('strong', {}, ...inlineNodes(token.c));
            if (token.t === 'em') return h('em', {}, ...inlineNodes(token.c));
            if (token.t === 'link') return h('a', { href: token.href, target: '_blank', rel: 'noopener noreferrer', text: token.v });
            return document.createTextNode(token.v);
        });
    }

    function formatted(text) {
        const blocks = window.TrackerMarkdown.parse(text).map(block => {
            if (block.type === 'heading') return h('h4', {}, ...inlineNodes(block.inline));
            if (block.type === 'code') return h('pre', { class: 'tk-code' }, h('code', { text: block.text }));
            if (block.type === 'list') {
                return h(block.ordered ? 'ol' : 'ul', {}, ...block.items.map(item =>
                    h('li', { class: 'lvl-' + item.level }, ...inlineNodes(item.inline))));
            }
            const parts = [];
            block.lines.forEach((tokens, index) => { if (index) parts.push(h('br')); parts.push(...inlineNodes(tokens)); });
            return h('p', {}, ...parts);
        });
        return h('div', { class: 'tk-md' }, ...blocks);
    }

    // ---- list -------------------------------------------------------------------------------
    function renderFilters() {
        $('tkFilters').replaceChildren(...FILTERS.map(([value, label]) => h('button', {
            class: 'tk-chip', type: 'button', 'aria-pressed': String(state.filter === value), text: label,
            onclick: () => { state.filter = value; state.listKey = ''; renderFilters(); refresh(); },
        })));
    }

    function renderList() {
        const list = $('tkList'), empty = $('tkListEmpty');
        empty.hidden = state.workflows.length > 0;
        if (!state.workflows.length) {
            empty.replaceChildren(document.createTextNode(state.filter ? 'No ' + state.filter + ' workflows.' : 'No workflows yet. '),
                state.filter ? '' : h('a', { href: '/dashboard', text: 'Create one on the dashboard' }));
        }
        list.replaceChildren(...state.workflows.map(workflow => h('li', {},
            h('button', { class: 'tk-item', type: 'button', 'aria-current': String(workflow.id === state.selected),
                onclick: () => select(workflow.id) },
                h('div', { class: 'tk-item-top' }, h('span', { class: 'tk-item-name', text: workflow.name }), badge(workflow.status)),
                progressBar(workflow.progress),
                h('div', { class: 'tk-item-sub' },
                    h('span', { text: workflow.progress.completed + '/' + workflow.progress.total + ' steps' + (workflow.current_step ? ' · ' + workflow.current_step : '') }),
                    h('span', { text: when(workflow.timeline.created_at) }))))));
    }

    // ---- detail -----------------------------------------------------------------------------
    function resultBlock(step, workflowId) {
        const ui = stepUi(workflowId, step.step_id);
        const out = step.output || {};
        const parts = [];

        if (step.status === 'failed' || (step.error && step.status !== 'completed')) {
            parts.push(h('div', { class: 'tk-result-label', text: 'Error' }), h('div', { class: 'tk-error', text: step.error || 'The step failed.' }));
        }
        if (out.text) {
            const long = out.text.length > LONG_TEXT;
            parts.push(
                h('div', { class: 'tk-result-label' }, h('span', { text: 'Result' }),
                    h('button', { class: 'tk-link', type: 'button', text: 'Copy', onclick: event => copy(out.text, event.target) })),
                h('div', { class: 'tk-text' + (long && !ui.more ? ' tk-clamp' : '') }, formatted(out.text)));
            if (long) parts.push(h('button', { class: 'tk-link', type: 'button', text: ui.more ? 'Show less' : 'Show more',
                onclick: () => { ui.more = !ui.more; renderDetail(true); } }));
        }
        if (out.code) {
            const long = out.code.split('\n').length > 18;
            parts.push(
                h('div', { class: 'tk-result-label' }, h('span', { text: 'Code' + (out.language ? ' · ' + out.language : '') }),
                    h('button', { class: 'tk-link', type: 'button', text: 'Copy', onclick: event => copy(out.code, event.target) })),
                h('pre', { class: 'tk-code' + (long && !ui.more ? ' tk-clamp' : '') }, h('code', { text: out.code })));
            if (long) parts.push(h('button', { class: 'tk-link', type: 'button', text: ui.more ? 'Show less' : 'Show more',
                onclick: () => { ui.more = !ui.more; renderDetail(true); } }));
        }
        if (out.explanation) {
            parts.push(h('div', { class: 'tk-result-label', text: 'Explanation' }), h('div', { class: 'tk-text' }, formatted(out.explanation)));
        }
        if (out.raw) {
            const metrics = out.metrics || {};
            const bits = [];
            if (metrics.tokens_used !== undefined) bits.push(metrics.tokens_used + ' tokens');
            if (metrics.word_count !== undefined) bits.push(metrics.word_count + ' words');
            if (metrics.cost) bits.push('$' + Number(metrics.cost).toFixed(4));
            parts.push(h('div', { class: 'tk-metrics' }, ...bits.map(text => h('span', { text })),
                h('button', { class: 'tk-link', type: 'button', text: ui.raw ? 'Hide raw output' : 'Raw output',
                    onclick: () => { ui.raw = !ui.raw; renderDetail(true); } })));
            if (ui.raw) parts.push(h('pre', { class: 'tk-code', text: JSON.stringify(out.raw, null, 2) }));
        }

        if (!parts.length) {
            const waitingOn = (step.depends_on || []).map(d => d.name).join(', ');
            const message = {
                running: 'Running now…',
                pending: waitingOn ? 'Waiting for ' + waitingOn + '.' : 'Waiting to start.',
                completed: 'Finished without any output.',
                skipped: 'This step was skipped.',
            }[step.status];
            if (message) parts.push(h('p', { class: 'tk-waiting', text: message }));
        }
        return parts;
    }

    function stepCard(step, workflowId) {
        const task = step.task;
        const meta = [h('span', {}, 'Agent type ', h('b', { text: step.agent_type || '–' }))];
        if (task) {
            meta.push(h('span', {}, 'Ran by ', h('b', { text: task.agent_name || (task.agent_id ? 'agent ' + task.agent_id : 'not assigned') })));
            meta.push(h('span', {}, 'Task ', h('b', { text: '#' + task.id })));
            if (task.duration_seconds !== null) meta.push(h('span', {}, 'Took ', h('b', { text: duration(task.duration_seconds) })));
            else if (task.started_at && step.status === 'running') meta.push(h('span', {}, 'Started ', h('b', { text: when(task.started_at) })));
        }
        if (step.attempts > 1) meta.push(h('span', {}, 'Attempts ', h('b', { text: String(step.attempts) })));
        if (step.depends_on.length) meta.push(h('span', {}, 'After ', h('b', { text: step.depends_on.map(d => d.name).join(', ') })));

        return h('li', { class: 'tk-step is-' + step.status },
            h('div', { class: 'tk-num', text: String(step.number) }),
            h('article', { class: 'tk-card' },
                h('div', { class: 'tk-card-head' }, h('h3', { text: step.name }), badge(step.status)),
                h('div', { class: 'tk-meta' }, ...meta),
                step.description ? h('div', { class: 'tk-asked', text: step.description }) : null,
                ...resultBlock(step, workflowId)));
    }

    async function act(label, run) {
        if (state.busy) return;
        state.busy = true; state.notice = ''; renderDetail(true);
        try { await run(); } catch (error) { state.notice = label + ' failed: ' + error.message; }
        state.busy = false;
        await refresh(true);
        schedule();
    }

    function renderDetail(force) {
        const pane = $('tkDetail');
        $('tkLayout').classList.toggle('has-selection', state.selected !== null);
        const detail = state.detail;
        if (!detail || detail.id !== state.selected) {
            pane.replaceChildren(state.selected === null
                ? h('p', { class: 'tk-empty', text: 'Select a workflow to see its steps and results.' })
                : h('p', { class: 'tk-empty', text: state.notice || 'Loading…' }));
            return;
        }

        const p = detail.progress, t = detail.timeline, id = detail.id;
        const startable = detail.status === 'pending';
        const cancellable = ['pending', 'running', 'paused'].includes(detail.status);
        const finished = ['completed', 'failed', 'cancelled'].includes(detail.status);
        const scroll = window.scrollY;

        // replaceChildren turns a null child into the text "null", so empty slots are filtered out
        pane.replaceChildren(...[
            h('button', { class: 'tk-btn tk-mobile-back', type: 'button', text: '← All workflows', onclick: () => select(null) }),
            h('div', { class: 'tk-title-row' }, h('h2', { text: detail.name }), badge(detail.status)),
            detail.description ? h('p', { class: 'tk-desc', text: detail.description }) : null,
            h('div', { class: 'tk-actions' },
                startable ? h('button', { class: 'tk-btn primary', type: 'button', disabled: state.busy, text: 'Start workflow',
                    onclick: () => act('Start', () => api('/api/workflow-engine/workflows/' + id + '/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })) }) : null,
                cancellable ? h('button', { class: 'tk-btn', type: 'button', disabled: state.busy, text: 'Cancel',
                    onclick: () => { if (confirm('Cancel this workflow? Steps that have not run will not run.')) act('Cancel', () => api('/api/workflow-engine/workflows/' + id + '/cancel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })); } }) : null,
                finished ? h('button', { class: 'tk-btn danger', type: 'button', disabled: state.busy, text: 'Delete',
                    onclick: () => { if (confirm('Delete "' + detail.name + '"? This cannot be undone.')) act('Delete', async () => { await api('/api/workflow-engine/workflows/' + id, { method: 'DELETE' }); select(null); }); } }) : null),
            state.notice ? h('div', { class: 'tk-notice', role: 'alert', text: state.notice }) : null,
            detail.error ? h('div', { class: 'tk-notice', role: 'alert', text: detail.error }) : null,
            h('div', { class: 'tk-summary' },
                h('div', { class: 'tk-stat' }, h('b', { text: p.completed + ' / ' + p.total }), h('span', { text: 'steps done' })),
                h('div', { class: 'tk-stat' }, h('b', { text: duration(t.duration_seconds) }), h('span', { text: 'total time' })),
                h('div', { class: 'tk-stat' }, h('b', { text: when(t.started_at) }), h('span', { text: 'started' })),
                h('div', { class: 'tk-stat' }, h('b', { text: when(t.completed_at) }), h('span', { text: 'finished' })),
                p.failed ? h('div', { class: 'tk-stat' }, h('b', { text: String(p.failed) }), h('span', { text: 'failed' })) : null),
            progressBar(p, true),
            h('ol', { class: 'tk-steps', style: 'margin-top:20px' }, ...detail.steps.map(step => stepCard(step, id)))].filter(Boolean));
        window.scrollTo(0, scroll);
    }

    // ---- loading ----------------------------------------------------------------------------
    async function loadList() {
        const query = new URLSearchParams({ limit: '100' });
        if (state.filter) query.set('status', state.filter);
        const data = await api('/api/workflow-tracker?' + query);
        const key = JSON.stringify(data.workflows);
        state.workflows = data.workflows;
        if (key !== state.listKey) { state.listKey = key; renderList(); }
    }

    async function loadDetail() {
        if (state.selected === null) return;
        const id = state.selected;
        try {
            const detail = await api('/api/workflow-tracker/' + id);
            if (id !== state.selected) return;
            const key = JSON.stringify(detail);
            state.detail = detail;
            if (key !== state.detailKey) { state.detailKey = key; renderDetail(); }
        } catch (error) {
            if (error.status === 404) { state.detail = null; state.notice = 'This workflow does not exist (or is not yours).'; renderDetail(); }
            else throw error;
        }
    }

    async function refresh(force) {
        if (force) { state.listKey = ''; state.detailKey = ''; }
        try {
            await loadList();
            if (state.selected === null && !state.userClosed && window.matchMedia('(min-width: 861px)').matches && state.workflows.length) {
                state.selected = state.workflows[0].id; location.hash = state.selected; renderList();
            }
            await loadDetail();
        } catch (error) { /* a failed poll is retried on the next tick */ }
    }

    function select(id) {
        state.selected = id; state.detail = null; state.detailKey = ''; state.notice = ''; state.userClosed = id === null;
        history.replaceState(null, '', id === null ? location.pathname : '#' + id);
        renderList(); renderDetail(); loadDetail().then(schedule, schedule);
    }

    function fromHash() {
        const id = parseInt(location.hash.slice(1), 10);
        return Number.isInteger(id) ? id : null;
    }

    let timer = null;
    function schedule() {
        clearTimeout(timer);
        // fast while anything is in flight, including the workflow you are looking at (the list may not know yet)
        const live = ['running', 'pending', 'paused'];
        const active = state.workflows.some(w => live.includes(w.status)) || (state.detail !== null && live.includes(state.detail.status));
        timer = setTimeout(async () => { if (!document.hidden) await refresh(); schedule(); }, active ? FAST_POLL_MS : SLOW_POLL_MS);
    }

    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(true); });
    window.addEventListener('hashchange', () => { const id = fromHash(); if (id !== state.selected) select(id); });

    state.selected = fromHash();
    renderFilters();
    renderDetail();
    refresh(true).then(schedule);
})();
