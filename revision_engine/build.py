"""Orchestrate the seven build stages into a static site. Pure: same tree, same bytes."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from revision_engine.anchors import Anchor, load_anchors, resolve_all
from revision_engine.config import (
    Chapter,
    Curriculum,
    LessonRef,
    ProjectConfig,
    load_curriculum,
    load_project_config,
)
from revision_engine.diagrams import render_dot, stamp_anchors
from revision_engine.errors import BuildError, Report
from revision_engine.highlight import highlight_source, token_css
from revision_engine.intrinsics import lookup
from revision_engine.lesson import LessonDoc, load_lesson
from revision_engine.markdown_ext import RenderContext, render_markdown
from revision_engine.narration import check_cues, load_cues, load_narration
from revision_engine.render import (
    NavChapter,
    NavLesson,
    PageModel,
    Variant,
    render_page,
    render_redirect,
    site_index,
    write_assets,
)
from revision_engine.sources import file_url, git_commit, read_source, short

VIDEO_SUFFIXES = (".mp4", ".webm", ".ogv")


@dataclass
class BuildResult:
    output: Path
    pages: list[Path]
    report: Report
    commit: str


@dataclass
class _LessonBuild:
    ref: LessonRef
    chapter: Chapter
    doc: LessonDoc
    where: str
    anchors: dict[str, Anchor]
    code_html: str
    lesson_html: str
    media: str | None
    cues: list[dict[str, Any]] | None


def _rel(cfg: ProjectConfig, p: Path) -> str:
    return p.relative_to(cfg.root).as_posix()


def _check_output(cfg: ProjectConfig, output: Path) -> None:
    """Refuse to wipe the repository itself or any folder above it."""
    output = output.resolve()
    if output == cfg.root or output in cfg.root.parents:
        raise BuildError("output folder must be inside the repository and not the repository itself")


def _build_lesson(cfg: ProjectConfig, chapter: Chapter, ref: LessonRef, report: Report) -> _LessonBuild:
    where = _rel(cfg, ref.path)
    doc = load_lesson(ref.path / "lesson.md", f"{where}/lesson.md")

    specs = load_anchors(ref.path / "anchors.yaml", doc.file, f"{where}/anchors.yaml")
    files = sorted({doc.file} | {s.file for s in specs.values()})
    sources = {f: read_source(cfg.root, f) for f in files}
    anchors = resolve_all(specs, sources)
    # Version one shows one file per lesson. Every consumer of the anchor set (fragments,
    # variants, cues, diagram nodes) would otherwise box foreign line numbers onto this file.
    for name, a in anchors.items():
        if a.file != doc.file:
            raise BuildError(
                f"{where}/anchors.yaml: anchor {name!r} resolves in {a.file!r} but this lesson shows {doc.file!r}"
            )
    if doc.start is not None and doc.start not in anchors:
        raise BuildError(f"{where}/lesson.md: start anchor {doc.start!r} is not defined in anchors.yaml")

    diagrams: dict[str, str] = {}
    diagrams_dir = ref.path / "diagrams"
    if diagrams_dir.is_dir():
        for dot in sorted(diagrams_dir.glob("*.dot")):
            svg = render_dot(dot, f"{where}/diagrams/{dot.name}")
            diagrams[dot.stem] = stamp_anchors(svg, set(anchors))

    ctx = RenderContext(
        anchors={name: a.file for name, a in anchors.items()},
        diagrams=diagrams,
        lookup=lookup,
        report=report,
        where=f"{where}/lesson.md",
        lesson_file=doc.file,
        line_offset=doc.body_line - 1,
    )
    rendered = render_markdown(doc.body, ctx)

    media: str | None = None
    cues: list[dict[str, Any]] | None = None
    narration_path = ref.path / "narration.yaml"
    cues_path = ref.path / "cues.json"
    if narration_path.is_file():
        if not cues_path.is_file():
            raise BuildError(f"{where}: narration.yaml present but cues.json missing; run 'rv2 narrate {where}'")
        narration = load_narration(narration_path, f"{where}/narration.yaml")
        data = load_cues(cues_path, f"{where}/cues.json")
        check_cues(narration, data, where)
        media = data["media"]
        cues = data["segments"]
    elif doc.media:
        media = doc.media
        if cues_path.is_file():
            cues = load_cues(cues_path, f"{where}/cues.json")["segments"]

    if media is not None:
        media_path = (ref.path / media).resolve()
        lesson_root = ref.path.resolve()
        if Path(media).is_absolute() or lesson_root not in media_path.parents:
            raise BuildError(f"{where}: media path {media!r} must be a relative path inside the lesson folder")
        if not media_path.is_file():
            raise BuildError(f"{where}: media file {media!r} not found")
    for i, seg in enumerate(cues or [], start=1):
        for name in seg.get("show", []):
            if name not in anchors:
                raise BuildError(f"{where}/cues.json: segment {i} shows unknown anchor {name!r}")
        if "diagram" in seg and seg["diagram"] not in diagrams:
            raise BuildError(f"{where}/cues.json: segment {i} refers to unknown diagram {seg['diagram']!r}")
        if "node" in seg:
            svg = diagrams.get(seg.get("diagram", ""), "")
            if f'data-node="{seg["node"]}"' not in svg:
                raise BuildError(
                    f"{where}/cues.json: segment {i} refers to node {seg['node']!r} "
                    f"which is not in diagram {seg.get('diagram')!r}"
                )

    return _LessonBuild(
        ref=ref,
        chapter=chapter,
        doc=doc,
        where=where,
        anchors=anchors,
        code_html=highlight_source(sources[doc.file]),
        lesson_html=rendered.html,
        media=media,
        cues=cues,
    )


def _nav(curriculum: Curriculum, current: LessonRef) -> tuple[NavChapter, ...]:
    return tuple(
        NavChapter(
            slug=ch.slug,
            title=ch.title,
            lessons=tuple(
                NavLesson(le.slug, le.title, f"{ch.slug}/{le.slug}/", le is current) for le in ch.lessons
            ),
        )
        for ch in curriculum.chapters
    )


def _media_kind(media: str | None) -> str | None:
    if media is None:
        return None
    return "video" if media.lower().endswith(VIDEO_SUFFIXES) else "audio"


def build(
    root: Path, output: Path | None = None, commit: str | None = None, check_only: bool = False
) -> BuildResult:
    cfg = load_project_config(root)
    curriculum = load_curriculum(cfg)
    output = (output or cfg.output).resolve()
    _check_output(cfg, output)

    commit = commit or git_commit(cfg.root)
    if commit is None:
        raise BuildError("not a git repository; pass --commit <sha> to identify the source revision")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise BuildError(f"commit must be a 40-character hex sha (got {commit!r})")

    report = Report()
    flat = [(ch, le) for ch in curriculum.chapters for le in ch.lessons]
    built = [_build_lesson(cfg, ch, le, report) for ch, le in flat]

    if check_only:
        return BuildResult(output=output, pages=[], report=report, commit=commit)

    if output.exists():
        if any(output.iterdir()) and not (output / "site.json").is_file():
            raise BuildError(
                f"output folder {output} exists and was not written by rv2 (no site.json); "
                "delete it yourself or choose another --output"
            )
        shutil.rmtree(output)
    output.mkdir(parents=True)
    assets = write_assets(output, token_css())

    pages: list[Path] = []
    for i, lb in enumerate(built):
        ch, le = lb.chapter, lb.ref
        prev_href = f"{flat[i - 1][0].slug}/{flat[i - 1][1].slug}/" if i > 0 else None
        next_href = f"{flat[i + 1][0].slug}/{flat[i + 1][1].slug}/" if i + 1 < len(flat) else None
        variants = tuple(Variant(a.name, a.label, a.start) for a in lb.anchors.values() if a.variant)
        rv_data = {
            "anchors": {name: {"start": a.start, "end": a.end} for name, a in sorted(lb.anchors.items())},
            "start": lb.doc.start,
            "cues": lb.cues,
            "variants": [{"name": v.name, "label": v.label, "start": v.start} for v in variants],
        }
        model = PageModel(
            site_title=cfg.site.title,
            root="../../",
            assets=assets,
            chapter_title=ch.title,
            lesson_title=lb.doc.title,
            summary=lb.doc.summary,
            nav=_nav(curriculum, le),
            prev_href=prev_href,
            next_href=next_href,
            file_path=lb.doc.file,
            commit_short=short(commit),
            file_url=file_url(cfg.repo, commit, lb.doc.file),
            code_html=lb.code_html,
            variants=variants,
            lesson_html=lb.lesson_html,
            media_url=lb.media,
            media_kind=_media_kind(lb.media),
            cues=lb.cues,
            rv_data=rv_data,
        )
        page_dir = output / ch.slug / le.slug
        page_dir.mkdir(parents=True)
        page = page_dir / "index.html"
        page.write_text(render_page(model), encoding="utf-8", newline="\n")
        pages.append(page)
        if lb.media:
            dst = page_dir / lb.media
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(le.path / lb.media, dst)

    (output / "site.json").write_text(
        json.dumps(site_index(cfg, curriculum), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    if flat:
        first = f"{flat[0][0].slug}/{flat[0][1].slug}/"
        (output / "index.html").write_text(render_redirect(first, cfg.site.title), encoding="utf-8", newline="\n")
    return BuildResult(output=output, pages=pages, report=report, commit=commit)
