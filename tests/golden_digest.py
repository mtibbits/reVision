"""Hash a built site for the golden test, with each diagram reduced to its node structure.

Every file is hashed byte-for-byte except the inlined `<svg class="rv-svg">` diagrams in
HTML pages. Each of those is replaced by a digest of its nodes: id, class, data-node,
data-anchor and `<text>` labels, sorted. Graphviz's layout (coordinates, fonts, its own
graph and edge ids, emit order) is left out, because the engine does not own it.

Why not pin a Graphviz version in CI instead: Ubuntu's graphviz debs have no upstream
checksum, Graphviz ships a major release about every six weeks, and text is laid out with
OS fonts (Arial on Windows, DejaVu/Liberation on Linux), so layout bytes differ by platform
even at one version. The structure was measured identical on Graphviz 16.1.0 (Windows) and
Ubuntu's 2.42.2 package (reports 2.43.0).

Dependency output (Pygments, markdown-it-py, Jinja2) is still hashed byte-for-byte; their
floors-only pins are a known gap.

Stdlib only, Python 3.10+, so it can be loaded by path where the engine's venv is absent.
"""

from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path

_SVG_RE = re.compile(r'<svg class="rv-svg".*?</svg>', re.S)
_G_RE = re.compile(r"<g\b[^>]*>")
_TEXT_RE = re.compile(r"<text\b[^>]*>(.*?)</text>", re.S)
FIELDS = ("id", "class", "data-node", "data-anchor")


def _attr(tag: str, name: str) -> str:
    m = re.search(r'(?<![\w-])' + re.escape(name) + r'="([^"]*)"', tag)
    return html.unescape(m.group(1)) if m else ""


def svg_structure(svg: str) -> str:
    """One line per node `<g>`: id, class, data-node, data-anchor, labels; sorted."""
    starts = list(_G_RE.finditer(svg))
    lines = []
    for i, m in enumerate(starts):
        attrs = {f: _attr(m.group(0), f) for f in FIELDS}
        if "node" not in attrs["class"].split():
            continue
        end = starts[i + 1].start() if i + 1 < len(starts) else len(svg)
        labels = [html.unescape(t) for t in _TEXT_RE.findall(svg, m.end(), end)]
        lines.append("\t".join([*attrs.values(), "|".join(labels)]))
    return "\n".join(sorted(lines))


def golden_hashes(root: Path) -> tuple[dict[str, str], dict[str, int]]:
    """sha256 per file under root, plus how many diagrams each HTML file had normalised."""
    hashes: dict[str, str] = {}
    counts: dict[str, int] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        key = p.relative_to(root).as_posix()
        data = p.read_bytes()
        if p.suffix == ".html":
            text, n = _SVG_RE.subn(_digest, data.decode("utf-8"))
            counts[key] = n
            data = text.encode("utf-8")
        hashes[key] = hashlib.sha256(data).hexdigest()
    return hashes, counts


def _digest(m: re.Match) -> str:
    sha = hashlib.sha256(svg_structure(m.group(0)).encode("utf-8")).hexdigest()
    return f'<svg rv-golden-structure="{sha}"/>'
