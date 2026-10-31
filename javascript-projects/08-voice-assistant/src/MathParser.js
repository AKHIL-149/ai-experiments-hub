const { replaceNumberWords } = require('./SpokenNumbers');

/**
 * Spoken arithmetic, evaluated exactly (no eval / Function, no language model):
 * "what is 5 plus 3 times 2" -> 11, "15 percent of 200" -> 30, "square root of 16" -> 4,
 * "2 to the power of 10" -> 1024.
 *
 * solve() reports why it could not answer, so callers can tell "this is not maths"
 * (hand the question to the AI) from "this is maths I cannot compute" (say so).
 */

const MAX_INPUT_LENGTH = 200;
const MAX_DEPTH = 40;

class MathError extends Error {
  constructor(reason) {
    super(reason);
    this.reason = reason;
  }
}

/**
 * Turn the spoken phrase into a plain expression string
 */
function toExpression(text) {
  let s = ` ${text.toLowerCase()} `;

  // Leading question words
  s = s.replace(/^\s*(?:(?:please|hey|ok|okay)\s+)*(?:calculate|compute|solve|evaluate|work out|how much is|what is|whats|what's)\s+(?:the\s+)?/, ' ');

  s = replaceNumberWords(s.trim());
  s = ` ${s} `;

  s = s
    .replace(/(\d),(?=\d{3}\b)/g, '$1')                       // 1,000 -> 1000
    .replace(/(\d+(?:\.\d+)?)\s*(?:percent|%)\s+of\s+/g, '($1/100)*')
    .replace(/\bsquare root of\b/g, ' sqrt ')
    .replace(/\bsqrt of\b/g, ' sqrt ')
    .replace(/\bto the power of\b/g, ' ^ ')
    .replace(/\braised to(?: the power of)?\b/g, ' ^ ')
    .replace(/\bsquared\b/g, ' ^ 2 ')
    .replace(/\bcubed\b/g, ' ^ 3 ')
    .replace(/\bmultiplied by\b/g, ' * ')
    .replace(/\bdivided by\b/g, ' / ')
    .replace(/\bover\b/g, ' / ')
    .replace(/\btimes\b/g, ' * ')
    .replace(/\bplus\b/g, ' + ')
    .replace(/\bminus\b/g, ' - ')
    .replace(/\b(?:modulo|mod)\b/g, ' % ')
    .replace(/\bnegative\b/g, ' - ')
    .replace(/(\d)\s*x\s*(?=\d)/g, '$1 * ');                  // "7 x 8"

  return s.replace(/\s+/g, ' ').trim();
}

/**
 * Split an expression string into tokens, or throw NOT_MATH on anything unexpected
 */
function tokenize(expression) {
  const tokens = [];
  const pattern = /\s*(\d+(?:\.\d+)?|\.\d+|sqrt|[-+*/^%()])/y;
  let position = 0;

  while (position < expression.length) {
    pattern.lastIndex = position;
    const match = pattern.exec(expression);
    if (!match) {
      if (/^\s*$/.test(expression.slice(position))) break;
      throw new MathError('not-math'); // a word, "=", a variable, ...
    }
    tokens.push(match[1]);
    position = pattern.lastIndex;
  }

  return tokens;
}

/**
 * Recursive-descent evaluator:
 *   expr    := term (('+' | '-') term)*
 *   term    := unary (('*' | '/' | '%') unary)*
 *   unary   := ('+' | '-') unary | power
 *   power   := primary ('^' unary)?
 *   primary := number | '(' expr ')' | 'sqrt' primary
 */
function evaluate(tokens) {
  let index = 0;
  let operators = 0;

  const peek = () => tokens[index];
  const take = () => tokens[index++];

  function parseExpression(depth) {
    if (depth > MAX_DEPTH) throw new MathError('not-math');
    let value = parseTerm(depth);
    while (peek() === '+' || peek() === '-') {
      operators++;
      const op = take();
      const right = parseTerm(depth);
      value = op === '+' ? value + right : value - right;
    }
    return value;
  }

  function parseTerm(depth) {
    let value = parseUnary(depth);
    while (peek() === '*' || peek() === '/' || peek() === '%') {
      operators++;
      const op = take();
      const right = parseUnary(depth);
      if (op === '*') {
        value *= right;
      } else {
        if (right === 0) throw new MathError('divide-by-zero');
        value = op === '/' ? value / right : value % right;
      }
    }
    return value;
  }

  function parseUnary(depth) {
    if (peek() === '-') {
      take();
      return -parseUnary(depth);
    }
    if (peek() === '+') {
      take();
      return parseUnary(depth);
    }
    return parsePower(depth);
  }

  function parsePower(depth) {
    const base = parsePrimary(depth);
    if (peek() === '^') {
      operators++;
      take();
      return Math.pow(base, parseUnary(depth));
    }
    return base;
  }

  function parsePrimary(depth) {
    const token = take();
    if (token === undefined) throw new MathError('not-math');

    if (token === '(') {
      const value = parseExpression(depth + 1);
      if (take() !== ')') throw new MathError('not-math');
      return value;
    }
    if (token === 'sqrt') {
      operators++;
      const value = parsePrimary(depth + 1);
      if (value < 0) throw new MathError('not-math');
      return Math.sqrt(value);
    }
    if (/^(\d|\.)/.test(token)) {
      return parseFloat(token);
    }
    throw new MathError('not-math');
  }

  const result = parseExpression(0);
  if (index < tokens.length) throw new MathError('not-math');
  // A bare number ("what is 2024") is not a calculation
  if (operators === 0) throw new MathError('not-math');
  return result;
}

/**
 * Try to answer a spoken arithmetic question.
 * @param {string} text - e.g. "what is 12 times 12"
 * @returns {{ok: true, value: number, expression: string} | {ok: false, reason: string}}
 *   reason: 'not-math' | 'divide-by-zero' | 'too-large'
 */
function solve(text) {
  if (typeof text !== 'string' || text.length > MAX_INPUT_LENGTH) {
    return { ok: false, reason: 'not-math' };
  }

  try {
    const expression = toExpression(text);
    const value = evaluate(tokenize(expression));
    if (!Number.isFinite(value)) {
      return { ok: false, reason: 'too-large' };
    }
    return { ok: true, value, expression };
  } catch (error) {
    if (error instanceof MathError) {
      return { ok: false, reason: error.reason };
    }
    throw error;
  }
}

/**
 * A number the way it should be spoken and shown: no floating-point noise (0.1 + 0.2 is
 * 0.3), no exponent notation, and "negative" spelled out.
 * @param {number} value
 * @returns {string}
 */
function formatNumber(value) {
  if (Object.is(value, -0)) value = 0;
  const sign = value < 0 ? 'negative ' : '';
  const abs = Math.abs(value);

  if (abs >= 1e21) {
    const [mantissa, exponent] = abs.toExponential(6).split('e');
    return `${sign}${Number(mantissa)} times 10 to the ${parseInt(exponent, 10)}`;
  }

  const integerText = (n) => n.toLocaleString('en-US', { useGrouping: false, maximumFractionDigits: 0 });

  let text;
  if (Number.isInteger(abs)) {
    text = integerText(abs);                      // exact integers are never rounded
  } else {
    // Drop floating-point noise (0.1 + 0.2, 3.0000000000000004) by keeping 10 significant digits
    const rounded = Number(abs.toPrecision(10));
    if (Number.isInteger(rounded)) {
      text = integerText(rounded);
    } else if (rounded < 1e-6) {
      text = rounded.toLocaleString('en-US', { useGrouping: false, maximumSignificantDigits: 6 });
    } else {
      text = String(rounded);
      if (/e/i.test(text)) {
        text = rounded.toLocaleString('en-US', { useGrouping: false, maximumFractionDigits: 10 });
      }
    }
  }

  return `${sign}${text}`;
}

module.exports = { solve, formatNumber, toExpression };
