"""Narrow layout: the media pane leaves the lesson at least as much of the region they share (#13)."""

from __future__ import annotations

import pytest

from . import test_media_error as _media_error
from .test_pages import MEDIA_READY

# Re-exported rather than imported by name, so the test parameter does not shadow an import.
long_media_url = _media_error.long_media_url
fail_media = _media_error.fail_media

CAP = 200  # --rv-media-h


def geometry(page) -> dict:
    return page.evaluate(
        """(() => {
          const r = (el) => { const b = el.getBoundingClientRect();
            return { top: b.top, bottom: b.bottom, left: b.left, right: b.right, height: b.height }; };
          const pane = document.getElementById('rv-media');
          return {
            pane: r(pane),
            lesson: r(document.getElementById('rv-lesson')),
            player: r(document.getElementById('rv-media-el')),
            transcript: r(document.getElementById('rv-transcript')),
            cue: r(document.querySelector('.rv-seg')),
            error: r(document.querySelector('.rv-media-error')),
            innerHeight: window.innerHeight,
            expanded: document.getElementById('rv-media-toggle').getAttribute('aria-expanded'),
            collapsed: pane.classList.contains('rv-media-collapsed'),
          };
        })()"""
    )


def inside(inner: dict, outer: dict) -> bool:
    return (
        inner["top"] >= outer["top"] - 0.5
        and inner["bottom"] <= outer["bottom"] + 0.5
        and inner["left"] >= outer["left"] - 0.5
        and inner["right"] <= outer["right"] + 0.5
    )


def in_viewport(box: dict, g: dict) -> bool:
    return box["top"] >= -0.5 and box["bottom"] <= g["innerHeight"] + 0.5


@pytest.mark.parametrize("size", [(700, 500), (700, 800), (700, 900)], ids=["700x500", "700x800", "700x900"])
def test_narrow_media_pane_leaves_lesson_room(hello, size):
    hello.set_viewport_size({"width": size[0], "height": size[1]})
    hello.wait_for_function(MEDIA_READY)
    g = geometry(hello)
    assert g["expanded"] == "true" and not g["collapsed"], g  # the pane's default state
    assert g["pane"]["height"] <= g["lesson"]["height"] + 0.5, g
    if size == (700, 900):
        assert abs(g["pane"]["height"] - CAP) <= 0.5, g  # half the region is 211.5: the cap binds
    assert inside(g["player"], g["pane"]), g
    assert in_viewport(g["player"], g), g  # belt-and-braces: the pane's bottom is the viewport's
    assert inside(g["cue"], g["pane"]), g
    assert inside(g["cue"], g["transcript"]), g  # not clipped by the transcript's own scroll box
    assert in_viewport(g["cue"], g), g  # belt-and-braces, as above
    assert hello.errors == []


def test_narrow_media_pane_with_panel_open(hello):
    hello.set_viewport_size({"width": 700, "height": 800})
    hello.wait_for_function(MEDIA_READY)
    hello.click('.rv-rail-btn[data-panel="curriculum"]')
    hello.wait_for_function("!document.getElementById('rv-panel').hidden")
    g = geometry(hello)
    assert g["pane"]["height"] <= g["lesson"]["height"] + 0.5, g
    assert hello.errors == []


def test_wide_layout_unchanged(hello):
    hello.set_viewport_size({"width": 1400, "height": 800})
    hello.wait_for_function(MEDIA_READY)
    g = geometry(hello)
    assert abs(g["lesson"]["height"] - 600) <= 0.5, g
    assert abs(g["pane"]["height"] - CAP) <= 0.5, g


def test_wide_short_window_unchanged(hello):
    hello.set_viewport_size({"width": 1400, "height": 300})
    hello.wait_for_function(MEDIA_READY)
    g = geometry(hello)
    assert abs(g["pane"]["height"] - CAP) <= 0.5, g
    assert abs(g["lesson"]["height"] - 100) <= 0.5, g


def test_failed_media_pane_no_taller_than_lesson_when_narrow(page, long_media_url):
    page.set_viewport_size({"width": 700, "height": 500})
    errors = fail_media(page, long_media_url, "late")
    g = geometry(page)
    assert g["pane"]["height"] <= g["lesson"]["height"] + 0.5, g
    assert inside(g["error"], g["pane"]), g
    assert errors == []
