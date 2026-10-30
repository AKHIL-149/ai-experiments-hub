const { test } = require('node:test');
const assert = require('node:assert/strict');

const { renderMarkdown } = require('../public/markdown');

test('headings, bold and italic', () => {
  assert.equal(renderMarkdown('## Top problems'), '<h2>Top problems</h2>');
  assert.equal(renderMarkdown('**To Sam K.:** sorry'), '<p><strong>To Sam K.:</strong> sorry</p>');
  assert.equal(renderMarkdown('an *odd* and _quiet_ word'), '<p>an <em>odd</em> and <em>quiet</em> word</p>');
});

test('a snake_case word or a lone asterisk is not turned into emphasis', () => {
  assert.equal(renderMarkdown('use feedback_csv and report_path'), '<p>use feedback_csv and report_path</p>');
  assert.equal(renderMarkdown('2 * 3 * 4'), '<p>2 * 3 * 4</p>');
  assert.equal(renderMarkdown('x_y_ z'), '<p>x_y_ z</p>'); // underscore inside a word, closing one after
});

test('bullet and numbered lists', () => {
  assert.equal(renderMarkdown('* one\n* two'), '<ul><li>one</li><li>two</li></ul>');
  assert.equal(renderMarkdown('- a\n- b'), '<ul><li>a</li><li>b</li></ul>');
  assert.equal(renderMarkdown('1. first\n2) second'), '<ol><li>first</li><li>second</li></ol>');
});

test('a heading directly followed by a list renders both', () => {
  assert.equal(
    renderMarkdown('## Love\n* a\n* b\n\n## Problems\n* c'),
    '<h2>Love</h2>\n<ul><li>a</li><li>b</li></ul>\n<h2>Problems</h2>\n<ul><li>c</li></ul>'
  );
});

test('tables become real tables, with short rows padded', () => {
  const html = renderMarkdown('| ID | Name |\n| --- | --- |\n| 1 | Dana |\n| 2 |');
  assert.match(html, /<th>ID<\/th><th>Name<\/th>/);
  assert.match(html, /<td>1<\/td><td>Dana<\/td>/);
  assert.match(html, /<td>2<\/td><td><\/td>/);
});

test('a line with a pipe but no separator row stays a paragraph', () => {
  assert.equal(renderMarkdown('a | b'), '<p>a | b</p>');
});

test('single line breaks inside a paragraph are kept', () => {
  assert.equal(renderMarkdown('**To Sam:**\nSorry to hear that.'), '<p><strong>To Sam:</strong><br>Sorry to hear that.</p>');
});

test('code spans and fenced code are not formatted inside', () => {
  assert.equal(renderMarkdown('run `a *b* c` now'), '<p>run <code>a *b* c</code> now</p>');
  assert.equal(renderMarkdown('```\n**x** <b>\n```'), '<pre><code>**x** &lt;b&gt;</code></pre>');
});

test('an unclosed code fence does not hang or lose text', () => {
  assert.equal(renderMarkdown('```\nabc'), '<pre><code>abc</code></pre>');
});

test('HTML in the text is escaped everywhere', () => {
  const evil = '<img src=x onerror="alert(1)">';
  for (const text of [evil, `# ${evil}`, `* ${evil}`, `**${evil}**`, `| ${evil} |\n| --- |\n| ${evil} |`, `> ${evil}`, `\`${evil}\``, '```\n' + evil + '\n```']) {
    const html = renderMarkdown(text);
    assert.ok(!html.includes('<img'), `unescaped tag in: ${html}`);
    assert.ok(html.includes('&lt;img'), `expected escaped text in: ${html}`);
  }
});

test('links and images are left as plain text', () => {
  const html = renderMarkdown('[click](javascript:alert(1)) ![x](http://e/x.png)');
  assert.ok(!html.includes('<a') && !html.includes('<img'));
});

test('empty and non-string input', () => {
  assert.equal(renderMarkdown(''), '');
  assert.equal(renderMarkdown(null), '');
  assert.equal(renderMarkdown(undefined), '');
});

test('blank lines separate paragraphs; rules and quotes work', () => {
  assert.equal(renderMarkdown('one\n\ntwo'), '<p>one</p>\n<p>two</p>');
  assert.equal(renderMarkdown('---'), '<hr>');
  assert.equal(renderMarkdown('> quoted'), '<blockquote>quoted</blockquote>');
});
