from __future__ import annotations

import http.server
import shutil
import threading
from functools import partial
from pathlib import Path

import pytest

from revision_engine.build import build
from revision_engine.serve import RangeHTTPRequestHandler

FIXED = "0123456789abcdef0123456789abcdef01234567"


class _QuietHandler(RangeHTTPRequestHandler):
    """Range-capable (so <audio> can seek, as on Pages hosting) and silent."""

    def log_message(self, format, *args):  # noqa: A002 - signature fixed by the base class
        pass


@pytest.fixture(scope="session")
def site_url(tmp_path_factory):
    root = tmp_path_factory.mktemp("site")
    src = root / "m"
    shutil.copytree(Path(__file__).resolve().parents[2] / "examples" / "minimal", src)
    out = root / "out"
    build(src, output=out, commit=FIXED)
    handler = partial(_QuietHandler, directory=str(out))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()


@pytest.fixture
def hello(page, site_url):
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(site_url + "intro/hello/")
    page.wait_for_function("window.RV !== undefined")
    page.errors = errors  # type: ignore[attr-defined]
    return page
