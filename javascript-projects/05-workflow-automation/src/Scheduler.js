const crypto = require('crypto');
const { parseCron, nextRun, describeCron, localMinuteKey, CronError } = require('./cron');
const { validateModelName } = require('./ollamaModels');

const NAME_MAX = 80;
const INPUT_MAX_BYTES = 20000;
const WORKFLOW_ID = /^[\w-]+(\/[\w-]+)*$/;
const EDITABLE = ['name', 'workflow_id', 'cron', 'input_data', 'model', 'enabled'];

class ScheduleValidationError extends Error {
  constructor(details) {
    super(details.join('; '));
    this.details = details;
    this.status = 400;
  }
}

/** A short reason for a failed run: the first step that failed, or the run's own error. */
function describeFailure(execution) {
  const steps = (execution && execution.result && execution.result.steps) || [];
  const failed = steps.find(step => !step.success);
  const text = failed ? `Step "${failed.step_id}" failed: ${failed.error}` : ((execution && execution.result && execution.result.error) || '');
  return text.length > 300 ? `${text.slice(0, 297)}...` : text;
}

function httpError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

/**
 * Runs workflows on cron schedules, in this process.
 *
 * start(workflowId, inputData, options) must resolve { executionId, done } where done resolves with the
 * final status ("completed" or "failed"). It rejects with error.code === "BUSY" when the server is at
 * its run limit. done may also resolve { status, message } to say why a run failed. Rules worth knowing:
 *  - a schedule never starts while its previous run is still going (the run is skipped and recorded);
 *  - a run that is more than lateToleranceMs late (computer asleep, server stopped) is skipped, never
 *    made up later: an out-of-date price check is worse than none;
 *  - skipped and failed runs are recorded on the schedule, so nothing fails silently;
 *  - a schedule that fails pauseAfterFailures times in a row pauses itself (and says so) instead of
 *    retrying a broken setup forever.
 */
class Scheduler {
  constructor({
    store, start, checkWorkflow = async () => [], now = () => new Date(), tickMs = 10000,
    maxSchedules = 50, lateToleranceMs = 120000, pauseAfterFailures = 10, log = console,
  }) {
    this.store = store;
    this.start = start;
    this.checkWorkflow = checkWorkflow;
    this.now = now;
    this.tickMs = tickMs;
    this.maxSchedules = maxSchedules;
    this.lateToleranceMs = lateToleranceMs;
    this.pauseAfterFailures = pauseAfterFailures; // 0 never pauses a schedule by itself
    this.log = log;

    this.schedules = new Map();
    this.running = new Map();   // schedule id -> execution id of its run in progress
    this.timer = null;
    this.ticking = false;
    this.lock = Promise.resolve();
  }

  get timezone() {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  }

  // ------------------------------------------------------------------ lifecycle

  async init() {
    const { schedules, warnings } = await this.store.load();
    warnings.forEach(w => this.log.warn(`Schedules: ${w}`));
    const now = this.now();

    for (const stored of schedules) {
      const s = {
        name: '', workflow_id: '', cron: '', input_data: {}, model: null, enabled: true,
        created_at: now.toISOString(), updated_at: now.toISOString(), next_run: null,
        last_run_at: null, last_status: null, last_message: '', last_execution_id: null,
        run_count: 0, consecutive_failures: 0, last_fired_key: null,
        ...stored,
      };

      if (s.last_status === 'running') {
        // its process died with the previous server
        s.last_status = 'failed';
        s.last_message = 'Interrupted: the server stopped while this run was in progress';
        s.consecutive_failures += 1;
      }

      this._settleNextRun(s, now);
      this.schedules.set(s.id, s);
    }
    if (this.schedules.size > 0) {
      await this._persist();
    }
  }

  /** Decide the next run for a schedule loaded from disk. Never makes up runs missed while off. */
  _settleNextRun(s, now) {
    if (!s.enabled) {
      s.next_run = null;
      return;
    }
    let cron;
    try {
      cron = parseCron(s.cron);
    } catch (error) {
      s.next_run = null;
      s.last_status = 'error';
      s.last_message = `The saved schedule is not valid and will not run: ${error.message}`;
      return;
    }

    const stored = s.next_run ? new Date(s.next_run) : null;
    if (stored && !Number.isNaN(stored.getTime())) {
      if (now - stored <= this.lateToleranceMs) {
        return; // still ahead (or only just past): the tick will run it
      }
      s.last_status = 'missed';
      s.last_message = `The server was not running at ${localMinuteKey(stored)}, so that run was skipped`;
      s.next_run = this._following(cron, now, localMinuteKey(stored));
      return;
    }
    s.next_run = this._following(cron, now, null);
  }

  startTimer() {
    if (this.timer) return;
    this.timer = setInterval(() => {
      this.tick().catch(error => this.log.error(`Scheduler tick failed: ${error.message}`));
    }, this.tickMs);
    this.timer.unref(); // the scheduler alone never keeps the process alive
  }

  stopTimer() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  // ------------------------------------------------------------------ reading

  _view(s) {
    const { last_fired_key, ...rest } = s;
    return { ...rest, input_data: structuredClone(s.input_data), description: describeCron(s.cron), running: this.running.has(s.id) };
  }

