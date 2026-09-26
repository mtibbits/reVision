import re

from revision_engine.highlight import highlight_source, token_css
from revision_engine.sources import SourceFile


def src(text: str, path="a.c") -> SourceFile:
    body = text[:-1] if text.endswith("\n") else text
    return SourceFile(path=path, text=text, lines=tuple(body.split("\n")) if body else ())


def test_one_div_per_line_with_numbers():
    html = highlight_source(src("int x;\nint y;\n"))
    assert html.count('class="rv-line"') == 2
    assert 'id="L1" data-line="1"' in html and 'id="L2" data-line="2"' in html
    assert '<span class="rv-ln">2</span>' in html


def test_multiline_comment_does_not_break_line_wrapping():
    html = highlight_source(src("/* a\n   b\n   c */\nint x;\n"))
    divs = re.findall(r'<div class="rv-line"[^>]*>.*?</div>', html, re.S)
    assert len(divs) == 4
    for d in divs:
        assert d.count("<span") == d.count("</span>")


def test_blank_and_last_line_without_newline_preserved():
    html = highlight_source(src("a\n\nb"))
    assert html.count('class="rv-line"') == 3


def test_tokens_get_pygments_classes_and_html_is_escaped():
    html = highlight_source(src("#include <stdio.h>\nif (a < b) {}\n"))
    assert "&lt;stdio.h&gt;" in html and "&lt;" in html
    assert 'class="k"' in html or 'class="cp"' in html


def test_unknown_extension_falls_back_to_plain_text():
    html = highlight_source(src("hello world\n", path="notes.zzz"))
    assert html.count('class="rv-line"') == 1 and "hello world" in html


def test_token_css_is_scoped():
    css = token_css()
    assert ".rv-code .k" in css or ".rv-code .k " in css


def test_token_css_has_dark_variants_and_no_container_background():
    css = token_css()
    assert ':root[data-theme="dark"] .rv-code .k' in css
    assert "@media (prefers-color-scheme: dark)" in css and ':root:not([data-theme="light"]) .rv-code .k' in css
    assert not re.search(r"^\.rv-code\s*\{[^}]*background", css, re.M)
