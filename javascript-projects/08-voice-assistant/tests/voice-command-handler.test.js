const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const VoiceCommandHandler = require('../src/VoiceCommandHandler');
const { silenceConsole } = require('./helpers');

const handler = new VoiceCommandHandler(path.join(__dirname, '../commands/commands.json'));

const commandFor = async (phrase) => (await handler.parseCommand(phrase)).command;

test('everyday phrases reach the right command', async () => {
  const expected = {
    'What time is it?': 'time', 'what is the time': 'time', "what's the time": 'time', 'tell me the time': 'time',
    'time': 'time', 'What time is it please?': 'time',
    'what day is it': 'date', 'What is the date today?': 'date', "what's today": 'date', "Today's date.": 'date',
    'tell me a joke': 'joke', 'Tell me a joke, please.': 'joke', 'joke': 'joke', 'can you tell me a joke': 'joke',
    'weather': 'weather', "What's the weather?": 'weather', 'is it raining': 'weather',
    'What is the weather like in Austin today?': 'weather', 'weather in new york': 'weather',
    'next f1 race': 'f1_schedule', 'when is the next race': 'f1_schedule', 'when is the next f1 grand prix': 'f1_schedule',
    'help': 'help', 'what can you do': 'help', 'commands': 'help',
    'hello': 'greeting', 'Hello there!': 'greeting', 'hi': 'greeting', 'good morning': 'greeting',
    'set a timer for 5 minutes': 'timer', 'Set a timer for five minutes.': 'timer', 'timer 90 seconds': 'timer',
    'remind me in 10 minutes to call mom': 'timer',
    'what is 5 plus 3': 'calculate', 'Calculate 25 times 4.': 'calculate', '5 plus 3': 'calculate',
    'what is the square root of 16': 'calculate', 'what is five plus three': 'calculate'
  };
  for (const [phrase, command] of Object.entries(expected)) {
    assert.equal(await commandFor(phrase), command, phrase);
  }
});

test('fragments, stopwords and blanks never trigger a command', async () => {
  for (const phrase of ['', ' ', '   ', '\n', 'it', 'is', 'the', 'what', 'a', 'me', 'tell', 'how', 'you', '?', '...', 'um']) {
    assert.equal(await commandFor(phrase), null, JSON.stringify(phrase));
  }
});

test('non-string input is not a command', async () => {
  for (const value of [null, undefined, 123, {}, ['time']]) {
    assert.equal(await commandFor(value), null);
  }
});

test('requests a command cannot really answer go to the AI instead', async () => {
  for (const phrase of [
    'tell me a joke about cats', 'help me with my homework', 'what time is it in tokyo',
    'what is the time in london', 'funny cat videos', 'who won the last f1 race', 'when is the next iphone release',
    'what is the capital of france', 'what is python 3', 'what is 2024 olympics', 'solve 3x + 4 = 10',
    'will it rain tomorrow', 'hi how are you', 'high school history', 'what time does the store open'
  ]) {
    assert.equal(await commandFor(phrase), null, phrase);
  }
});

test('a recognised command carries its parameters and a confidence', async () => {
  const exact = await handler.parseCommand('what time is it');
  assert.equal(exact.confidence, 1);
  assert.equal(exact.handler, 'getTime');

  const timer = await handler.parseCommand('set a timer for 5 minutes');
  assert.deepEqual(timer.parameters, { duration: '5 minutes' });
  assert.ok(timer.confidence >= 0.7);
});

test('the best match wins regardless of registry order', async () => {
  // "what day is it" overlaps the time command's words, but the date command is the exact one
  assert.equal(await commandFor('what day is it'), 'date');
});

test('calculate answers arithmetic exactly and says so when it cannot', async () => {
  const run = async (phrase) => handler.calculate({}, { originalTranscript: phrase });

  assert.equal((await run('What is 12 times 12?')).response, 'The result is 144.');
  assert.equal((await run('what is 0.1 plus 0.2')).response, 'The result is 0.3.');
  assert.equal((await run('what is 7 minus 10')).response, 'The result is negative 3.');
  assert.equal((await run('what is 10 divided by 0')).response, "I can't divide by zero.");
  assert.equal((await run('what is 2 to the power of 10000')).response, 'That number is too large for me to work out.');
  assert.equal((await run('what is 99999999999 times 99999999999')).response, 'The result is 1 times 10 to the 22.');

  const notMath = await run('what is python 3');
  assert.equal(notMath.fallThrough, true);
});

