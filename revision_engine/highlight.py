"""Pygments highlighting emitted as one <div class="rv-line"> per source line."""

from __future__ import annotations

import re

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.util import ClassNotFound

from revision_engine.sources import SourceFile

# With linespans set, Pygments emits `<span id="L-n">…\n</span>` per line: the newline sits
# inside the span, before its close tag, and tokens never cross a line boundary.
_LINE_RE = re.compile(r'<span id="L-(\d+)">(.*?)\n</span>', re.S)


def _lexer(path: str):
    try:
        return get_lexer_for_filename(path, stripnl=False, ensurenl=False)
    except ClassNotFound:
        return TextLexer(stripnl=False, ensurenl=False)


def highlight_source(source: SourceFile) -> str:
    n = len(source.lines)
    if n == 0:
        return ""
    formatter = HtmlFormatter(linespans="L", cssclass="rvhl", nowrap=False)
    text = "\n".join(source.lines) + "\n"
    html = highlight(text, _lexer(source.path), formatter)
    inner = html[html.index("<pre>") + len("<pre>") : html.rindex("</pre>")]
    matches = _LINE_RE.findall(inner)
    if len(matches) != n:
        raise AssertionError(f"highlighter produced {len(matches)} lines for {n} source lines in {source.path}")

    out: list[str] = []
    for i, (_, code) in enumerate(matches, start=1):
        out.append(
            f'<div class="rv-line" id="L{i}" data-line="{i}">'
            f'<span class="rv-ln">{i}</span><span class="rv-code">{code}</span></div>'
        )
    return "\n".join(out) + "\n"


def _style_defs(style: str, selector: str) -> str:
    """Pygments token rules under `selector`, without the container background rule."""
    defs = HtmlFormatter(style=style).get_style_defs(selector)
    kept = [line for line in defs.splitlines() if not re.match(re.escape(selector) + r"\s*\{", line)]
    return "\n".join(kept)


def token_css() -> str:
    light = _style_defs("default", ".rv-code")
    dark_forced = _style_defs("github-dark", ':root[data-theme="dark"] .rv-code')
    dark_auto = _style_defs("github-dark", ':root:not([data-theme="light"]) .rv-code')
    return (
        f"{light}\n"
        f"@media (prefers-color-scheme: dark) {{\n{dark_auto}\n}}\n"
        f"{dark_forced}\n"
    )
