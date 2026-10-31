const test = require('node:test');
const assert = require('node:assert/strict');
const { wordsToNumber, replaceNumberWords } = require('../src/SpokenNumbers');

test('wordsToNumber handles units, tens, hundreds and scales', () => {
  assert.equal(wordsToNumber(['five']), 5);
  assert.equal(wordsToNumber(['nineteen']), 19);
  assert.equal(wordsToNumber(['twenty', 'five']), 25);
  assert.equal(wordsToNumber(['one', 'hundred', 'and', 'five']), 105);
  assert.equal(wordsToNumber(['two', 'thousand', 'three', 'hundred']), 2300);
  assert.equal(wordsToNumber(['three', 'million']), 3000000);
  assert.equal(wordsToNumber(['hundred']), 100);
});

test('replaceNumberWords turns runs of number words into digits', () => {
  assert.equal(replaceNumberWords('five plus three'), '5 plus 3');
  assert.equal(replaceNumberWords('twenty five times four'), '25 times 4');
  assert.equal(replaceNumberWords('one hundred and five minutes'), '105 minutes');
  assert.equal(replaceNumberWords('a hundred'), '100');
  assert.equal(replaceNumberWords('a thousand and one'), '1001');
});

test('replaceNumberWords reads spoken decimals', () => {
  assert.equal(replaceNumberWords('two point five times two'), '2.5 times 2');
  assert.equal(replaceNumberWords('zero point zero five'), '0.05');
});

test('replaceNumberWords leaves other words alone', () => {
  assert.equal(replaceNumberWords('what is the time'), 'what is the time');
  assert.equal(replaceNumberWords('a joke'), 'a joke');
  assert.equal(replaceNumberWords('and then some'), 'and then some');
  assert.equal(replaceNumberWords('point of view'), 'point of view');
});

test('"and" only joins the parts of one number, after hundred or a scale word', () => {
  assert.equal(replaceNumberWords('one hundred and five'), '105');
  assert.equal(replaceNumberWords('five and six'), '5 and 6');
  assert.equal(replaceNumberWords('five minutes and six seconds'), '5 minutes and 6 seconds');
  assert.equal(replaceNumberWords('twenty and five'), '20 and 5');
});
