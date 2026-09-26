"""Parse lesson.md: YAML front matter plus a Markdown body."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from revision_engine.errors import BuildError


@dataclass(frozen=True)
class LessonDoc:
    title: str
    summary: str
    file: str
    start: str | None
    media: str | None
    voice: str | None
    body: str


def _opt_str(m: dict, key: str, where: str) -> str | None:
    v = m.get(key)
    if v is None:
        return None
    if not isinstance(v, str):
        raise BuildError(f"{where}: front matter key {key!r} must be a string")
    return v


def load_lesson(path: Path, where: str) -> LessonDoc:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise BuildError(f"{where}: front matter must start with '---' on line 1")
    end = text.find("\n---\n", 4)
    if end == -1:
        if text.endswith("\n---"):
            end = len(text) - 4
        else:
            raise BuildError(f"{where}: front matter is not closed by a '---' line")
    try:
        meta = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError as e:
        raise BuildError(f"{where}: front matter is not valid YAML: {e}") from e
    if not isinstance(meta, dict):
        raise BuildError(f"{where}: front matter must be a mapping")
    for key in ("title", "file"):
        if not isinstance(meta.get(key), str) or not meta[key]:
            raise BuildError(f"{where}: front matter key {key!r} is required")
    body = text[end + 5 :]
    return LessonDoc(
        title=meta["title"],
        summary=_opt_str(meta, "summary", where) or "",
        file=meta["file"].replace("\\", "/"),
        start=_opt_str(meta, "start", where),
        media=_opt_str(meta, "media", where),
        voice=_opt_str(meta, "voice", where),
        body=body,
    )
