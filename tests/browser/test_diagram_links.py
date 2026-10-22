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
# app.js's focus listeners make the anchored <g> a live stop (Enter pins), but it sets no tabindex, so the <g>
# takes focus only in Blink (#82).
G_UNFOCUSABLE = pytest.mark.xfail_browser(
    "firefox", "webkit", reason="anchored diagram <g> is not focusable outside Blink: listeners but no tabindex (#82)",
    raises=AssertionError,
)
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


def tab_walk(links) -> dict:
    """Tab through the page and report which of the free node's link, the anchored node, and its link took focus."""
    links.evaluate(
        """([node, free]) => {
            window.__walk = { free: false, node: false, nodeLink: false };
            document.addEventListener('focusin', (e) => {
                if (e.target.matches(node)) window.__walk.node = true;
                if (e.target.closest(node + ' a')) window.__walk.nodeLink = true;
                if (e.target.closest(free + ' a')) window.__walk.free = true;
            });
            if (document.activeElement) document.activeElement.blur();
        }""",
        [NODE, FREE],
    )
    for _ in range(200):
        links.keyboard.press("Tab")
    return links.evaluate("window.__walk")


@pytest.mark.xfail_browser(
    "webkit",
    platforms=("win32",),
    reason="WebKit on Windows skips links on Tab, so the free node's link is never reached (#81)",
    raises=AssertionError,
)
def test_stripped_link_is_not_a_tab_stop(links):
    # Walk the real Tab order: Chromium reports tabIndex 0 for an href-less SVG <a> yet never stops on it.
    assert links.locator(NODE + " a").count() >= 1
    walk = tab_walk(links)
    assert walk["free"] is True, walk  # the walk reached a diagram link at all
    assert walk["nodeLink"] is False, walk


@G_UNFOCUSABLE
def test_anchored_node_is_a_tab_stop(links):
    walk = tab_walk(links)
    assert walk["node"] is True, walk


# Click the node, not its <text>: WebKit reports the box of SVG <text> in these nodes far from where it is drawn
# (on the caption), so Playwright's click point misses; the <g>'s box is right and its centre hits the <text>.
def test_click_on_anchored_linked_node_pins(links):
    links.click(NODE)
    links.wait_for_timeout(WINDOW_MS)
    assert links.evaluate("location.hash") == "#add-fn"
    assert "rv-pinned" in (links.locator(NODE).get_attribute("class") or "").split()
    assert links.popups == []


@G_UNFOCUSABLE
def test_enter_on_anchored_linked_node_pins(links):
    links.locator(NODE).focus()
    assert links.locator(NODE).evaluate("g => g === document.activeElement")
    links.keyboard.press("Enter")
    links.wait_for_function("location.hash === '#add-fn'", timeout=WINDOW_MS)
    assert "rv-pinned" in (links.locator(NODE).get_attribute("class") or "").split()
    assert links.popups == []


def test_free_node_link_still_navigates(links):
    links.click(FREE)
    links.wait_for_url("https://example.com/printf", timeout=WINDOW_MS)
