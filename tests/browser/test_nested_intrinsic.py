"""An intrinsic link inside an anchor phrase opens on click and Enter; the rest of the phrase still pins."""

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

OLD = "replace the single addition with something like `_mm256_fmadd_ps`,"
NEW = "replace [the single addition with something like `_mm256_fmadd_ps`](@add-expr),"
PHRASE = '.rv-anchor[data-anchor="add-expr"]:has(a.rv-intrinsic)'
LINK = PHRASE + " a.rv-intrinsic"


@pytest.fixture(scope="module")
def nested_url(tmp_path_factory):
    root = tmp_path_factory.mktemp("nested")
    src = root / "m"
    shutil.copytree(Path(__file__).resolve().parents[2] / "examples" / "minimal", src)
    lesson = src / "docs/revision/chapters/01-intro/lessons/01-hello/lesson.md"
    text = lesson.read_text(encoding="utf-8")
    assert text.count(OLD) == 1
    lesson.write_text(text.replace(OLD, NEW), encoding="utf-8")
    out = root / "out"
    build(src, output=out, commit=FIXED)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(_QuietHandler, directory=str(out)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/intro/hello/"
    server.shutdown()


@pytest.fixture
def nested(page, nested_url):
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(nested_url)
    page.wait_for_function("window.RV !== undefined")
    page.errors = errors  # type: ignore[attr-defined]
    return page


def boxed(page):
    return page.evaluate("Array.from(document.querySelectorAll('.rv-line.rv-boxed')).map(l => +l.dataset.line)")


def stub_vendor(page) -> str:
    """Answer the vendor URL locally, on the context so the popup is covered too."""
    href = page.locator(LINK).get_attribute("href")
    assert href.startswith("https://")
    page.context.route(
        re.compile("^" + re.escape(href.split("#")[0])),
        lambda r: r.fulfill(status=200, content_type="text/html", body="<p>vendor</p>"),
    )
    return href


def test_fixture_nests_one_intrinsic_link_in_the_phrase(nested):
    assert nested.locator(LINK).count() == 1
    assert "_mm256_fmadd_ps" in nested.locator(LINK).get_attribute("href")
    assert nested.errors == []


def test_click_on_nested_link_opens_it_and_does_not_pin(nested):
    href = stub_vendor(nested)
    with nested.expect_popup(timeout=3000) as info:
        nested.click(LINK)
    popup = info.value
    popup.wait_for_load_state()
    assert popup.url == href
    assert nested.evaluate("window.RV.pinned") is None
    assert nested.evaluate("location.hash") == ""
    assert not nested.evaluate("document.body.classList.contains('rv-pinned')")


def test_enter_on_focused_nested_link_opens_it(nested):
    href = stub_vendor(nested)
    nested.locator(LINK).focus()
    with nested.expect_popup(timeout=3000) as info:
        nested.keyboard.press("Enter")
    popup = info.value
    popup.wait_for_load_state()
    assert popup.url == href
    assert nested.evaluate("window.RV.pinned") is None


def test_click_on_phrase_outside_link_still_pins(nested):
    nested.locator(PHRASE).scroll_into_view_if_needed()
    pt = nested.locator(PHRASE).evaluate(
        "el => { const r = el.getClientRects()[0]; return {x: r.left + 3, y: r.top + r.height / 2}; }"
    )
    assert 0 <= pt["y"] < nested.evaluate("window.innerHeight")
    nested.mouse.click(pt["x"], pt["y"])
    assert boxed(nested) == [7]
    assert nested.evaluate("location.hash") == "#add-expr"
    assert nested.evaluate("window.RV.pinned") == "add-expr"


def test_hover_on_nested_link_boxes_the_anchor(nested):
    nested.hover(LINK)
    assert boxed(nested) == [7]
    nested.mouse.move(0, 0)
    assert boxed(nested) == []


def test_focus_on_nested_link_boxes_the_anchor(nested):
    assert boxed(nested) == [5, 6, 7, 8]
    nested.locator(LINK).focus()
    assert boxed(nested) == [7]
    nested.evaluate("document.activeElement.blur()")
    assert boxed(nested) == []


def test_enter_on_focused_plain_anchor_still_pins(nested):
    nested.locator('.rv-anchor[data-anchor="call-site"]').focus()
    nested.keyboard.press("Enter")
    assert boxed(nested) == [12]
    assert nested.evaluate("location.hash") == "#call-site"
    assert nested.evaluate("window.RV.pinned") == "call-site"


def test_focus_and_blur_on_plain_anchor(nested):
    assert boxed(nested) == [5, 6, 7, 8]
    nested.locator('.rv-anchor[data-anchor="call-site"]').focus()
    assert boxed(nested) == [12]
    nested.evaluate("document.activeElement.blur()")
    assert boxed(nested) == []
