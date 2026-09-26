"""Turn per-lesson build products into HTML pages, hashed assets, and site.json."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

from revision_engine.config import Curriculum, ProjectConfig

Assets = dict[str, str]

_env = Environment(
    loader=PackageLoader("revision_engine", "templates"),
    autoescape=select_autoescape(["html", "j2"]),
    keep_trailing_newline=True,
)


@dataclass(frozen=True)
class NavLesson:
    slug: str
    title: str
    href: str
    current: bool


@dataclass(frozen=True)
class NavChapter:
    slug: str
    title: str
    lessons: tuple[NavLesson, ...]


@dataclass(frozen=True)
class Variant:
    name: str
    label: str
    start: int


@dataclass(frozen=True)
class PageModel:
    site_title: str
    root: str
    assets: Assets
    chapter_title: str
    lesson_title: str
    summary: str
    nav: tuple[NavChapter, ...]
    prev_href: str | None
    next_href: str | None
    file_path: str
    commit_short: str
    file_url: str
    code_html: str
    variants: tuple[Variant, ...]
    lesson_html: str
    media_url: str | None
    media_kind: str | None
    cues: list[dict[str, Any]] | None
    rv_data: dict[str, Any]


def _hashed_name(name: str, content: bytes) -> str:
    stem, ext = name.rsplit(".", 1)
    return f"{stem}.{hashlib.sha256(content).hexdigest()[:8]}.{ext}"


def write_assets(out: Path, token_css: str) -> Assets:
    assets_dir = out / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    static = resources.files("revision_engine").joinpath("static")
    files = {
        "styles.css": static.joinpath("styles.css").read_bytes(),
        "app.js": static.joinpath("app.js").read_bytes(),
        "tokens.css": token_css.encode("utf-8"),
    }
    result: Assets = {}
    for name, content in files.items():
        hashed = _hashed_name(name, content)
        (assets_dir / hashed).write_bytes(content)
        result[name] = f"assets/{hashed}"
    return result


def json_for_script(data: Any) -> str:
    """JSON safe to embed inside <script type="application/json">."""
    return json.dumps(data, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")


def render_page(model: PageModel) -> str:
    template = _env.get_template("lesson.html.j2")
    return template.render(m=model, rv_data_json=json_for_script(model.rv_data))


def render_redirect(target_href: str, title: str) -> str:
    return _env.get_template("redirect.html.j2").render(target=target_href, title=title)


def site_index(cfg: ProjectConfig, curriculum: Curriculum) -> dict:
    return {
        "title": cfg.site.title,
        "chapters": [
            {
                "slug": ch.slug,
                "title": ch.title,
                "lessons": [
                    {"slug": le.slug, "title": le.title, "href": f"{ch.slug}/{le.slug}/"} for le in ch.lessons
                ],
            }
            for ch in curriculum.chapters
        ],
    }
