"""Media that fails to load: the error message must show inside the pane, in either event order."""

from __future__ import annotations

import http.server
import re
import shutil
import threading
from functools import partial
from pathlib import Path
from typing import NamedTuple

import pytest

from revision_engine.build import build
from revision_engine.narration import SilentSynthesizer, narrate

from .conftest import FIXED, _QuietHandler

SEGMENTS = 14
WAV = re.compile(r".*\.wav(\?.*)?$")
APP = re.compile(r".*/assets/app\.[0-9a-f]+\.js$")


class MediaGate:
    """What the test server does with media and app.js: fail the media, and hold either until released."""

    def __init__(self) -> None:
        self.fail = False
        self.media = threading.Event()
        self.app = threading.Event()
        self.release()

    def release(self) -> None:
        self.media.set()
        self.app.set()

    def reset(self) -> None:
        self.fail = False
        self.release()


class _GatedHandler(_QuietHandler):
    def __init__(self, *args, gate: MediaGate, **kwargs):
        self.gate = gate  # before super().__init__, which serves the request
        super().__init__(*args, **kwargs)

    def send_head(self):
        if WAV.match(self.path) and self.gate.fail:
            self.gate.media.wait(30)
            self.send_error(404)  # admitted as failing, so it fails whatever the gate says now
            return None
        if APP.match(self.path):
            self.gate.app.wait(30)
        return super().send_head()


class GatedSite(NamedTuple):
    url: str
    gate: MediaGate


def _serve_gated(out: Path):
    gate = MediaGate()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(_GatedHandler, gate=gate, directory=str(out)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield GatedSite(f"http://127.0.0.1:{server.server_address[1]}/intro/hello/", gate)
    gate.reset()
    server.shutdown()


@pytest.fixture(scope="module")
def long_media(tmp_path_factory):
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
    yield from _serve_gated(out)


@pytest.fixture(scope="module")
def short_media(tmp_path_factory):
    root = tmp_path_factory.mktemp("short-media")
    src = root / "m"
    shutil.copytree(Path(__file__).resolve().parents[2] / "examples" / "minimal", src)
    out = root / "out"
    build(src, output=out, commit=FIXED)
    yield from _serve_gated(out)


def fail_media(page, site: GatedSite, order: str) -> list[str]:
    """Load site with its media failing before ("early") or after ("late") the deferred app.js runs.

    The server fails the media, not page.route: WebKit's media requests never reach Playwright, so a route
    neither sees nor fails them. The media stays failing after this returns."""
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    gate = site.gate
    try:
        gate.fail = True
        if order == "late":
            gate.media.clear()
            gate.app.set()
            page.goto(site.url, wait_until="domcontentloaded")  # a held media request delays "load"
            page.wait_for_function("window.RV !== undefined")
            assert page.evaluate("document.getElementById('rv-media-el').error === null")
            gate.media.set()
        else:
            gate.media.set()
            gate.app.clear()
            page.goto(site.url, wait_until="commit")
            page.wait_for_function(
                "(() => { const m = document.getElementById('rv-media-el'); return !!m && m.error !== null; })()"
            )
            assert page.evaluate("window.RV === undefined")
            gate.app.set()
            page.wait_for_function("window.RV !== undefined")
        page.wait_for_function("!document.querySelector('.rv-media-error').hidden", timeout=5000)
    finally:
        gate.release()
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
    hello.wait_for_function("document.getElementById('rv-media-el').readyState >= 1")
    m = measure(hello)
    assert not m["failedClass"], m
    assert hello.evaluate("document.querySelector('.rv-media-error').hidden")
    assert abs(m["paneH"] - m["cap"]) <= 0.5, m
    assert hello.errors == []
