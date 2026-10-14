"""Media that fails to load: the error message must show inside the pane, in either event order."""

from __future__ import annotations

import http.server
import re
import shutil
import threading
from functools import partial
from pathlib import Path

import pytest

from revision_engine.build import build
from revision_engine.narration import SilentSynthesizer, narrate

from .conftest import FIXED, _QuietHandler

SEGMENTS = 14
WAV = re.compile(r".*\.wav(\?.*)?$")
APP = re.compile(r".*/assets/app\.[0-9a-f]+\.js$")


@pytest.fixture(scope="module")
def long_media_url(tmp_path_factory):
    root = tmp_path_factory.mktemp("media")
    src = root / "m"
    shutil.copytree(Path(__file__).resolve().parents[2] / "examples" / "minimal", src)
    lesson = src / "docs/revision/chapters/01-intro/lessons/01-hello"
    (lesson / "narration.yaml").write_text(
        "segments:\n"
        + "".join(f"  - text: Segment number {i} of the narration.\n    show: add-fn\n" for i in range(SEGMENTS)),
        encoding="utf-8",
    )
    narrate(lesson, SilentSynthesizer(rate=8000, seconds_per_char=0.01), voice="silent-fixture")
    out = root / "out"
    build(src, output=out, commit=FIXED)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(_QuietHandler, directory=str(out)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/intro/hello/"
    server.shutdown()


def fail_media(page, url: str, order: str) -> list[str]:
    """Load url with its media failing before ("early") or after ("late") the deferred app.js runs."""
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    held: list = []
    if order == "late":
        page.route(WAV, lambda r: held.append(r))
        page.goto(url, wait_until="domcontentloaded")  # a held media request delays "load"
        page.wait_for_function("window.RV !== undefined")
        held[0].abort()
        page.wait_for_function("document.getElementById('rv-media-el').error !== null")
    else:
        page.route(WAV, lambda r: r.abort())
        page.route(APP, lambda r: held.append(r))
        page.goto(url, wait_until="commit")
        page.wait_for_function(
            "(() => { const m = document.getElementById('rv-media-el'); return !!m && m.error !== null; })()"
        )
        held[0].fulfill(response=held[0].fetch())
        page.wait_for_function("window.RV !== undefined")
    page.wait_for_function("!document.querySelector('.rv-media-error').hidden", timeout=5000)
    return errors


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
          };
        })()"""
    )


@pytest.mark.parametrize("width", [1400, 700])
@pytest.mark.parametrize("order", ["early", "late"])
def test_error_message_visible_with_long_transcript(page, long_media_url, order, width):
    page.set_viewport_size({"width": width, "height": 800})
    errors = fail_media(page, long_media_url, order)
    m = measure(page)
    assert m["segCount"] == SEGMENTS, m  # the subject: a transcript longer than the pane
    assert m["tScroll"] > m["tClient"], m
    assert m["text"] == "Narration unavailable.", m
    assert m["msgH"] > 0, m
    assert m["msgInside"], m
    assert m["playerHidden"], m
    assert m["tH"] > 0, m
    assert errors == []


def test_transcript_scrolls_to_last_segment_in_error_state(page, long_media_url):
    page.set_viewport_size({"width": 1400, "height": 800})
    errors = fail_media(page, long_media_url, "late")
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
def test_failed_pane_fits_content_and_caps(page, long_media_url, site_url, order, case):
    page.set_viewport_size({"width": 1400, "height": 800})
    url = long_media_url if case == "long" else site_url + "intro/hello/"
    errors = fail_media(page, url, order)
    m = measure(page)
    assert m["msgH"] > 0 and m["msgInside"], m
    assert m["paneH"] <= m["cap"] + 0.5, m
    content = m["borderTop"] + m["padTop"] + m["padBottom"] + m["msgH"] + m["rowGap"] + m["tScroll"]
    assert m["paneH"] <= content + 1, m
    if case == "short":
        assert m["paneH"] < m["cap"] - 1, m  # the pane shrank to its content
    else:
        assert m["paneH"] >= m["cap"] - 0.5, m  # the pane is capped, not grown
    assert errors == []


def test_working_media_pane_unchanged(page, site_url):
    page.set_viewport_size({"width": 1400, "height": 800})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(site_url + "intro/hello/")
    page.wait_for_function("window.RV !== undefined")
    page.wait_for_function("document.getElementById('rv-media-el').readyState >= 1")
    m = measure(page)
    assert not m["failedClass"], m
    assert page.evaluate("document.querySelector('.rv-media-error').hidden")
    assert abs(m["paneH"] - m["cap"]) <= 0.5, m
    assert errors == []
