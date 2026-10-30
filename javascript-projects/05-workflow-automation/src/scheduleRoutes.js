const { parseCron, nextRuns, describeCron, CronError } = require('./cron');
const { ScheduleValidationError } = require('./Scheduler');
const { requiredInputs } = require('./workflowSchema');

const ID_PATTERN = /^[\w-]+$/;

/**
 * The workflow check a schedule needs: the workflow exists and every input it needs has a value
 * (a blank input would make the run fail every time, so it is refused when saving).
 */
function makeWorkflowChecker(engine) {
  return async (workflowId, inputData) => {
    let workflow;
    try {
      workflow = await engine.loadWorkflow(workflowId);
    } catch (error) {
      return [`Workflow not found: ${workflowId}`];
    }
    const missing = requiredInputs(workflow).filter((name) => {
      const value = inputData[name];
      return value === undefined || value === null || String(value).trim() === '';
    });
    return missing.length > 0 ? [`Missing input${missing.length > 1 ? 's' : ''}: ${missing.join(', ')}`] : [];
  };
}

/** Add the /api/schedules routes to an express app. */
function registerScheduleRoutes(app, { scheduler, executionManager }) {
  const wrap = (handler) => async (req, res) => {
    try {
      await handler(req, res);
    } catch (error) {
      if (error instanceof ScheduleValidationError) {
        return res.status(400).json({ error: 'Schedule is not valid', details: error.details });
      }
      if (error.status && error.status < 500) {
        return res.status(error.status).json({ error: error.message });
      }
      console.error('Schedule error:', error.message);
      res.status(500).json({ error: error.message });
    }
  };

  const body = (req) => {
    if (!req.body || typeof req.body !== 'object' || Array.isArray(req.body)) {
      const error = new Error('The request body must be a JSON object');
      error.status = 400;
      throw error;
    }
    return req.body;
  };

  const idOf = (req) => {
    if (!ID_PATTERN.test(req.params.id)) {
      const error = new Error(`Schedule not found: ${req.params.id}`);
      error.status = 404;
      throw error;
    }
    return req.params.id;
  };

  app.get('/api/schedules', wrap(async (req, res) => {
    res.json({ timezone: scheduler.timezone, now: scheduler.now().toISOString(), schedules: scheduler.list() });
  }));

  // What a schedule would do, without saving it: used for the live preview in the form
  app.post('/api/schedules/preview', wrap(async (req, res) => {
    const { cron } = body(req);
    try {
      const parsed = parseCron(cron);
      res.json({
        valid: true, description: describeCron(cron), timezone: scheduler.timezone,
        next: nextRuns(parsed, scheduler.now(), 5).map(d => d.toISOString()),
      });
    } catch (error) {
      if (!(error instanceof CronError)) throw error;
      res.json({ valid: false, error: error.message, next: [] });
    }
  }));

  app.post('/api/schedules', wrap(async (req, res) => {
    res.status(201).json(await scheduler.create(body(req)));
  }));

  app.get('/api/schedules/:id', wrap(async (req, res) => {
    const schedule = scheduler.get(idOf(req));
    if (!schedule) return res.status(404).json({ error: `Schedule not found: ${req.params.id}` });
    res.json(schedule);
  }));

  app.patch('/api/schedules/:id', wrap(async (req, res) => {
    res.json(await scheduler.update(idOf(req), body(req)));
  }));

  app.delete('/api/schedules/:id', wrap(async (req, res) => {
    await scheduler.remove(idOf(req));
    res.status(204).end();
  }));

  app.post('/api/schedules/:id/run', wrap(async (req, res) => {
    res.status(202).json(await scheduler.runNow(idOf(req)));
  }));

  app.get('/api/schedules/:id/runs', wrap(async (req, res) => {
    const id = idOf(req);
    if (!scheduler.get(id)) return res.status(404).json({ error: `Schedule not found: ${id}` });
    const limit = Math.min(Math.max(parseInt(req.query.limit, 10) || 10, 1), 50);
    const runs = (await executionManager.listExecutions({ schedule_id: id })).slice(0, limit);
    res.json(runs.map(({ execution_id, status, trigger_type, started_at, duration_ms, steps_completed, steps_failed }) => (
      { execution_id, status, trigger_type, started_at, duration_ms, steps_completed, steps_failed }
    )));
  }));
}

module.exports = { registerScheduleRoutes, makeWorkflowChecker };
