from __future__ import annotations

import contextlib
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
from revision_engine.serve import RangeHTTPRequestHandler

from ..conftest import EXAMPLES
from .marks import pytest_collection_modifyitems, pytest_configure  # noqa: F401 - the xfail_browser hooks

FIXED = "0123456789abcdef0123456789abcdef01234567"
HELLO_SRC = "docs/revision/chapters/01-intro/lessons/01-hello"
MEDIA_READY = "document.getElementById('rv-media-el').readyState >= 1"
SEGMENTS = 14
WAV = re.compile(r".*\.wav(\?.*)?$")
APP = re.compile(r".*/assets/app\.[0-9a-f]+\.js$")


class _QuietHandler(RangeHTTPRequestHandler):
    """Range-capable (so <audio> can seek, as on Pages hosting) and silent."""

    def log_message(self, format, *args):  # noqa: A002 - signature fixed by the base class
        pass


def build_example(tmp_path_factory, name: str, edit=None) -> Path:
    """Build a fresh copy of the minimal example, after edit(src) changes it if given."""
    root = tmp_path_factory.mktemp(name)
    src = root / "m"
    shutil.copytree(EXAMPLES / "minimal", src)
    if edit is not None:
        edit(src)
    out = root / "out"
    build(src, output=out, commit=FIXED)
    return out


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


@contextlib.contextmanager
def serve(out: Path, handler=_QuietHandler, **handler_kwargs):
    """Serve out on a free local port for the duration of the block."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(handler, directory=str(out), **handler_kwargs))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()


def open_lesson(page, url: str, init_script: str | None = None, wait: bool = True):
    """Open url collecting uncaught page errors into page.errors, waiting for the app to start unless told not to.

    The init script is added before the first goto, so it runs on that load too."""
    if init_script is not None:
        page.add_init_script(init_script)
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url)
    if wait:
        page.wait_for_function("window.RV !== undefined")
    page.errors = errors  # type: ignore[attr-defined]
    return page


def boxed(page):
    return page.evaluate("Array.from(document.querySelectorAll('.rv-line.rv-boxed')).map(l => +l.dataset.line)")


class MediaGate:
    """Holds the test server's media (which it always fails) or app.js until released."""

    def __init__(self) -> None:
        self.media = threading.Event()
        self.app = threading.Event()
        self.release()

    def release(self) -> None:
        self.media.set()
        self.app.set()


class _GatedHandler(_QuietHandler):
    def __init__(self, *args, gate: MediaGate, **kwargs):
        self.gate = gate  # before super().__init__, which serves the request
        super().__init__(*args, **kwargs)

    def send_head(self):
        if WAV.match(self.path):
            self.gate.media.wait(30)
            self.send_error(404)
            return None
        if APP.match(self.path):
            self.gate.app.wait(30)
        return super().send_head()


class GatedSite(NamedTuple):
    url: str
    gate: MediaGate


@contextlib.contextmanager
def serve_gated(out: Path):
    gate = MediaGate()
    with serve(out, _GatedHandler, gate=gate) as base:
        try:
            yield GatedSite(base + "intro/hello/", gate)
        finally:
            gate.release()


def fail_media(page, site: GatedSite, order: str) -> list[str]:
    """Load site with its media failing before ("early") or after ("late") the deferred app.js runs.

    The server fails the media, not page.route: WebKit's media requests never reach Playwright, so a route
    neither sees nor fails them."""
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    gate = site.gate
    try:
        if order == "late":
            gate.media.clear()
            page.goto(site.url, wait_until="domcontentloaded")  # a held media request delays "load"
            page.wait_for_function("window.RV !== undefined")
            assert page.evaluate("document.getElementById('rv-media-el').error === null")
            gate.media.set()
        else:
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


@pytest.fixture(scope="session")
def site_out(tmp_path_factory):
    """The minimal example, built once per session; serve it, never change it."""
    return build_example(tmp_path_factory, "site")


@pytest.fixture(scope="session")
def site_url(site_out):
    with serve(site_out) as url:
        yield url


@pytest.fixture
def hello(page, site_url):
    return open_lesson(page, site_url + "intro/hello/")


@pytest.fixture(scope="module")
def long_media(tmp_path_factory):
    def edit(src):
        lesson = src / HELLO_SRC
        (lesson / "narration.yaml").write_text(
            "segments:\n"
            + "".join(f"  - text: Segment number {i} of the narration.\n    show: add-fn\n" for i in range(SEGMENTS)),
            encoding="utf-8",
        )
        narrate(lesson, SilentSynthesizer(rate=8000, seconds_per_char=0.01), voice="silent-fixture")

    with serve_gated(build_example(tmp_path_factory, "media", edit=edit)) as site:
        yield site
