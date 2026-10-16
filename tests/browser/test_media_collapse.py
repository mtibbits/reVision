"""The reader can collapse the media pane by keyboard and restore it, without disturbing playback or cues."""

from __future__ import annotations

import pytest

from .test_pages import MEDIA_READY, boxed


def measure(page) -> dict:
    return page.evaluate(
        """(() => {
          const pane = document.getElementById('rv-media');
          const toggle = document.getElementById('rv-media-toggle');
          const player = document.getElementById('rv-media-el');
          return {
            paneH: pane.getBoundingClientRect().height,
            lessonH: document.getElementById('rv-lesson').getBoundingClientRect().height,
            toggleH: toggle.getBoundingClientRect().height,
            playerH: player.getBoundingClientRect().height,
            gapX: toggle.getBoundingClientRect().left - player.getBoundingClientRect().right,
            playerVisible: player.checkVisibility(),
            transcriptVisible: document.getElementById('rv-transcript').checkVisibility(),
            collapsed: pane.classList.contains('rv-media-collapsed'),
            expanded: toggle.getAttribute('aria-expanded'),
            docH: document.documentElement.scrollHeight,
            cap: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--rv-media-h')),
          };
        })()"""
    )


def media_state(page) -> dict:
    return page.evaluate(
        "(() => { const m = document.getElementById('rv-media-el'); return { paused: m.paused, t: m.currentTime }; })()"
    )


def test_toggle_works_by_keyboard_and_keeps_its_name(hello):
    assert hello.locator("#rv-media-toggle").count() == 1
    hello.set_viewport_size({"width": 1400, "height": 800})
    button = hello.get_by_role("button", name="Narration", exact=True)
    assert button.count() == 1
    assert button.get_attribute("aria-expanded") == "true"

    hello.click("#rv-lesson h1")
    reached = False
    for _ in range(60):
        hello.keyboard.press("Tab")
        if hello.evaluate("document.activeElement.id") == "rv-media-toggle":
            reached = True
            break
    assert reached

    hello.keyboard.press("Enter")
    m = measure(hello)
    assert m["expanded"] == "false", m
    assert m["collapsed"], m
    assert not m["playerVisible"], m
    assert not m["transcriptVisible"], m
    assert hello.get_by_role("button", name="Narration", exact=True, expanded=False).count() == 1
    assert hello.evaluate("document.activeElement.id") == "rv-media-toggle"

    hello.keyboard.press("Space")
    m = measure(hello)
    assert m["expanded"] == "true", m
    assert not m["collapsed"], m
    assert m["playerVisible"], m
    assert m["transcriptVisible"], m
    assert hello.errors == []


@pytest.mark.parametrize("width", [1400, 700])
def test_collapse_gives_lesson_the_freed_height(hello, width):
    hello.set_viewport_size({"width": width, "height": 800})
    hello.wait_for_function(MEDIA_READY)
    assert hello.locator("#rv-media-toggle").count() == 1

    e = measure(hello)
    hello.click("#rv-media-toggle")
    c = measure(hello)
    hello.click("#rv-media-toggle")
    r = measure(hello)

    assert abs(e["paneH"] - e["cap"]) <= 0.5, e  # expanded pane is unchanged
    assert abs(e["gapX"] - 6) <= 0.5, e  # the toggle's own margin spaces it from the player
    assert e["paneH"] - c["paneH"] > 100, (e, c)  # the subject: collapsing frees real height
    assert abs((c["lessonH"] - e["lessonH"]) - (e["paneH"] - c["paneH"])) <= 1, (e, c)
    assert c["paneH"] <= c["toggleH"] + 0.5, c
    assert c["docH"] <= 800, c
    assert abs(r["paneH"] - e["paneH"]) <= 0.5, (e, r)
    assert abs(r["lessonH"] - e["lessonH"]) <= 0.5, (e, r)
    assert hello.errors == []


def test_playback_and_cues_continue_while_collapsed(hello):
    assert hello.locator("#rv-media-toggle").count() == 1
    hello.set_viewport_size({"width": 1400, "height": 800})
    hello.wait_for_function(MEDIA_READY)
    hello.evaluate("window.RV.seek(window.RV.data.cues[1].start - 2.0)")
    assert hello.evaluate("window.RV.activeSegment()") == 0

    played = hello.evaluate(
        """async () => {
          try { await document.getElementById('rv-media-el').play(); return null; }
          catch (err) { return String(err); }
        }"""
    )
    assert played is None

    hello.click("#rv-media-toggle")
    assert measure(hello)["collapsed"]
    assert hello.evaluate("window.RV.activeSegment()") == 0  # the cue change below happens while collapsed
    assert not media_state(hello)["paused"]

    hello.wait_for_function("window.RV.activeSegment() === 1", timeout=5000)
    assert measure(hello)["collapsed"]
    assert boxed(hello) == [7]
    s = media_state(hello)
    assert not s["paused"], s
    assert s["t"] > hello.evaluate("window.RV.data.cues[1].start"), s

    t1 = s["t"]
    hello.click("#rv-media-toggle")
    hello.wait_for_function(f"document.getElementById('rv-media-el').currentTime > {t1}", timeout=5000)
    s = media_state(hello)
    assert not s["paused"], s
    assert s["t"] > t1, (t1, s)
    hello.evaluate("document.getElementById('rv-media-el').pause()")
    assert hello.errors == []


def test_lesson_without_media_has_no_toggle(hello, site_url):
    assert hello.locator("#rv-media-toggle").count() == 1  # control: the media lesson has one

    hello.goto(site_url + "intro/quiet/")
    hello.wait_for_function("window.RV !== undefined")
    assert hello.locator("#rv-media").is_hidden()
    assert hello.locator(".rv-media-toggle").count() == 0
    assert hello.errors == []


def test_toggle_hidden_without_script(browser, site_url):
    context = browser.new_context(java_script_enabled=False)
    try:
        page = context.new_page()
        page.goto(site_url + "intro/hello/")
        assert page.locator("#rv-media-toggle").count() == 1
        assert page.locator("#rv-media-toggle").is_hidden()
        assert page.locator("#rv-media-el").is_visible()
        widths = page.evaluate(
            """(() => {
              const pane = document.getElementById('rv-media');
              const s = getComputedStyle(pane);
              return {
                player: document.getElementById('rv-media-el').getBoundingClientRect().width,
                content: pane.clientWidth - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight),
              };
            })()"""
        )
        assert abs(widths["player"] - widths["content"]) <= 0.5, widths  # the hidden toggle's column takes no width
    finally:
        context.close()
