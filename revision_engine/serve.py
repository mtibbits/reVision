"""Local preview: build to a temp folder, serve it, rebuild when the content changes."""

from __future__ import annotations

import http.server
import os
import re
import sys
import tempfile
import threading
import time
from functools import partial
from pathlib import Path

from revision_engine.build import build
from revision_engine.errors import BuildError

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")


class _Slice:
    """A bounded reader over an open file, for streaming one byte range."""

    def __init__(self, f, remaining: int) -> None:
        self._f = f
        self._remaining = remaining

    def read(self, n: int = -1) -> bytes:
        if self._remaining <= 0:
            return b""
        n = self._remaining if n is None or n < 0 else min(n, self._remaining)
        data = self._f.read(n)
        self._remaining -= len(data)
        return data

    def close(self) -> None:
        self._f.close()


class RangeHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler plus HTTP Range support, which <audio> needs to seek."""

    def end_headers(self) -> None:
        if not any(h.lower().startswith("accept-ranges") for h in self._headers_buffer_text()):
            self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def _headers_buffer_text(self) -> list[str]:
        buf = getattr(self, "_headers_buffer", [])
        return [b.decode("latin-1", "replace") for b in buf]

    def send_head(self):
        path = self.translate_path(self.path)
        range_header = self.headers.get("Range")
        if os.path.isdir(path) or not range_header:
            return super().send_head()
        m = _RANGE_RE.match(range_header.strip())
        if not m or (m.group(1) == "" and m.group(2) == ""):
            return super().send_head()
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None
        stat = os.fstat(f.fileno())
        size = stat.st_size
        if m.group(1):
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else size - 1
        else:
            start = max(0, size - int(m.group(2)))
            end = size - 1
        end = min(end, size - 1)
        if start > end or start >= size:
            f.close()
            self.send_response(416, "Requested Range Not Satisfiable")
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None
        self.send_response(206, "Partial Content")
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
        self.end_headers()
        f.seek(start)
        return _Slice(f, end - start + 1)


class Watcher:
    """Polls file modification times under `root`, skipping ignored folders and VCS/cache noise."""

    def __init__(self, root: Path, ignore: tuple[Path, ...] = ()) -> None:
        self.root = root.resolve()
        self.ignore = tuple(p.resolve() for p in ignore)
        self._last = self.snapshot()

    def _skip(self, p: Path) -> bool:
        parts = set(p.parts)
        if ".git" in parts or "__pycache__" in parts or ".venv" in parts:
            return True
        return any(ig == p or ig in p.parents for ig in self.ignore)

    def snapshot(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for p in self.root.rglob("*"):
            if p.is_file() and not self._skip(p):
                try:
                    out[p.as_posix()] = p.stat().st_mtime_ns
                except OSError:
                    pass
        return out

    def changed(self) -> bool:
        now = self.snapshot()
        if now != self._last:
            self._last = now
            return True
        return False


def _build(root: Path, output: Path, commit: str | None) -> None:
    try:
        result = build(root, output=output, commit=commit)
        print(f"built {len(result.pages)} pages -> {output}", flush=True)
        for w in result.report.warnings:
            print(f"warning: {w}", flush=True)
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr, flush=True)


def serve(root: Path, port: int, commit: str | None, once: bool = False) -> None:
    root = root.resolve()
    with tempfile.TemporaryDirectory(prefix="rv2-serve-") as tmp:
        output = Path(tmp) / "site"
        _build(root, output, commit)
        if once:
            return
        handler = partial(RangeHTTPRequestHandler, directory=str(output))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        print(f"serving http://127.0.0.1:{server.server_address[1]}/  (Ctrl+C to stop)", flush=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        watcher = Watcher(root, ignore=(root / "public",))
        try:
            while True:
                time.sleep(1.0)
                if watcher.changed():
                    _build(root, output, commit)
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
