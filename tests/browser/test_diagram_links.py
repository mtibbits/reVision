"""A link on an anchored diagram node is stripped at build, so a click pins and Tab skips it; a free node keeps its link."""

from __future__ import annotations

import re

import pytest

from .conftest import HELLO_SRC, boxed, build_example, open_lesson, replace_once, serve

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
    def edit(src):
        for node, attr in EDITS.items():
            replace_once(src / HELLO_SRC / "diagrams/flow.dot", f'id="{node}"', f'id="{node}", {attr}')

    with serve(build_example(tmp_path_factory, "links", edit=edit)) as url:
        yield url + "intro/hello/"


@pytest.fixture
def links(page, links_url):
    page.context.route(
        re.compile(r"^https://example\.com/"),
        lambda r: r.fulfill(status=200, content_type="text/html", body="<p>stub</p>"),
    )
    popups: list[object] = []
    page.context.on("page", lambda p: popups.append(p))
    open_lesson(page, links_url)
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


# stamp_anchors gives each anchored <g> tabindex="0" at build, so it takes focus with or without app.js and is a Tab
# stop in every engine (#82).
def test_anchored_node_is_a_tab_stop(links):
    walk = tab_walk(links)
    assert walk["node"] is True, walk


def test_anchored_node_takes_focus_without_javascript(browser, links_url):
    ctx = browser.new_context(java_script_enabled=False)
    try:
        page = ctx.new_page()
        page.goto(links_url)
        node = page.locator(NODE)
        node.focus()
        assert node.evaluate("g => g === document.activeElement")
        # Reload rather than blur: Firefox resumes Tab after the blurred node and does not wrap back to it.
        page.goto(links_url)
        reached = False
        for _ in range(200):
            page.keyboard.press("Tab")
            if node.evaluate("g => g === document.activeElement"):
                reached = True
                break
        assert reached
    finally:
        ctx.close()


# Click the node, not its <text>: WebKit reports the box of SVG <text> in these nodes far from where it is drawn
# (on the caption), so Playwright's click point misses; the <g>'s box is right and its centre hits the <text>.
def test_click_on_anchored_linked_node_pins(links):
    links.click(NODE)
    links.wait_for_timeout(WINDOW_MS)
    assert links.evaluate("location.hash") == "#add-fn"
    assert "rv-pinned" in (links.locator(NODE).get_attribute("class") or "").split()
    assert links.popups == []


def test_enter_on_anchored_linked_node_pins(links):
    # The lesson's start anchor is add-fn, so its lines are boxed on load; clear them so focus has to re-box them.
    expected = boxed(links)
    assert expected != []
    links.evaluate("RV.clearBox()")
    assert boxed(links) == []
    links.locator(NODE).focus()
    assert links.locator(NODE).evaluate("g => g === document.activeElement")
    assert boxed(links) == expected
    links.keyboard.press("Enter")
    links.wait_for_function("location.hash === '#add-fn'", timeout=WINDOW_MS)
    assert "rv-pinned" in (links.locator(NODE).get_attribute("class") or "").split()
    assert links.popups == []


def test_free_node_link_still_navigates(links):
    links.click(FREE)
    links.wait_for_url("https://example.com/printf", timeout=WINDOW_MS)
