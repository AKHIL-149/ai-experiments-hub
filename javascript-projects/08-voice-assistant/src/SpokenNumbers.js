/**
 * Spoken number words -> digits ("twenty five" -> "25", "one hundred and five" -> "105",
 * "two point five" -> "2.5"). Speech recognition usually writes digits, but not always
 * ("five minutes"), so the maths and timer parsers run their input through this first.
 */

const UNITS = {
  zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9,
  ten: 10, eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16,
  seventeen: 17, eighteen: 18, nineteen: 19
};

const TENS = {
  twenty: 20, thirty: 30, forty: 40, fourty: 40, fifty: 50, sixty: 60, seventy: 70,
  eighty: 80, ninety: 90
};

const SCALES = { thousand: 1e3, million: 1e6, billion: 1e9 };

const isNumberWord = (word) =>
  word in UNITS || word in TENS || word === 'hundred' || word in SCALES;

/**
 * Value of a run of number words, e.g. ['one', 'hundred', 'and', 'five'] -> 105.
 * @param {string[]} words
 * @returns {number}
 */
function wordsToNumber(words) {
  let total = 0;
  let current = 0;

  for (const word of words) {
    if (word in UNITS) {
      current += UNITS[word];
    } else if (word in TENS) {
      current += TENS[word];
    } else if (word === 'hundred') {
      current = (current || 1) * 100;
    } else if (word in SCALES) {
      total += (current || 1) * SCALES[word];
      current = 0;
    }
    // "and" carries no value
  }

  return total + current;
}

/**
 * Replace every run of number words in a sentence with digits.
 * "a hundred" / "a thousand" count as 100 / 1000. Words that are not numbers are untouched.
 * @param {string} text
 * @returns {string}
 */
function replaceNumberWords(text) {
  const tokens = text.split(/\s+/).filter(Boolean);
  const out = [];
  let i = 0;

  while (i < tokens.length) {
    const word = tokens[i];
    const startsRun = isNumberWord(word) ||
      (word === 'a' && i + 1 < tokens.length && (tokens[i + 1] === 'hundred' || tokens[i + 1] in SCALES));

    if (!startsRun) {
      out.push(word);
      i++;
      continue;
    }

    // Collect the run: number words, with "and" allowed between two number words
    const run = [];
    while (i < tokens.length) {
      const current = tokens[i];
      if (isNumberWord(current) || (current === 'a' && run.length === 0)) {
        run.push(current);
        i++;
      } else if (current === 'and' && run.length > 0 && i + 1 < tokens.length && isNumberWord(tokens[i + 1]) &&
                 (run[run.length - 1] === 'hundred' || run[run.length - 1] in SCALES)) {
        // "one hundred and five" is one number; "five and six" is two
        run.push(current);
        i++;
      } else {
        break;
      }
    }

    let value = String(wordsToNumber(run.filter(w => w !== 'a')));

    // "two point five" -> 2.5 (digits spoken one by one after "point")
    if (tokens[i] === 'point') {
      const digits = [];
      let j = i + 1;
      while (j < tokens.length && tokens[j] in UNITS && UNITS[tokens[j]] <= 9) {
        digits.push(UNITS[tokens[j]]);
        j++;
      }
      if (digits.length > 0) {
        value += '.' + digits.join('');
        i = j;
      }
    }

    out.push(value);
  }

  return out.join(' ');
}

module.exports = { wordsToNumber, replaceNumberWords };
