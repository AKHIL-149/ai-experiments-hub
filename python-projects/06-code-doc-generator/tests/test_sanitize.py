"""The documentation page shows generated HTML to the user, so anything that could run script must go."""
import pytest

from src.web.sanitize import sanitize_html


def clean(html):
    return sanitize_html(html)


# ------------------------------------------------------------------ what must survive

def test_ordinary_documentation_markup_is_kept():
    html = ('<h1 id="mod">Module</h1><p>Some <strong>bold</strong>, <em>italic</em> and <code>code</code>.</p>'
            '<ul><li>one</li><li>two</li></ul><pre><code class="language-python">x = 1\n</code></pre>'
            '<table><thead><tr><th>a</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table><hr><blockquote>q</blockquote>')
    assert clean(html) == html.replace('<hr>', '<hr>')


def test_text_is_escaped_not_dropped():
    assert clean('a < b & c > d') == 'a &lt; b &amp; c &gt; d'
    assert clean('<p>5 &lt; 6</p>') == '<p>5 &lt; 6</p>'


def test_safe_links_keep_their_href_and_get_rel():
    out = clean('<a href="https://example.com/x?y=1&amp;z=2">site</a>')
    assert 'href="https://example.com/x?y=1&amp;z=2"' in out and 'rel="noopener noreferrer"' in out and '>site</a>' in out
    assert 'href="#section-1"' in clean('<a href="#section-1">go</a>')
    assert 'href="mailto:a@b.c"' in clean('<a href="mailto:a@b.c">mail</a>')
    assert 'href="docs/page.html"' in clean('<a href="docs/page.html">rel</a>')


# ------------------------------------------------------------------ script and handlers

@pytest.mark.parametrize('payload', [
    '<script>alert(1)</script>',
    '<SCRIPT SRC=//evil.example/x.js></SCRIPT>',
    '<scr<script>ipt>alert(1)</scr</script>ipt>',
    '<img src=x onerror=alert(1)>',
    '<img src="x" onerror="alert(1)">',
    '<svg onload=alert(1)>',
    '<svg><script>alert(1)</script></svg>',
    '<body onload=alert(1)>',
    '<div onclick="alert(1)">x</div>',
    '<p onmouseover=alert(1)>x</p>',
    '<iframe src="javascript:alert(1)"></iframe>',
    '<iframe srcdoc="<script>alert(1)</script>"></iframe>',
    '<object data="data:text/html,<script>alert(1)</script>"></object>',
    '<embed src="javascript:alert(1)">',
    '<math><mtext></mtext><script>alert(1)</script></math>',
    '<form action="javascript:alert(1)"><input type=submit></form>',
    '<style>@import "javascript:alert(1)";</style>',
    '<link rel=stylesheet href=//evil.example/x.css>',
    '<meta http-equiv="refresh" content="0;url=javascript:alert(1)">',
    '<base href="//evil.example/">',
    '<details open ontoggle=alert(1)>x</details>',
    '<video><source onerror=alert(1)></video>',
    '<a href="javascript:alert(1)">x</a>',
    '<a href="JaVaScRiPt:alert(1)">x</a>',
    '<a href="java\nscript:alert(1)">x</a>',
    '<a href="  javascript:alert(1)">x</a>',
    '<a href="&#106;avascript:alert(1)">x</a>',
    '<a href="jav&#x61;script:alert(1)">x</a>',
    '<a href="data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==">x</a>',
    '<a href="vbscript:msgbox(1)">x</a>',
    '<a style="x" href="https://ok.example" onclick="alert(1)">x</a>',
    '<div style="background:url(javascript:alert(1))">x</div>',
    '<p><!--[if IE]><script>alert(1)</script><![endif]--></p>',
    '<![CDATA[<script>alert(1)</script>]]>',
    '<?php echo 1; ?>',
    '<noscript><p title="</noscript><img src=x onerror=alert(1)>">',
    '<textarea></textarea><script>alert(1)</script>',
    '<template><script>alert(1)</script></template>',
    '"><script>alert(1)</script>',
])
def test_nothing_that_can_run_script_survives(payload):
    out = clean(payload).lower()
    for needle in ('<script', 'onerror', 'onload', 'onclick', 'onmouseover', 'ontoggle', 'javascript:', 'vbscript:',
                   '<iframe', '<object', '<embed', '<svg', '<math', '<form', '<style', '<link', '<meta', '<base',
                   'data:text/html', 'srcdoc', 'alert(1)<'):
        assert needle not in out, f'{needle!r} survived in {out!r} (from {payload!r})'
    assert ' on' not in out.replace(' one', '')  # no event-handler attribute of any kind


