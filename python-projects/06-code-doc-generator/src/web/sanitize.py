"""Allowlist HTML sanitizer for documentation shown in the browser.

Generated documentation contains text taken from the user's own code (docstrings, names, default
values), and the results page also accepts the documentation as a form field, so anything shown
as HTML must be reduced to harmless markup first. The rule is an allowlist: only the tags and
attributes below survive, everything is re-escaped on output, and URLs are limited to a few
schemes. There is no HTML library dependency on purpose: the parser is the standard one.
"""
import re
from html import escape
from html.parser import HTMLParser
from typing import Dict, List, Optional

ALLOWED_TAGS = {
    'a', 'abbr', 'b', 'blockquote', 'br', 'code', 'dd', 'del', 'details', 'div', 'dl', 'dt', 'em',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'i', 'li', 'ol', 'p', 'pre', 's', 'small', 'span',
    'strong', 'sub', 'summary', 'sup', 'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr', 'ul',
}
VOID_TAGS = {'br', 'hr'}
# These are removed together with everything inside them
DROP_WITH_CONTENT = {
    'script', 'style', 'iframe', 'object', 'embed', 'svg', 'math', 'form', 'textarea', 'select',
    'title', 'noscript', 'template', 'head', 'frameset', 'applet', 'audio', 'video', 'canvas',
    'button', 'xmp', 'plaintext', 'noembed', 'noframes',
}
# Starting one of these closes an open sibling of the kind listed (as HTML does: <li>a<li>b is two items)
IMPLICITLY_CLOSES = {
    'li': ('li',), 'dt': ('dt', 'dd'), 'dd': ('dt', 'dd'),
    'td': ('td', 'th'), 'th': ('td', 'th'),
    'tr': ('td', 'th', 'tr'), 'tbody': ('tbody', 'thead', 'tfoot'), 'thead': ('tbody', 'thead', 'tfoot'),
    'tfoot': ('tbody', 'thead', 'tfoot'),
}
# ...but only if no container of the same family sits between them
CONTAINERS = {'li': ('ul', 'ol'), 'dt': ('dl',), 'dd': ('dl',), 'td': ('tr', 'table'), 'th': ('tr', 'table'),
              'tr': ('table', 'tbody', 'thead', 'tfoot'), 'tbody': ('table',), 'thead': ('table',), 'tfoot': ('table',)}
MAX_DEPTH = 100
SAFE_SCHEMES = {'http', 'https', 'mailto'}

_CLASS = re.compile(r'^[\w\- ]{1,100}$')
_ID = re.compile(r'^[\w\-:.]{1,100}$')
_NUMBER = re.compile(r'^\d{1,3}$')
_ALIGN = {'left', 'right', 'center'}
_CONTROL = re.compile(r'[\x00-\x20\x7f-\x9f​-‏  ﻿]+')


def _safe_url(value: str) -> Optional[str]:
    """The URL if it is harmless, else None."""
    squeezed = _CONTROL.sub('', value)          # "java\nscript:" and similar tricks
    if not squeezed:
        return None
    if squeezed.startswith('#'):
        fragment = value.strip()           # validated as written: no spaces or control characters inside
        return fragment if fragment == '#' or _ID.match(fragment[1:]) else None
    match = re.match(r'^([a-zA-Z][a-zA-Z0-9+.\-]*):', squeezed)
    if match:
        return value.strip() if match.group(1).lower() in SAFE_SCHEMES else None
    if ':' in squeezed.split('/')[0].split('?')[0].split('#')[0]:
        return None                              # a colon before any slash always means a scheme
    return value.strip()


def _clean_attrs(tag: str, attrs) -> List[str]:
    """The allowed attributes of a tag, ready to write."""
    out: List[str] = []
    seen = set()
    for name, value in attrs:
        name = (name or '').lower()
        value = value if value is not None else ''
        if name in seen:
            continue
        keep: Optional[str] = None
        if name == 'class' and _CLASS.match(value):
            keep = value
        elif name == 'id' and _ID.match(value):
            keep = value
        elif tag == 'a' and name == 'href':
            keep = _safe_url(value)
        elif tag == 'a' and name == 'title':
            keep = value[:200]
        elif tag in ('td', 'th') and name in ('colspan', 'rowspan') and _NUMBER.match(value):
            keep = value
        elif tag in ('td', 'th') and name == 'align' and value.lower() in _ALIGN:
            keep = value.lower()
        if keep is not None:
            seen.add(name)
            out.append(f'{name}="{escape(keep, quote=True)}"')
    if tag == 'a' and any(a.startswith('href=') for a in out):
        out.append('rel="noopener noreferrer"')
    return out


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: List[str] = []
        self.stack: List[str] = []
        self.skipping: Optional[str] = None     # name of the dangerous element whose content is being dropped
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.skipping:
            if tag == self.skipping:
                self.skip_depth += 1
            return
        if tag in DROP_WITH_CONTENT:
            self.skipping, self.skip_depth = tag, 1
            return
        if tag == 'img':
            alt = dict((n.lower(), v) for n, v in attrs).get('alt')
            if alt:
                self.out.append(escape(alt))
            return
        if tag not in ALLOWED_TAGS:
            return                              # the tag goes, its text stays (escaped)
        self._close_siblings(tag)
        if len(self.stack) >= MAX_DEPTH and tag not in VOID_TAGS:
            return
        attrs_text = _clean_attrs(tag, attrs)
        self.out.append(f'<{tag}{" " + " ".join(attrs_text) if attrs_text else ""}>')
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def _close_siblings(self, tag):
        closes = IMPLICITLY_CLOSES.get(tag)
        if not closes:
            return
        walls = CONTAINERS[tag]
        for open_tag in reversed(self.stack):
            if open_tag in walls:
                return
            if open_tag in closes:
                while self.stack:
                    top = self.stack.pop()
                    self.out.append(f'</{top}>')
                    if top == open_tag:
                        return
        return

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS and tag.lower() in ALLOWED_TAGS and not self.skipping:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.skipping:
            if tag == self.skipping:
                self.skip_depth -= 1
                if self.skip_depth == 0:
                    self.skipping = None
            return
        if tag not in self.stack:
            return                              # stray closing tag
        while self.stack:
            top = self.stack.pop()
            self.out.append(f'</{top}>')
            if top == tag:
                break

    def handle_data(self, data):
        if not self.skipping:
            self.out.append(escape(data.replace('\x00', '')))

    # comments, doctypes, CDATA and processing instructions are dropped
    def handle_comment(self, data):
        pass

    def handle_decl(self, decl):
        pass

    def handle_pi(self, data):
        pass

    def unknown_decl(self, data):
        pass

    def result(self) -> str:
        while self.stack:
            self.out.append(f'</{self.stack.pop()}>')
        return ''.join(self.out)


def sanitize_html(html: Optional[str]) -> str:
    """Return a safe version of the HTML: only allowlisted markup, escaped text, safe links."""
    if not html:
        return ''
    parser = _Sanitizer()
    parser.feed(html)
    parser.close()
    return parser.result()
