"""Load and validate revision.yaml and curriculum.yaml into frozen dataclasses."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from revision_engine.errors import BuildError

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
HOSTS = ("github", "gitlab")
DEFAULT_VOICE = "en_US-lessac-medium"


@dataclass(frozen=True)
class SiteConfig:
    title: str
    base_url: str


@dataclass(frozen=True)
class RepoConfig:
    url: str
    host: str


@dataclass(frozen=True)
class ProjectConfig:
    root: Path
    site: SiteConfig
    repo: RepoConfig
    content: Path
    output: Path
    voice: str


@dataclass(frozen=True)
class LessonRef:
    slug: str
    title: str
    path: Path
    type: str = "lesson"


@dataclass(frozen=True)
class Chapter:
    slug: str
    title: str
    lessons: tuple[LessonRef, ...]


@dataclass(frozen=True)
class Curriculum:
    chapters: tuple[Chapter, ...]


def _load_yaml(path: Path) -> Any:
    if not path.is_file():
        raise BuildError(f"{path.name} not found at {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise BuildError(f"{path}: invalid YAML: {e}") from e
    return {} if data is None else data


def _mapping(data: Any, where: str, file: str) -> dict:
    if not isinstance(data, dict):
        raise BuildError(f"{file}: {where} must be a mapping")
    return data


def _require(m: dict, key: str, where: str, file: str) -> Any:
    if key not in m or m[key] is None:
        raise BuildError(f"{file}: {where}.{key} is required")
    return m[key]


def _string(m: dict, key: str, where: str, file: str, default: str | None = None) -> str:
    value = m.get(key, default) if default is not None else _require(m, key, where, file)
    if not isinstance(value, str):
        raise BuildError(f"{file}: {where}.{key} must be a string")
    return value


def _slug(value: Any, where: str, file: str) -> str:
    if not isinstance(value, str) or not SLUG_RE.match(value):
        raise BuildError(f"{file}: {where}: {value!r} is not a slug (lowercase letters, digits, hyphens)")
    return value


def load_project_config(root: Path) -> ProjectConfig:
    root = root.resolve()
    file = "revision.yaml"
    data = _mapping(_load_yaml(root / file), "top level", file)

    site = _mapping(_require(data, "site", "top level", file), "site", file)
    repo = _mapping(_require(data, "repo", "top level", file), "repo", file)
    host = _string(repo, "host", "repo", file)
    if host not in HOSTS:
        raise BuildError(f"{file}: repo.host must be one of: {', '.join(HOSTS)} (got {host!r})")

    narration = _mapping(data.get("narration") or {}, "narration", file)

    return ProjectConfig(
        root=root,
        site=SiteConfig(
            title=_string(site, "title", "site", file),
            base_url=_string(site, "base_url", "site", file, ""),
        ),
        repo=RepoConfig(url=_string(repo, "url", "repo", file), host=host),
        content=root / _string(data, "content", "top level", file, "docs/revision"),
        output=root / _string(data, "output", "top level", file, "public"),
        voice=_string(narration, "voice", "narration", file, DEFAULT_VOICE),
    )


def load_curriculum(cfg: ProjectConfig) -> Curriculum:
    path = cfg.content / "curriculum.yaml"
    file = path.relative_to(cfg.root).as_posix()
    data = _mapping(_load_yaml(path), "top level", file)
    raw_chapters = data.get("chapters")
    if not isinstance(raw_chapters, list):
        raise BuildError(f"{file}: chapters must be a list")

    chapters: list[Chapter] = []
    seen_chapters: set[str] = set()
    for ci, raw in enumerate(raw_chapters):
        where = f"chapters[{ci}]"
        m = _mapping(raw, where, file)
        slug = _slug(m.get("slug"), f"{where}.slug", file)
        if slug in seen_chapters:
            raise BuildError(f"{file}: duplicate chapter slug {slug!r}")
        seen_chapters.add(slug)
        raw_lessons = m.get("lessons")
        if not isinstance(raw_lessons, list):
            raise BuildError(f"{file}: {where}.lessons must be a list")
        lessons: list[LessonRef] = []
        seen_lessons: set[str] = set()
        for li, lraw in enumerate(raw_lessons):
            lwhere = f"{where}.lessons[{li}]"
            lm = _mapping(lraw, lwhere, file)
            lslug = _slug(lm.get("slug"), f"{lwhere}.slug", file)
            if lslug in seen_lessons:
                raise BuildError(f"{file}: duplicate lesson slug {lslug!r} in chapter {slug!r}")
            seen_lessons.add(lslug)
            ltype = _string(lm, "type", lwhere, file, "lesson")
            if ltype != "lesson":
                raise BuildError(f"{file}: {lwhere}.type: only 'lesson' is supported in this version")
            lpath = (cfg.content / _string(lm, "path", lwhere, file)).resolve()
            if not (lpath / "lesson.md").is_file():
                raise BuildError(f"{file}: {lwhere}.path: {lpath / 'lesson.md'} not found")
            lessons.append(LessonRef(slug=lslug, title=_string(lm, "title", lwhere, file), path=lpath, type=ltype))
        chapters.append(Chapter(slug=slug, title=_string(m, "title", where, file), lessons=tuple(lessons)))
    return Curriculum(chapters=tuple(chapters))
