"""Narrow layout: the media pane leaves the lesson at least as much of the region they share (#13)."""

from __future__ import annotations

import math

import pytest

from .conftest import MEDIA_READY, fail_media

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


def test_audio_cap_leaves_first_cue_room(hello):
    """Pins the audio cap Firefox needs (#45): Firefox sizes the player's grid row from its declared max-height,
    not its controls, so this reads that declared value and pins Firefox's budget from Chromium; since #64 CI also
    runs it in Firefox directly. A red at the budget assert is a Firefox overflow; a red at the >= 54 assert is
    Chromium's controls squeezed. It does not see a height/min-height on audio, a narrow @media rule that changes
    the pane, or a Firefox intrinsic-size change (the test above does)."""
    hello.set_viewport_size({"width": 700, "height": 500})
    hello.wait_for_function(MEDIA_READY)
    v = hello.evaluate(
        """(() => {
          const pane = document.getElementById('rv-media');
          const player = document.getElementById('rv-media-el');
          const ps = getComputedStyle(pane);
          return {
            contentH: pane.getBoundingClientRect().height
              - parseFloat(ps.borderTopWidth) - parseFloat(ps.borderBottomWidth)
              - parseFloat(ps.paddingTop) - parseFloat(ps.paddingBottom),
            maxH: parseFloat(getComputedStyle(player).maxHeight),
            rowGap: parseFloat(ps.rowGap),
            cueH: document.querySelector('.rv-seg').getBoundingClientRect().height,
            tag: player.tagName,
          };
        })()"""
    )
    assert v["tag"] == "AUDIO", v  # intro/hello/ must stay an audio lesson, or this guards nothing
    assert math.isfinite(v["maxH"]), v  # an uncapped player fails here, not through a NaN comparison
    assert v["maxH"] >= 54, v  # Chromium's audio control height; a lower cap squeezes its controls
    assert v["maxH"] + v["rowGap"] + v["cueH"] <= v["contentH"] + TOL, v  # Firefox's row budget at 700x500
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
    assert g["cap"] == 200, g  # AC3 (#13): at 1400x800 the pane stays 200px and the lesson 600px
    assert abs(g["pane"]["height"] - g["cap"]) <= TOL, g
    assert abs(g["lesson"]["height"] - (height - g["cap"])) <= TOL, g
    assert hello.errors == []


def test_cap_waits_for_container_query_support(hello):
    # An engine without cq units would still accept min(var(--rv-media-h), 50cqh), since it holds a var(),
    # then find it invalid at computed-value time and drop the pane to height: auto, below the base layout.
    conditions = hello.evaluate(
        """(() => {
          const found = [];
          const walk = (rules, guard) => {
            for (const rule of rules) {
              if (rule.style && rule.style.cssText.includes('cqh')) found.push(guard);
              if (rule.cssRules) walk(rule.cssRules, rule instanceof CSSSupportsRule ? rule.conditionText : guard);
            }
          };
          for (const sheet of document.styleSheets) walk(sheet.cssRules, null);
          return found;
        })()"""
    )
    assert len(conditions) == 2, conditions  # the pane's height and the failed pane's max-height
    assert all(c is not None and "cqh" in c for c in conditions), conditions


def test_failed_media_pane_no_taller_than_lesson_when_narrow(page, long_media):
    page.set_viewport_size({"width": 700, "height": 500})
    fail_media(page, long_media, "late")
    g = geometry(page)
    assert g["pane"]["height"] <= g["lesson"]["height"] + TOL, g
    assert inside(g["error"], g["pane"]), g
    assert page.errors == []
