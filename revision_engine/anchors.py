"""Named code regions: load from anchors.yaml and resolve to concrete line ranges."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from revision_engine.config import SLUG_RE
from revision_engine.errors import BuildError
from revision_engine.sources import SourceFile


@dataclass(frozen=True)
class AnchorSpec:
    name: str
    file: str
    from_: str | None
    to: str | None
    match: str | None
    lines: tuple[int, int] | None
    variant: bool
    label: str


@dataclass(frozen=True)
class Anchor:
    name: str
    file: str
    start: int
    end: int
    variant: bool
    label: str


def _parse_lines(value: Any, name: str, where: str) -> tuple[int, int]:
    if isinstance(value, str):
        m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", value)
        if not m:
            raise BuildError(f"{where}: anchor {name!r}: lines must look like '88-92'")
        a, b = int(m.group(1)), int(m.group(2))
    elif isinstance(value, list) and len(value) == 2 and all(isinstance(v, int) for v in value):
        a, b = value
    elif isinstance(value, int):
        a = b = value
    else:
        raise BuildError(f"{where}: anchor {name!r}: lines must look like '88-92'")
    if a < 1 or b < a:
        raise BuildError(f"{where}: anchor {name!r}: lines {a}-{b} is not a valid range")
    return (a, b)


def load_anchors(path: Path, default_file: str, where: str) -> dict[str, AnchorSpec]:
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise BuildError(f"{where}: invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise BuildError(f"{where}: top level must be a mapping of anchor name to definition")

    specs: dict[str, AnchorSpec] = {}
    for name, body in data.items():
        if not isinstance(name, str) or not SLUG_RE.match(name):
            raise BuildError(f"{where}: {name!r} is not a slug (lowercase letters, digits, hyphens)")
        if not isinstance(body, dict):
            raise BuildError(f"{where}: anchor {name!r} must be a mapping")
        forms = [k for k in ("from", "match", "lines") if k in body]
        if len(forms) != 1 or ("to" in body and "from" not in body):
            raise BuildError(f"{where}: anchor {name!r} must use exactly one of from/to, match, lines")
        if "from" in body and "to" not in body:
            raise BuildError(f"{where}: anchor {name!r} has 'from' but no 'to'")
        for key in ("from", "to", "match", "file", "label"):
            if key in body and not isinstance(body[key], str):
                raise BuildError(f"{where}: anchor {name!r}: {key} must be a string")
        if "to" in body:
            try:
                re.compile(body["to"])
            except re.error as e:
                raise BuildError(f"{where}: anchor {name!r}: 'to' is not a valid regex: {e}") from e
        variant = body.get("variant", False)
        if not isinstance(variant, bool):
            raise BuildError(f"{where}: anchor {name!r}: variant must be true or false")
        specs[name] = AnchorSpec(
            name=name,
            file=body.get("file", default_file),
            from_=body.get("from"),
            to=body.get("to"),
            match=body.get("match"),
            lines=_parse_lines(body["lines"], name, where) if "lines" in body else None,
            variant=variant,
            label=body.get("label", name),
        )
    return specs


def _single_line(needle: str, source: SourceFile, spec: AnchorSpec, what: str) -> int:
    hits = [i + 1 for i, line in enumerate(source.lines) if needle in line]
    if not hits:
        raise BuildError(f"anchor {spec.name!r} in {source.path}: no line contains {needle!r} ({what})")
    if len(hits) > 1:
        listing = "; ".join(f"line {n}: {source.lines[n - 1].strip()}" for n in hits)
        raise BuildError(
            f"anchor {spec.name!r} in {source.path}: {what} {needle!r} matches {len(hits)} lines, "
            f"need exactly one: {listing}"
        )
    return hits[0]


def resolve(spec: AnchorSpec, source: SourceFile) -> Anchor:
    n = len(source.lines)
    if spec.lines is not None:
        start, end = spec.lines
        if end > n:
            raise BuildError(f"anchor {spec.name!r} in {source.path}: lines {start}-{end} exceed file length {n}")
    elif spec.match is not None:
        start = end = _single_line(spec.match, source, spec, "match")
    else:
        assert spec.from_ is not None and spec.to is not None
        start = _single_line(spec.from_, source, spec, "from")
        pattern = re.compile(spec.to)
        end = next((i + 1 for i in range(start, n) if pattern.search(source.lines[i])), None)
        if end is None:
            raise BuildError(
                f"anchor {spec.name!r} in {source.path}: no line after line {start} matches to={spec.to!r}"
            )
    return Anchor(name=spec.name, file=source.path, start=start, end=end, variant=spec.variant, label=spec.label)


def resolve_all(specs: dict[str, AnchorSpec], sources: dict[str, SourceFile]) -> dict[str, Anchor]:
    out: dict[str, Anchor] = {}
    for name, spec in specs.items():
        if spec.file not in sources:
            raise BuildError(f"anchor {name!r} refers to file {spec.file!r} which is not loaded")
        out[name] = resolve(spec, sources[spec.file])
    return out
