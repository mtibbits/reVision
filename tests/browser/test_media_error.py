"""Media that fails to load: the error message must show inside the pane, in either event order."""

from __future__ import annotations

import pytest

from .conftest import MEDIA_READY, SEGMENTS, fail_media, serve_gated


@pytest.fixture(scope="module")
def short_media(site_out):
    with serve_gated(site_out) as site:
        yield site


def measure(page) -> dict:
    return page.evaluate(
        """(() => {
          const pane = document.getElementById('rv-media');
          const msg = document.querySelector('.rv-media-error');
          const t = document.getElementById('rv-transcript');
          const ps = getComputedStyle(pane);
          const p = pane.getBoundingClientRect(), m = msg.getBoundingClientRect();
          return {
            paneH: p.height,
            cap: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--rv-media-h')),
            borderTop: parseFloat(ps.borderTopWidth), padTop: parseFloat(ps.paddingTop),
            padBottom: parseFloat(ps.paddingBottom), rowGap: parseFloat(ps.rowGap),
            text: msg.textContent.trim(), msgH: m.height,
            msgInside: m.top >= p.top - 0.5 && m.bottom <= p.bottom + 0.5,
            playerHidden: document.getElementById('rv-media-el').hidden,
            tH: t.getBoundingClientRect().height, tScroll: t.scrollHeight, tClient: t.clientHeight,
            segCount: t.querySelectorAll('.rv-seg').length,
            failedClass: pane.classList.contains('rv-media-failed'),
            toggleH: document.getElementById('rv-media-toggle').getBoundingClientRect().height,
          };
        })()"""
    )


@pytest.mark.parametrize("width", [1400, 700])
@pytest.mark.parametrize("order", ["early", "late"])
def test_error_message_visible_with_long_transcript(page, long_media, order, width):
    page.set_viewport_size({"width": width, "height": 800})
    errors = fail_media(page, long_media, order)
    m = measure(page)
    assert m["segCount"] == SEGMENTS, m  # the subject: a transcript longer than the pane
    assert m["tScroll"] > m["tClient"], m
    assert m["text"] == "Narration unavailable.", m
    assert m["msgH"] > 0, m
    assert m["msgInside"], m
    assert m["playerHidden"], m
    assert m["tH"] > 0, m
    assert errors == []


def test_transcript_scrolls_to_last_segment_in_error_state(page, long_media):
    page.set_viewport_size({"width": 1400, "height": 800})
    errors = fail_media(page, long_media, "late")
    box = page.evaluate(
        """(() => {
          const t = document.getElementById('rv-transcript');
          t.scrollTop = t.scrollHeight;
          const segs = t.querySelectorAll('.rv-seg');
          const r = t.getBoundingClientRect(), s = segs[segs.length - 1].getBoundingClientRect();
          return { tTop: r.top, tBottom: r.bottom, sTop: s.top, sBottom: s.bottom };
        })()"""
    )
    assert box["sTop"] >= box["tTop"] - 1, box
    assert box["sBottom"] <= box["tBottom"] + 1, box
    assert errors == []


@pytest.mark.parametrize("case", ["long", "short"])
@pytest.mark.parametrize("order", ["early", "late"])
def test_failed_pane_fits_content_and_caps(page, long_media, short_media, order, case):
    page.set_viewport_size({"width": 1400, "height": 800})
    site = long_media if case == "long" else short_media
    errors = fail_media(page, site, order)
    m = measure(page)
    assert m["msgH"] > 0 and m["msgInside"], m
    assert m["paneH"] <= m["cap"] + 0.5, m
    content = m["borderTop"] + m["padTop"] + m["padBottom"] + max(m["msgH"], m["toggleH"]) + m["rowGap"] + m["tScroll"]  # row 1 holds the message and the toggle
    assert m["paneH"] <= content + 1, m
    if case == "short":
        assert m["paneH"] < m["cap"] - 1, m  # the pane shrank to its content
    else:
        assert m["paneH"] >= m["cap"] - 0.5, m  # the pane is capped, not grown
    assert errors == []


def test_working_media_pane_unchanged(hello):
    hello.set_viewport_size({"width": 1400, "height": 800})
    hello.wait_for_function(MEDIA_READY)
    m = measure(hello)
    assert not m["failedClass"], m
    assert hello.evaluate("document.querySelector('.rv-media-error').hidden")
    assert abs(m["paneH"] - m["cap"]) <= 0.5, m
    assert hello.errors == []
