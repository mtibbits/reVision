"""A link on an anchored diagram node is stripped at build, so a click pins and Tab skips it; a free node keeps its link."""

from __future__ import annotations

import http.server
import re
import shutil
import threading
from functools import partial
from pathlib import Path

import pytest

from revision_engine.build import build

from .conftest import FIXED, _QuietHandler

EDITS = {"add-fn": 'URL="https://example.com/add"', "printf-node": 'href="https://example.com/printf"'}
# Every selector is SVG-scoped: the variant button and the phrase span also carry data-anchor="add-fn".
NODE = '.rv-svg g[data-anchor="add-fn"]'
FREE = '.rv-svg g[data-node="printf-node"]'
WINDOW_MS = 3000
LINKED = (
    "els => els.filter(a => a.hasAttribute('href')"
    " || a.hasAttributeNS('http://www.w3.org/1999/xlink', 'href')).length"
)


@pytest.fixture(scope="module")
def links_url(tmp_path_factory):
    root = tmp_path_factory.mktemp("links")
    src = root / "m"
    shutil.copytree(Path(__file__).resolve().parents[2] / "examples" / "minimal", src)
    dot = src / "docs/revision/chapters/01-intro/lessons/01-hello/diagrams/flow.dot"
    text = dot.read_text(encoding="utf-8")
    for node, attr in EDITS.items():
        assert text.count(f'id="{node}"') == 1
        text = text.replace(f'id="{node}"', f'id="{node}", {attr}')
    dot.write_text(text, encoding="utf-8", newline="\n")
    out = root / "out"
    build(src, output=out, commit=FIXED)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(_QuietHandler, directory=str(out)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/intro/hello/"
    server.shutdown()


@pytest.fixture
def links(page, links_url):
    page.context.route(
        re.compile(r"^https://example\.com/"),
        lambda r: r.fulfill(status=200, content_type="text/html", body="<p>stub</p>"),
    )
    errors: list[str] = []
    popups: list[object] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.context.on("page", lambda p: popups.append(p))
    page.goto(links_url)
    page.wait_for_function("window.RV !== undefined")
    page.errors = errors  # type: ignore[attr-defined]
    page.popups = popups  # type: ignore[attr-defined]
    return page


def test_fixture_anchored_node_has_no_link_and_free_node_keeps_one(links):
    assert links.locator(NODE).count() == 1
    assert links.locator(NODE + " a").count() >= 1
    assert links.locator(NODE + " a").evaluate_all(LINKED) == 0
    assert links.locator(FREE + " a").evaluate_all(LINKED) == 1
    assert links.errors == []


def test_stripped_link_is_not_a_tab_stop(links):
    # Walk the real Tab order: Chromium reports tabIndex 0 for an href-less SVG <a> yet never stops on it.
    # The anchored <g> itself is a live stop (app.js's focus listeners make it focusable; Enter pins), so
    # only an <a> inside the node would be the dead stop.
    assert links.locator(NODE + " a").count() >= 1
    links.evaluate(
        """([node, free]) => {
            window.__nodeLink = false;
            window.__node = false;
            window.__free = false;
            document.addEventListener('focusin', (e) => {
                if (e.target.matches(node)) window.__node = true;
                if (e.target.closest(node + ' a')) window.__nodeLink = true;
                if (e.target.closest(free + ' a')) window.__free = true;
            });
            if (document.activeElement) document.activeElement.blur();
        }""",
        [NODE, FREE],
    )
    for _ in range(200):
        links.keyboard.press("Tab")
    assert links.evaluate("window.__free") is True
    assert links.evaluate("window.__node") is True
    assert links.evaluate("window.__nodeLink") is False


def test_click_on_anchored_linked_node_pins(links):
    links.click(NODE + " text")
    links.wait_for_timeout(WINDOW_MS)
    assert links.evaluate("location.hash") == "#add-fn"
    assert "rv-pinned" in (links.locator(NODE).get_attribute("class") or "").split()
    assert links.popups == []


def test_free_node_link_still_navigates(links):
    links.click(FREE + " text")
    links.wait_for_url("https://example.com/printf", timeout=WINDOW_MS)