  list() {
    return [...this.schedules.values()].reverse().map(s => this._view(s));
  }

  get(id) {
    const s = this.schedules.get(id);
    return s ? this._view(s) : null;
  }

  _require(id) {
    const s = this.schedules.get(id);
    if (!s) throw httpError(404, `Schedule not found: ${id}`);
    return s;
  }

  // ------------------------------------------------------------------ changing

  /** Run one change at a time, so a save never interleaves with another change or a tick. */
  _exclusive(fn) {
    const result = this.lock.then(fn, fn);
    this.lock = result.catch(() => {});
    return result;
  }

  async _persist() {
    await this.store.save([...this.schedules.values()]);
  }

  async _validate(fields, { checkWorkflow }) {
    const errors = [];
    const has = (key) => fields[key] !== undefined;

    if (has('name')) {
      const name = typeof fields.name === 'string' ? fields.name.trim() : '';
      if (!name) errors.push('Name is required');
      else if (name.length > NAME_MAX) errors.push(`Name must be ${NAME_MAX} characters or fewer`);
    }
    let workflowOk = true;
    if (has('workflow_id')) {
      if (typeof fields.workflow_id !== 'string' || !fields.workflow_id.trim()) {
        errors.push('Workflow is required');
        workflowOk = false;
      } else if (!WORKFLOW_ID.test(fields.workflow_id)) {
        errors.push('Workflow ID is not valid');
        workflowOk = false;
      }
    }
    if (has('cron')) {
      try {
        parseCron(fields.cron);
      } catch (error) {
        if (!(error instanceof CronError)) throw error;
        errors.push(error.message);
      }
    }
    let inputOk = true;
    if (has('input_data')) {
      const data = fields.input_data;
      if (!data || typeof data !== 'object' || Array.isArray(data)) {
        errors.push('input_data must be an object of values, like {"name": "value"}');
        inputOk = false;
      } else if (JSON.stringify(data).length > INPUT_MAX_BYTES) {
        errors.push(`input_data is too large (limit ${INPUT_MAX_BYTES / 1000} KB)`);
        inputOk = false;
      }
    }
    if (has('model')) {
      try {
        validateModelName(fields.model);
      } catch (error) {
        errors.push(error.message);
      }
    }
    if (has('enabled') && typeof fields.enabled !== 'boolean') {
      errors.push('enabled must be true or false');
    }

    if (checkWorkflow && workflowOk && inputOk) {
      errors.push(...(await this.checkWorkflow(fields.workflow_id, fields.input_data)));
    }
    return errors;
  }

  create(input = {}) {
    return this._exclusive(async () => {
      const fields = {
        // missing required fields are validated as blank, not skipped
        name: input.name ?? '', workflow_id: input.workflow_id ?? '', cron: input.cron ?? '',
        input_data: input.input_data === undefined ? {} : input.input_data,
        model: input.model || null, enabled: input.enabled === undefined ? true : input.enabled,
      };
      const errors = await this._validate(fields, { checkWorkflow: true });
      if (errors.length === 0 && this.schedules.size >= this.maxSchedules) {
        errors.push(`There can be at most ${this.maxSchedules} schedules`);
      }
      if (errors.length > 0) throw new ScheduleValidationError(errors);

      const now = this.now();
      const s = {
        id: `sch-${crypto.randomBytes(4).toString('hex')}`,
        name: fields.name.trim(), workflow_id: fields.workflow_id, cron: fields.cron.trim(),
        input_data: structuredClone(fields.input_data), model: fields.model, enabled: fields.enabled,
        created_at: now.toISOString(), updated_at: now.toISOString(), next_run: null,
        last_run_at: null, last_status: null, last_message: '', last_execution_id: null,
        run_count: 0, consecutive_failures: 0, last_fired_key: null,
      };
      s.next_run = s.enabled ? this._following(parseCron(s.cron), now, null) : null;

      this.schedules.set(s.id, s);
      try {
        await this._persist();
      } catch (error) {
        this.schedules.delete(s.id);
        throw error;
      }
      return this._view(s);
    });
  }

  update(id, patch = {}) {
    return this._exclusive(async () => {
      const s = this._require(id);
      const fields = {};
      for (const key of EDITABLE) if (patch[key] !== undefined) fields[key] = patch[key];
      if (fields.model === '') fields.model = null;

      // only look at the workflow again when what runs changes, so a schedule can still be paused
      // or deleted after its workflow has gone
      const changesRun = 'workflow_id' in fields || 'input_data' in fields;
      const merged = { ...fields, ...(changesRun ? { workflow_id: fields.workflow_id ?? s.workflow_id, input_data: fields.input_data ?? s.input_data } : {}) };
      const errors = await this._validate(merged, { checkWorkflow: changesRun });
      if (errors.length > 0) throw new ScheduleValidationError(errors);

      const before = { ...s };
      Object.assign(s, fields);
      if (typeof s.name === 'string') s.name = s.name.trim();
      if (typeof s.cron === 'string') s.cron = s.cron.trim();
      s.updated_at = this.now().toISOString();
      if ('enabled' in fields && fields.enabled && !before.enabled) {
        // turned back on by hand: start counting failures afresh (and drop the old "paused" note)
        s.consecutive_failures = 0;
        s.last_message = '';
      }
      if ('cron' in fields || 'enabled' in fields) {
        s.next_run = s.enabled ? this._following(parseCron(s.cron), this.now(), null) : null;
      }
      try {
        await this._persist();
      } catch (error) {
        Object.assign(s, before);
        throw error;
      }
      return this._view(s);
    });
  }