def test_dangerous_elements_lose_their_contents_but_harmless_unknown_ones_keep_their_text():
    assert clean('<p>a</p><script>steal()</script><p>b</p>') == '<p>a</p><p>b</p>'
    assert clean('<style>.x{}</style>text') == 'text'
    assert clean('<blink>hello</blink>') == 'hello'
    assert clean('<custom-tag>hello</custom-tag>') == 'hello'


def test_images_become_their_alt_text():
    assert clean('<img src="https://x.example/a.png" alt="a diagram">') == 'a diagram'
    assert clean('<img src=x>') == ''


def test_attributes_outside_the_allowlist_are_removed():
    out = clean('<p class="note x" id="p1" style="color:red" data-x="1" title="t" onfocus="1" contenteditable>t</p>')
    assert out == '<p class="note x" id="p1">t</p>'
    assert clean('<code class="language-py&quot; onmouseover=&quot;x">c</code>') == '<code>c</code>'
    assert clean('<h2 id="a b&quot;c">h</h2>') == '<h2>h</h2>'


def test_table_cell_attributes_are_limited_to_layout_numbers():
    assert clean('<td colspan="2" align="right">x</td>') == '<td colspan="2" align="right">x</td>'
    assert clean('<td colspan="2&quot; onclick=&quot;x" align="javascript:1">x</td>') == '<td>x</td>'


# ------------------------------------------------------------------ structure

def test_unclosed_tags_are_closed_so_the_rest_of_the_page_is_not_swallowed():
    assert clean('<div><p>a') == '<div><p>a</p></div>'
    assert clean('<ul><li>a<li>b') == '<ul><li>a</li><li>b</li></ul>'


def test_stray_closing_tags_are_ignored():
    assert clean('a</p></div>b') == 'ab'
    assert clean('</script><p>x</p>') == '<p>x</p>'


def test_broken_markup_does_not_crash():
    for html in ['<', '<<>>', '<a href=', '<a href="x', '&', '&#', '&#xZZ;', '<p', '</', '<!--', '<!-- x', '\x00<p>x</p>\x00']:
        assert isinstance(clean(html), str)


def test_nesting_depth_is_limited():
    deep = '<div>' * 5000 + 'x' + '</div>' * 5000
    out = clean(deep)
    assert 'x' in out and out.count('<div>') <= 200


def test_empty_and_none():
    assert clean('') == '' and clean(None) == ''


def test_output_is_idempotent():
    html = '<p>a &lt; b <a href="https://e.com">l</a></p><pre><code>x &amp; y</code></pre>'
    assert clean(clean(html)) == clean(html)


# ------------------------------------------------------------------ gaps found by mutation testing

@pytest.mark.parametrize('html', [
    '<iframe>IFRAME-TEXT</iframe>', '<svg><text>SVG-TEXT</text></svg>', '<title>TITLE-TEXT</title>',
    '<object>OBJ-TEXT</object>', '<math><mi>MATH-TEXT</mi></math>', '<form>FORM-TEXT</form>', '<video>VIDEO-TEXT</video>',
])
def test_the_contents_of_dangerous_elements_are_dropped_with_them(html):
    assert clean(f'a{html}b') == 'ab'


def test_nested_dangerous_elements_are_removed_as_a_whole():
    assert clean('<svg><svg></svg><image onerror=1>LEAK</svg>after') == 'after'
    assert clean('<iframe><iframe></iframe>LEAK</iframe>after') == 'after'
    # script and style are raw-text elements: like a browser, the first closing tag ends them
    assert clean('<style>a{}<style></style>LEAK</style>after') == 'LEAKafter'


def test_alt_text_from_images_is_escaped():
    assert clean('<img src=x alt="<script>alert(1)</script>">') == '&lt;script&gt;alert(1)&lt;/script&gt;'
    assert clean('<img alt="a &amp; b">') == 'a &amp; b'


def test_scheme_names_are_case_insensitive_for_safe_links():
    assert 'href="HTTPS://Example.com/A"' in clean('<a href="HTTPS://Example.com/A">x</a>')
    assert 'href="MailTo:a@b.c"' in clean('<a href="MailTo:a@b.c">x</a>')


def test_fragment_links_must_look_like_ids():
    assert 'href=' not in clean('<a href="#a b">x</a>')
    assert 'href=' not in clean('<a href="#a&quot;onclick=&quot;1">x</a>')
    assert 'href="#"' in clean('<a href="#">x</a>')


@pytest.mark.parametrize('href', ['java\tscript:alert(1)', 'java\nscript:alert(1)', 'java\rscript:alert(1)', '\x01javascript:alert(1)',
                                  'javascript​:alert(1)', 'a:b', 'x:1', ' \nhttps://ok.example', '//evil.example/x', 'data:image/png;base64,AAAA'])
def test_only_real_http_mailto_and_relative_links_are_kept(href):
    out = clean(f'<a href="{href}">x</a>')
    if href.strip().startswith(('https://', '//')):
        assert 'href=' in out
    else:
        assert 'href=' not in out, out
