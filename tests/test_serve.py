import http.server
import shutil
import threading
import time
import urllib.error
import urllib.request
from functools import partial

import pytest

from revision_engine.serve import RangeHTTPRequestHandler, Watcher, serve

FIXED = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture
def range_server(tmp_path):
    (tmp_path / "a.bin").write_bytes(bytes(range(256)))
    handler = partial(RangeHTTPRequestHandler, directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/a.bin"
    server.shutdown()


def _get(url, range_header=None):
    req = urllib.request.Request(url, headers={"Range": range_header} if range_header else {})
    with urllib.request.urlopen(req) as resp:
        return resp.status, dict(resp.headers), resp.read()


def test_range_request_returns_partial_content(range_server):
    status, headers, body = _get(range_server, "bytes=10-19")
    assert status == 206
    assert headers["Content-Range"] == "bytes 10-19/256" and headers["Content-Length"] == "10"
    assert body == bytes(range(10, 20))


def test_open_ended_and_suffix_ranges(range_server):
    status, headers, body = _get(range_server, "bytes=250-")
    assert status == 206 and body == bytes(range(250, 256)) and headers["Content-Range"] == "bytes 250-255/256"
    status, headers, body = _get(range_server, "bytes=-4")
    assert status == 206 and body == bytes(range(252, 256))


def test_full_get_still_works_and_advertises_ranges(range_server):
    status, headers, body = _get(range_server)
    assert status == 200 and len(body) == 256 and headers["Accept-Ranges"] == "bytes"


def test_unsatisfiable_range_is_416(range_server):
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(range_server, "bytes=300-400")
    assert e.value.code == 416


def test_watcher_detects_content_change_and_ignores_output(minimal_example, tmp_path):
    src = tmp_path / "m"
    shutil.copytree(minimal_example, src)
    w = Watcher(src, ignore=(src / "public",))
    assert not w.changed()
    (src / "public").mkdir(exist_ok=True)
    (src / "public" / "x").write_text("x")
    assert not w.changed()
    time.sleep(0.02)
    cur = src / "docs/revision/curriculum.yaml"
    cur.write_text(cur.read_text() + "\n")
    assert w.changed()
    assert not w.changed()


def test_serve_once_builds(minimal_example, tmp_path, monkeypatch):
    src = tmp_path / "m"
    shutil.copytree(minimal_example, src)
    built = {}

    class FakeResult:
        pages = []

        class report:
            warnings = []

    def fake_build(root, output, commit):
        built["out"] = output
        return FakeResult()

    monkeypatch.setattr("revision_engine.serve.build", fake_build)
    serve(src, port=0, commit=FIXED, once=True)
    assert "out" in built
