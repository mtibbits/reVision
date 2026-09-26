"""Render Graphviz dot files to inline SVG and stamp node ids for the front end."""

from __future__ import annotations

import html
import re
import shutil
import subprocess
from pathlib import Path

from revision_engine.errors import BuildError

_STRIP_RES = (
    re.compile(r"<\?xml[^>]*\?>\s*"),
    re.compile(r"<!DOCTYPE[^>]*>\s*"),
    re.compile(r"<!--.*?-->\s*", re.S),
)
_NODE_RE = re.compile(r'<g id="([^"]+)" class="node"')
_SVG_OPEN_RE = re.compile(r"<svg\b")


def graphviz_version() -> str | None:
    if shutil.which("dot") is None:
        return None
    out = subprocess.run(["dot", "-V"], capture_output=True, text=True, check=False)
    m = re.search(r"version\s+(\S+)", out.stderr + out.stdout)
    return m.group(1) if m else None


def render_dot(path: Path, where: str) -> str:
    if shutil.which("dot") is None:
        raise BuildError(f"{where}: graphviz 'dot' is not installed or not on PATH")
    proc = subprocess.run(
        ["dot", "-Tsvg", "-Gbgcolor=transparent", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if proc.returncode != 0:
        raise BuildError(f"{where}: graphviz failed: {proc.stderr.strip()}")
    svg = proc.stdout
    for rx in _STRIP_RES:
        svg = rx.sub("", svg)
    svg = svg.strip()

    def node(m: re.Match) -> str:
        # Graphviz entity-escapes ids (a hyphen becomes &#45;); restore the author's spelling.
        name = html.unescape(m.group(1))
        return f'<g id="{name}" class="node" data-node="{name}"'

    svg = _NODE_RE.sub(node, svg)
    svg = _SVG_OPEN_RE.sub('<svg class="rv-svg"', svg, count=1)
    return svg


def stamp_anchors(svg: str, anchor_names: set[str]) -> str:
    def repl(m: re.Match) -> str:
        node = m.group(1)
        if node in anchor_names:
            return f'<g id="{node}" class="node rv-svg-anchor" data-node="{node}" data-anchor="{node}"'
        return m.group(0)

    return re.sub(r'<g id="([^"]+)" class="node" data-node="[^"]+"', repl, svg)
