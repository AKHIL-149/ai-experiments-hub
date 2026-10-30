// Small, safe markdown renderer for step results and saved reports.
// Every piece of text is escaped before any tag is added, so model output cannot inject HTML.
// Supported: headings, paragraphs, bold/italic, `code`, fenced code, bullet/numbered lists,
// tables, block quotes, horizontal rules. Links and images are left as plain text on purpose.

function mdEscape(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function mdInline(text) {
  const codes = [];
  let html = mdEscape(text).replace(/`([^`]+)`/g, (m, code) => {
    codes.push(code);
    return `\u0000${codes.length - 1}\u0000`;
  });
  html = html
    .replace(/\*\*(?=\S)(.+?)(?<=\S)\*\*/g, '<strong>$1</strong>')
    .replace(/(?<![\w*])\*(?=\S)([^*]+?)(?<=\S)\*(?![\w*])/g, '<em>$1</em>')
    .replace(/(?<![\w_])_(?=\S)([^_]+?)(?<=\S)_(?![\w_])/g, '<em>$1</em>');
  return html.replace(/\u0000(\d+)\u0000/g, (m, i) => `<code>${codes[Number(i)]}</code>`);
}

function mdTableCells(line) {
  let row = line.trim();
  if (row.startsWith('|')) row = row.slice(1);
  if (row.endsWith('|')) row = row.slice(0, -1);
  return row.split('|').map(cell => cell.trim());
}

const MD_TABLE_SEPARATOR = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
const MD_BULLET = /^\s*[-*+]\s+(.*)$/;
const MD_NUMBERED = /^\s*\d+[.)]\s+(.*)$/;

function renderMarkdown(source) {
  const lines = String(source ?? '').replace(/\r\n?/g, '\n').split('\n');
  const out = [];
  let i = 0;

  const startsBlock = (line, next) =>
    /^\s*(#{1,6})\s/.test(line) || /^\s*```/.test(line) || MD_BULLET.test(line) ||
    MD_NUMBERED.test(line) || /^\s*>/.test(line) || /^\s*([-*_])(\s*\1){2,}\s*$/.test(line) ||
    (line.includes('|') && next !== undefined && MD_TABLE_SEPARATOR.test(next) && next.includes('-'));

  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) { i += 1; continue; }

    if (/^\s*```/.test(line)) {
      const code = [];
      i += 1;
      while (i < lines.length && !/^\s*```/.test(lines[i])) code.push(lines[i++]);
      i += 1; // closing fence (or end of text)
      out.push(`<pre><code>${mdEscape(code.join('\n'))}</code></pre>`);
      continue;
    }

    const heading = line.match(/^\s*(#{1,6})\s+(.*?)\s*#*\s*$/);
    if (heading) {
      const level = heading[1].length;
      out.push(`<h${level}>${mdInline(heading[2])}</h${level}>`);
      i += 1;
      continue;
    }

    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) {
      out.push('<hr>');
      i += 1;
      continue;
    }

    if (line.includes('|') && i + 1 < lines.length && lines[i + 1].includes('-') && MD_TABLE_SEPARATOR.test(lines[i + 1])) {
      const header = mdTableCells(line);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].trim() && lines[i].includes('|')) rows.push(mdTableCells(lines[i++]));
      out.push(
        '<table><thead><tr>' + header.map(c => `<th>${mdInline(c)}</th>`).join('') + '</tr></thead><tbody>' +
        rows.map(r => '<tr>' + header.map((_, k) => `<td>${mdInline(r[k] ?? '')}</td>`).join('') + '</tr>').join('') +
        '</tbody></table>'
      );
      continue;
    }

    const listPattern = MD_BULLET.test(line) ? MD_BULLET : MD_NUMBERED.test(line) ? MD_NUMBERED : null;
    if (listPattern) {
      const tag = listPattern === MD_BULLET ? 'ul' : 'ol';
      const items = [];
      while (i < lines.length && listPattern.test(lines[i])) {
        items.push(lines[i++].match(listPattern)[1]);
      }
      out.push(`<${tag}>${items.map(item => `<li>${mdInline(item)}</li>`).join('')}</${tag}>`);
      continue;
    }

    if (/^\s*>/.test(line)) {
      const quote = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) quote.push(lines[i++].replace(/^\s*>\s?/, ''));
      out.push(`<blockquote>${mdInline(quote.join('\n')).replace(/\n/g, '<br>')}</blockquote>`);
      continue;
    }

    // Paragraph: consecutive lines, each line break kept
    const paragraph = [];
    while (i < lines.length && lines[i].trim() && !(paragraph.length && startsBlock(lines[i], lines[i + 1]))) {
      paragraph.push(lines[i++]);
    }
    out.push(`<p>${paragraph.map(mdInline).join('<br>')}</p>`);
  }

  return out.join('\n');
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { renderMarkdown };
}
