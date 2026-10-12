"""Read CI's constraints file and compare it with what is installed.

ci-constraints-requirements.txt pins, for CI only, the runtime dependencies whose output the
golden test hashes; pyproject.toml keeps floors. Pins are written in pip's canonical form
(lowercase PEP 503 name, `==`), and versions are compared as `packaging` versions, so
`3.1` equals an installed `3.1.0`.

Stdlib plus `packaging`, which pytest depends on, so every test environment has it.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Callable
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parent.parent
CONSTRAINTS = ROOT / "ci-constraints-requirements.txt"
INSTALL_CMD = 'python -m pip install -e ".[dev]" -c ci-constraints-requirements.txt'

_PIN_RE = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s#]+)")


def _pin_error(path: Path, lineno: int, line: str, msg: str) -> ValueError:
    return ValueError(f"{path.name}:{lineno}: {msg}: {line!r}")


def read_pins(path: Path = CONSTRAINTS) -> dict[str, str]:
    """Map each pinned name to its version, in file order; reject anything but `name==version`."""
    pins: dict[str, str] = {}
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _PIN_RE.fullmatch(line)
        if m is None:
            raise _pin_error(path, lineno, line, "expected name==version")
        name, version = m.groups()
        if name != canonicalize_name(name):
            raise _pin_error(path, lineno, line, f"write the name as {canonicalize_name(name)}")
        if name in pins:
            raise _pin_error(path, lineno, line, "duplicate pin")
        try:
            Version(version)
        except InvalidVersion:
            raise _pin_error(path, lineno, line, "invalid version") from None
        pins[name] = version
    return pins


def pin_mismatches(
    pins: dict[str, str] | None = None,
    version: Callable[[str], str] = metadata.version,
) -> list[str]:
    """One line per pin whose installed version differs or is missing, in pin order."""
    pins = read_pins() if pins is None else pins
    mismatches = []
    for name, pinned in pins.items():
        try:
            installed = version(name)
        except metadata.PackageNotFoundError:
            mismatches.append(f"{name} not installed, CI pins {pinned}")
            continue
        if Version(installed) != Version(pinned):
            mismatches.append(f"{name} {installed} installed, CI pins {pinned}")
    return mismatches


def runtime_dependencies() -> set[str]:
    """Normalized names of pyproject.toml's runtime dependencies."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return {canonicalize_name(Requirement(d).name) for d in project["dependencies"]}


def runtime_closure() -> set[str]:
    """Normalized names of the installed runtime dependencies and theirs, without extras."""
    queue = list(runtime_dependencies())
    seen: set[str] = set()
    while queue:
        name = canonicalize_name(queue.pop())
        if name in seen:
            continue
        seen.add(name)
        for spec in metadata.requires(name) or []:
            req = Requirement(spec)
            if req.marker is None or req.marker.evaluate({"extra": ""}):
                queue.append(req.name)
    return seen
