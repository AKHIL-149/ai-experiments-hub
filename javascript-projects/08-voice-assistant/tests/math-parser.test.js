const test = require('node:test');
const assert = require('node:assert/strict');
const { solve, formatNumber } = require('../src/MathParser');

const answer = (text) => {
  const result = solve(text);
  assert.ok(result.ok, `${text}: expected an answer, got ${result.reason}`);
  return result.value;
};
const reason = (text) => {
  const result = solve(text);
  assert.equal(result.ok, false, `${text}: expected no answer`);
  return result.reason;
};

test('the four operations, spoken and symbolic', () => {
  assert.equal(answer('what is 5 plus 3'), 8);
  assert.equal(answer('what is 10 minus 20'), -10);
  assert.equal(answer('what is 7 times 8'), 56);
  assert.equal(answer('calculate 100 divided by 4'), 25);
  assert.equal(answer('what is 2+2'), 4);
  assert.equal(answer('compute 9 / 3'), 3);
  assert.equal(answer('what is 7 x 8'), 56);
  assert.equal(answer('what is 10 over 4'), 2.5);
});

test('operator precedence and parentheses', () => {
  assert.equal(answer('what is 5 plus 3 times 2'), 11);
  assert.equal(answer('what is (2 plus 3) times 4'), 20);
  assert.equal(answer('what is 2 to the power of 3 to the power of 2'), 512); // right-associative
  assert.equal(answer('what is 2 minus 3 minus 4'), -5);                      // left-associative
});

test('powers, roots, percentages, modulo', () => {
  assert.equal(answer('what is 2 to the power of 10'), 1024);
  assert.equal(answer('what is 3 squared'), 9);
  assert.equal(answer('what is 3 cubed'), 27);
  assert.equal(answer('what is the square root of 16'), 4);
  assert.equal(answer('square root of 81'), 9);
  assert.equal(answer('what is 15 percent of 200'), 30);
  assert.equal(answer('what is 10 mod 3'), 1);
});

test('spoken number words work like digits', () => {
  assert.equal(answer('what is five plus three'), 8);
  assert.equal(answer('what is twenty five times four'), 100);
  assert.equal(answer('what is two point five times two'), 5);
  assert.equal(answer('what is negative 5 plus 2'), -3);
});

test('thousands separators and decimals', () => {
  assert.equal(answer('what is 1,000 plus 1'), 1001);
  assert.equal(answer('what is 1.5 times 4'), 6);
  assert.equal(answer('what is .5 plus .5'), 1);
});

test('division by zero is reported, not computed', () => {
  assert.equal(reason('what is 1/0'), 'divide-by-zero');
  assert.equal(reason('what is 10 divided by 0'), 'divide-by-zero');
  assert.equal(reason('what is 5 mod 0'), 'divide-by-zero');
});

test('results that overflow are reported as too large', () => {
  assert.equal(reason('what is 2 to the power of 10000'), 'too-large');
  assert.equal(reason('what is 9 to the power of 9 to the power of 9'), 'too-large');
});

test('questions that are not arithmetic are not answered', () => {
  for (const text of [
    'what is python 3', 'what is 2024 olympics', 'what is the capital of france', 'what is 2024',
    'solve 3x + 4 = 10', 'what is 5 plus', 'what is ((((1', 'what is the sum of 2 and 3',
    'what is the square root of negative 4', '', 'hello'
  ]) {
    assert.equal(reason(text), 'not-math', text);
  }
});

test('code-like input is never evaluated', () => {
  for (const text of ['what is process.exit()', 'what is 1; 2', 'what is require("fs")', 'what is constructor', 'what is 2 ** 3 ** 2']) {
    assert.equal(solve(text).ok, false, text);
  }
});

test('very long or deeply nested input is refused safely', () => {
  assert.equal(reason(`what is ${'1 plus '.repeat(100)}1`), 'not-math');
  assert.equal(reason(`what is ${'('.repeat(100)}1${')'.repeat(100)} plus 1`), 'not-math');
});

test('formatNumber removes floating point noise', () => {
  assert.equal(formatNumber(0.1 + 0.2), '0.3');
  assert.equal(formatNumber(100 / 3), '33.33333333');
  assert.equal(formatNumber(1 / 3), '0.3333333333');
  assert.equal(formatNumber(2 / 3 * 3), '2');
});

test('formatNumber treats near-integers as integers', () => {
  assert.equal(formatNumber(0.1 * 3 * 10), '3');          // 3.0000000000000004
  assert.equal(formatNumber((0.7 + 0.1) * 10), '8');      // 7.999999999999999
  assert.equal(formatNumber(1.1 * 1.1), '1.21');          // 1.2100000000000002
});

test('formatNumber never rounds an exact integer', () => {
  assert.equal(formatNumber(1234567890123), '1234567890123');
  assert.equal(formatNumber(123456789012345), '123456789012345');
  assert.equal(formatNumber(-98765432109876), 'negative 98765432109876');
  assert.equal(formatNumber(2 ** 40), '1099511627776');
});

test('the square root of a negative number is not answered', () => {
  assert.equal(solve('what is the square root of (0 minus 4)').ok, false);
  assert.equal(solve('what is the square root of (0 minus 4)').reason, 'not-math');
  assert.equal(solve('what is the square root of (4 minus 4)').value, 0);
});

test('formatNumber spells out sign and never uses exponent notation', () => {
  assert.equal(formatNumber(-3), 'negative 3');
  assert.equal(formatNumber(-0), '0');
  assert.equal(formatNumber(1e15), '1000000000000000');
  assert.equal(formatNumber(1e22), '1 times 10 to the 22');
  assert.equal(formatNumber(1.5e30), '1.5 times 10 to the 30');
  assert.equal(formatNumber(0.0000001234), '0.0000001234');
  assert.doesNotMatch(formatNumber(1e-9), /e/i);
});