test('setTimer: parses, stores, labels and refuses bad durations', async () => {
  const h = new VoiceCommandHandler(path.join(__dirname, '../commands/commands.json'));
  const set = (duration) => h.setTimer({ duration }, {});

  const five = await set('five minutes');
  assert.equal(five.success, true);
  assert.equal(five.response, "Timer set for 5 minutes. I'll let you know when time is up!");
  assert.equal(five.data.timer.duration, 300);
  assert.ok(Math.abs(five.data.timer.endTime - (Date.now() + 300000)) < 2000);
  assert.equal(h.timers.size, 1);

  assert.match((await set('1.5 hours')).response, /1 hour and 30 minutes/);
  assert.match((await set('an hour')).response, /Timer set for 1 hour\./);

  const reminder = await set('10 minutes to call mom');
  assert.equal(reminder.response, "OK, I'll remind you to call mom in 10 minutes.");
  assert.equal(reminder.data.timer.label, 'call mom');

  assert.match((await set('0 minutes')).response, /longer than zero/);
  assert.match((await set('99999999 hours')).response, /up to 24 hours/);
  assert.match((await set('for the pasta')).response, /couldn't set that timer/);
  assert.equal(h.timers.size, 4, 'refused timers are not stored');

  // ids are unique even when two timers are set in the same millisecond
  const a = (await set('1 minute')).data.timer.id;
  const b = (await set('1 minute')).data.timer.id;
  assert.notEqual(a, b);
});

test('setTimer forgets finished timers and caps how many can run', async () => {
  const h = new VoiceCommandHandler(path.join(__dirname, '../commands/commands.json'));
  h.timers.set('old', { id: 'old', endTime: Date.now() - 1000 });
  await h.setTimer({ duration: '1 minute' }, {});
  assert.equal(h.timers.has('old'), false);

  h.maxTimers = 3;
  await h.setTimer({ duration: '1 minute' }, {});
  await h.setTimer({ duration: '1 minute' }, {});
  const refused = await h.setTimer({ duration: '1 minute' }, {});
  assert.equal(refused.success, false);
  assert.match(refused.response, /a lot of timers/);
});

test('extractWeatherLocation finds the place, and only the place', () => {
  const place = (t) => handler.extractWeatherLocation(t);
  assert.equal(place('weather'), null);
  assert.equal(place("What's the weather?"), null);
  assert.equal(place('weather in Austin'), 'Austin');
  assert.equal(place('What is the weather in Austin?'), 'Austin');
  assert.equal(place('What is the weather like in Austin today?'), 'Austin');
  assert.equal(place('how is the weather in Paris, France?'), 'Paris, France');
  assert.equal(place('weather forecast for Boston'), 'Boston');
  assert.equal(place('weather in New York right now'), 'New York');
  assert.equal(place('weather at San Francisco please.'), 'San Francisco');
  assert.equal(place('weather in '), null);
  assert.equal(place(`weather in ${'x'.repeat(200)}`), null);
});

test('getWeather asks for the named city, and is honest about forecasts', async () => {
  const asked = [];
  const h = new VoiceCommandHandler(path.join(__dirname, '../commands/commands.json'), {
    weatherService: {
      getCurrentWeather: async (location) => {
        asked.push(location);
        return { location: location || 'Houston, TX, US', description: 'clear', tempF: 70, feelsLikeF: 71, humidity: 40 };
      }
    }
  });

  const austin = await h.getWeather({}, { originalTranscript: 'What is the weather like in Austin today?' });
  assert.deepEqual(asked, ['Austin']);
  assert.equal(austin.response, "It's currently 70°F and clear in Austin, feels like 71°F, with 40% humidity.");

  const tomorrow = await h.getWeather({}, { originalTranscript: 'will the weather be nice tomorrow' });
  assert.match(tomorrow.response, /^I can only check current conditions\. It's currently/);
  assert.equal(asked[1], null);
});

test('getWeather failure is a polite answer, not a crash', async () => {
  const restore = silenceConsole();
  try {
    const h = new VoiceCommandHandler(path.join(__dirname, '../commands/commands.json'), {
      weatherService: { getCurrentWeather: async () => { throw new Error('boom'); } }
    });
    const result = await h.getWeather({}, { originalTranscript: 'weather' });
    assert.equal(result.success, false);
    assert.match(result.response, /couldn't get the weather/);
  } finally { restore(); }
});

test('executeCommand: unknown handler and handler errors are answered, not thrown', async () => {
  const restore = silenceConsole();
  try {
    assert.match((await handler.executeCommand({ handler: null })).response, /didn't understand/);
    assert.match((await handler.executeCommand({ handler: 'nope' })).response, /not implemented/);
    const broken = new VoiceCommandHandler(path.join(__dirname, '../commands/commands.json'));
    broken.getTime = async () => { throw new Error('kaput'); };
    const result = await broken.executeCommand({ handler: 'getTime', parameters: {} });
    assert.equal(result.success, false);
    assert.match(result.response, /kaput/);
  } finally { restore(); }
});

test('time and date answers use the real clock', async () => {
  const time = await handler.getTime({}, {});
  assert.match(time.response, /^The current time is \d{1,2}:\d{2}\s?(AM|PM)\.$/);
  const date = await handler.getDate({}, {});
  assert.equal(date.response, `Today is ${new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}.`);
});

test('a missing or broken registry file gives an empty handler, not a crash', async () => {
  const restore = silenceConsole();
  try {
    const empty = new VoiceCommandHandler('/nonexistent/commands.json');
    assert.deepEqual(empty.listCommands(), {});
    assert.equal((await empty.parseCommand('what time is it')).command, null);
  } finally { restore(); }
});
