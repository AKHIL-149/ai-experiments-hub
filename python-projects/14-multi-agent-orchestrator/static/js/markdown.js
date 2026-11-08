/*
 * A small, safe markdown reader for the answers agents write (headings, **bold**, *italic*, `code`, lists,
 * code fences, links). It only produces a plain data tree: the page turns that into elements with
 * textContent, so nothing a model writes is ever parsed as HTML. No DOM here, so it can be tested in node.
 *
 * parse(text) -> blocks:
 *   { type: 'heading', inline }  { type: 'p', lines: [inline, ...] }  { type: 'code', text }
 *   { type: 'list', ordered, items: [{ level, inline }] }
 * inline is a list of { t: 'text'|'code'|'strong'|'em'|'link', v?, c?, href? }.
 */
(function (root) {
    'use strict';

    // `code` | **bold** | __bold__ | [text](https://url) | *italic* (not "* " bullets or "2 * 3 * 4")
    const INLINE = /(`[^`\n]+`)|(\*\*(?:[^*\n]|\*(?!\*))+?\*\*|__[^_\n]+?__)|(\[[^\]\n]+\]\((https?:\/\/[^\s)]+)\))|(\*[^*\s][^*\n]*?[^*\s]\*|\*[^*\s]\*)/g;
    const FENCE = /^\s*```[\w+-]*\s*$/;
    const RULE = /^\s*([=\-_*])(\s*\1){2,}\s*$/;
    const HEADING = /^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$/;
    const BOLD_LINE = /^\s*(?:\*\*|__)([^*_\n]+?)(?:\*\*|__)\s*:?\s*$/;
    const ITEM = /^(\s*)([*\-+•]|\d+[.)])\s+(.*)$/;

    function inline(text) {
        const out = [];
        let last = 0, match;
        // a regex of its own per call: inline() calls itself for nested markup, and a shared global regex would
        // have its position reset by that inner call, so the outer loop would never end
        const pattern = new RegExp(INLINE.source, 'g');
        while ((match = pattern.exec(text)) !== null) {
            if (match.index > last) out.push({ t: 'text', v: text.slice(last, match.index) });
            if (match[1]) out.push({ t: 'code', v: match[1].slice(1, -1) });
            else if (match[2]) out.push({ t: 'strong', c: inline(match[2].slice(2, -2)) });
            else if (match[3]) out.push({ t: 'link', v: match[3].slice(1, match[3].indexOf(']')), href: match[4] });
            else out.push({ t: 'em', c: inline(match[5].slice(1, -1)) });
            last = match.index + match[0].length;
        }
        if (last < text.length) out.push({ t: 'text', v: text.slice(last) });
        return out;
    }

    function parse(source) {
        const lines = String(source === null || source === undefined ? '' : source).replace(/\r\n?/g, '\n').split('\n');
        const blocks = [];
        let paragraph = [];
        let list = null;

        const flushParagraph = () => {
            if (paragraph.length) blocks.push({ type: 'p', lines: paragraph.map(inline) });
            paragraph = [];
        };
        const flushList = () => { list = null; };

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];

            if (FENCE.test(line)) {
                flushParagraph(); flushList();
                const code = [];
                i++;
                while (i < lines.length && !FENCE.test(lines[i])) code.push(lines[i++]);
                blocks.push({ type: 'code', text: code.join('\n') });
                continue;
            }
            if (!line.trim()) { flushParagraph(); flushList(); continue; }
            if (RULE.test(line)) { flushParagraph(); flushList(); continue; }   // "-----" and "=====" lines

            let found = line.match(HEADING) || line.match(BOLD_LINE);
            if (found) {
                flushParagraph(); flushList();
                blocks.push({ type: 'heading', inline: inline(found[1].replace(/:\s*$/, '')) });
                continue;
            }

            found = line.match(ITEM);
            if (found) {
                flushParagraph();
                const ordered = /\d/.test(found[2]);
                if (!list || list.ordered !== ordered) { list = { type: 'list', ordered, items: [] }; blocks.push(list); }
                const width = found[1].replace(/\t/g, '    ').length;
                list.items.push({ level: Math.min(3, Math.floor(width / 2)), inline: inline(found[3]) });
                continue;
            }

            // an indented line right under a list item continues that item
            if (list && /^\s+\S/.test(line)) {
                const item = list.items[list.items.length - 1];
                item.inline = item.inline.concat([{ t: 'text', v: ' ' }], inline(line.trim()));
                continue;
            }
            flushList();
            paragraph.push(line);
        }
        flushParagraph();
        return blocks;
    }

    const api = { parse, inline };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else root.TrackerMarkdown = api;
})(typeof window !== 'undefined' ? window : globalThis);
