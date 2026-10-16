"""Narrow layout: the media pane leaves the lesson at least as much of the region they share (#13)."""

from __future__ import annotations

import pytest

from . import test_media_error as _media_error
from .test_pages import MEDIA_READY

# A fixture re-exported rather than imported by name, so the test parameter does not shadow an import.
long_media_url = _media_error.long_media_url

TOL = 0.5


def geometry(page) -> dict:
    return page.evaluate(
        """(() => {
          const r = (el) => el.getBoundingClientRect().toJSON();
          const pane = document.getElementById('rv-media');
          return {
            pane: r(pane),
            right: r(document.querySelector('.rv-right')),
            lesson: r(document.getElementById('rv-lesson')),
            player: r(document.getElementById('rv-media-el')),
            transcript: r(document.getElementById('rv-transcript')),
            cue: r(document.querySelector('.rv-seg')),
            error: r(document.querySelector('.rv-media-error')),
            cap: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--rv-media-h')),
            innerHeight: window.innerHeight,
            expanded: document.getElementById('rv-media-toggle').getAttribute('aria-expanded'),
            collapsed: pane.classList.contains('rv-media-collapsed'),
          };
        })()"""
    )


def inside(inner: dict, outer: dict) -> bool:
    return (
        inner["top"] >= outer["top"] - TOL
        and inner["bottom"] <= outer["bottom"] + TOL
        and inner["left"] >= outer["left"] - TOL
        and inner["right"] <= outer["right"] + TOL
    )


def in_viewport(box: dict, g: dict) -> bool:
    return box["top"] >= -TOL and box["bottom"] <= g["innerHeight"] + TOL


@pytest.mark.parametrize("height", [500, 800, 900], ids=["700x500", "700x800", "700x900"])
def test_narrow_media_pane_leaves_lesson_room(hello, height):
    hello.set_viewport_size({"width": 700, "height": height})
    hello.wait_for_function(MEDIA_READY)
    g = geometry(hello)
    assert g["expanded"] == "true" and not g["collapsed"], g  # the pane's default state
    assert g["pane"]["height"] <= g["lesson"]["height"] + TOL, g
    assert inside(g["player"], g["pane"]), g
    assert in_viewport(g["player"], g), g  # belt-and-braces: the pane's bottom is the viewport's
    assert inside(g["cue"], g["pane"]), g
    assert inside(g["cue"], g["transcript"]), g  # not clipped by the transcript's own scroll box
    assert in_viewport(g["cue"], g), g  # belt-and-braces, as above
    # Last, so a too-small cap still fails at the placement asserts above; at 700x900 the cap binds.
    assert abs(g["pane"]["height"] - min(g["cap"], g["right"]["height"] / 2)) <= TOL, g
    assert hello.errors == []


def test_narrow_media_pane_with_panel_open(hello):
    hello.set_viewport_size({"width": 700, "height": 800})
    hello.wait_for_function(MEDIA_READY)
    hello.click('.rv-rail-btn[data-panel="curriculum"]')
    hello.wait_for_function("!document.getElementById('rv-panel').hidden")
    g = geometry(hello)
    assert g["pane"]["height"] <= g["lesson"]["height"] + TOL, g
    assert hello.errors == []


@pytest.mark.parametrize("height", [800, 300], ids=["1400x800", "1400x300"])
def test_wide_layout_unchanged(hello, height):
    hello.set_viewport_size({"width": 1400, "height": height})
    hello.wait_for_function(MEDIA_READY)
    g = geometry(hello)
    assert abs(g["pane"]["height"] - g["cap"]) <= TOL, g
    assert abs(g["lesson"]["height"] - (height - g["cap"])) <= TOL, g
    assert hello.errors == []


def test_failed_media_pane_no_taller_than_lesson_when_narrow(page, long_media_url):
    page.set_viewport_size({"width": 700, "height": 500})
    errors = _media_error.fail_media(page, long_media_url, "late")
    g = geometry(page)
    assert g["pane"]["height"] <= g["lesson"]["height"] + TOL, g
    assert inside(g["error"], g["pane"]), g
    assert errors == []