  remove(id) {
    return this._exclusive(async () => {
      const s = this._require(id);
      this.schedules.delete(id);
      try {
        await this._persist();
      } catch (error) {
        this.schedules.set(id, s);
        throw error;
      }
    });
  }

  // ------------------------------------------------------------------ running

  _following(cron, after, skipKey) {
    const next = nextRun(cron, after, { skipLocalMinute: skipKey || undefined });
    return next ? next.toISOString() : null;
  }

  /** Move a schedule past the slot that was just handled. */
  _advance(s, now, slot) {
    s.next_run = this._following(parseCron(s.cron), now, localMinuteKey(slot));
  }

  /** Count a failed run and pause the schedule if it has failed too many times in a row. */
  _recordFailure(s, message) {
    s.consecutive_failures += 1;
    s.last_message = message || s.last_message;
    if (this.pauseAfterFailures > 0 && s.consecutive_failures >= this.pauseAfterFailures && s.enabled) {
      s.enabled = false;
      s.next_run = null;
      s.last_message = `${s.last_message ? `${s.last_message}. ` : ''}Paused automatically after ${s.consecutive_failures} failed runs in a row`;
      this.log.warn(`Schedule ${s.id} (${s.name}) paused after ${s.consecutive_failures} failed runs in a row`);
    }
  }

  /** Start one run. Returns true if a run started. Records skips and failures on the schedule. */
  async _fire(s, { manual }) {
    if (this.running.has(s.id)) {
      s.last_status = 'skipped';
      s.last_message = 'Skipped: the previous run is still in progress';
      return false;
    }

    let started;
    try {
      started = await this.start(s.workflow_id, structuredClone(s.input_data), {
        model: s.model, triggerType: manual ? 'schedule-manual' : 'schedule', scheduleId: s.id,
      });
    } catch (error) {
      if (error.code === 'BUSY') {
        s.last_status = 'skipped';
        s.last_message = `Skipped: ${error.message}`;
        if (manual) throw httpError(429, error.message);
        return false;
      }
      s.last_status = 'error';
      this._recordFailure(s, error.message);
      if (manual) throw httpError(error.status || 500, error.message);
      return false;
    }

    s.last_run_at = this.now().toISOString();
    s.last_status = 'running';
    s.last_message = '';
    s.last_execution_id = started.executionId;
    s.run_count += 1;
    this.running.set(s.id, started.executionId);

    started.done.then(
      (outcome) => this._finished(s.id, started.executionId, outcome),
      () => this._finished(s.id, started.executionId, 'failed')
    );
    return true;
  }

  _finished(id, executionId, outcome) {
    if (this.running.get(id) === executionId) this.running.delete(id);
    const s = this.schedules.get(id);
    if (!s || s.last_execution_id !== executionId) return;

    const { status, message } = typeof outcome === 'string' ? { status: outcome, message: '' } : outcome;
    if (status === 'completed') {
      s.last_status = 'completed';
      s.last_message = '';
      s.consecutive_failures = 0;
    } else {
      s.last_status = 'failed';
      this._recordFailure(s, message);
    }
    this._persist().catch(error => this.log.error(`Could not save schedule ${id}: ${error.message}`));
  }

  runNow(id) {
    return this._exclusive(async () => {
      const s = this._require(id);
      if (this.running.has(id)) throw httpError(409, 'This schedule is already running');
      try {
        await this._fire(s, { manual: true });
      } finally {
        await this._persist().catch(error => this.log.error(`Could not save schedule ${id}: ${error.message}`));
      }
      return this._view(s);
    });
  }

  /** Start everything that is due. Returns the ids of the schedules that started a run. */
  async tick() {
    if (this.ticking) return [];
    this.ticking = true;
    try {
      return await this._exclusive(async () => {
        const now = this.now();
        const started = [];
        let changed = false;

        for (const s of this.schedules.values()) {
          if (!s.enabled || !s.next_run) continue;
          const due = new Date(s.next_run);
          if (due > now) continue;

          if (now - due > this.lateToleranceMs) {
            s.last_status = 'missed';
            s.last_message = `Missed the run due at ${localMinuteKey(due)} (the scheduler was paused or the computer was asleep); it was skipped`;
          } else if (await this._fire(s, { manual: false })) {
            started.push(s.id);
            s.last_fired_key = localMinuteKey(due);
          }
          this._advance(s, now, due);
          changed = true;
        }

        if (changed) await this._persist();
        return started;
      });
    } finally {
      this.ticking = false;
    }
  }
}

module.exports = { Scheduler, ScheduleValidationError, describeFailure };
