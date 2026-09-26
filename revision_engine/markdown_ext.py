"""Markdown rendering with the reVision extensions.

Extensions, all plain CommonMark syntax so other renderers degrade gracefully:
  [phrase](@anchor)        anchor phrase -> <span class="rv-anchor" data-anchor=...>
  [name](!intrinsic)       vendor link   -> <a class="rv-intrinsic" href=...>
  `name` (inline code)     auto-linked when the name is in a vendor table
  ![alt](diagrams/x.dot)   inline pre-rendered SVG in a <figure class="rv-diagram">
  ```quiz ... ```          page-local knowledge check widget
"""

from __future__ import annotations

import html
import posixpath
from dataclasses import dataclass, field
from typing import Callable

import yaml
from markdown_it import MarkdownIt
from markdown_it.token import Token

from revision_engine.errors import BuildError, Report


@dataclass
class RenderContext:
    anchors: dict[str, str]
    diagrams: dict[str, str]
    lookup: Callable[[str], str | None]
    report: Report
    where: str
    lesson_file: str


@dataclass
class RenderedLesson:
    html: str
    used_anchors: list[str] = field(default_factory=list)
    used_diagrams: list[str] = field(default_factory=list)
    quiz_count: int = 0


def _line(token: Token, parent_line: int) -> int:
    return token.map[0] + 1 if token.map else parent_line


def _link_text(children: list[Token], start: int) -> str:
    parts: list[str] = []
    for tok in children[start + 1 :]:
        if tok.type == "link_close":
            break
        if tok.type in ("text", "code_inline"):
            parts.append(tok.content)
    return "".join(parts)


def _close(children: list[Token], open_index: int) -> Token:
    for tok in children[open_index + 1 :]:
        if tok.type == "link_close":
            return tok
    raise AssertionError("link_open without link_close")


def _rewrite_links(children: list[Token], line: int, ctx: RenderContext, out: RenderedLesson) -> None:
    for i, tok in enumerate(children):
        if tok.type != "link_open":
            continue
        href = tok.attrGet("href") or ""
        if href.startswith("@"):
            name = href[1:]
            if name not in ctx.anchors:
                raise BuildError(f"{ctx.where}:{line}: unknown anchor {name!r}")
            if ctx.anchors[name] != ctx.lesson_file:
                raise BuildError(
                    f"{ctx.where}:{line}: anchor {name!r} resolves in {ctx.anchors[name]!r} "
                    f"but this lesson shows {ctx.lesson_file!r}"
                )
            tok.tag = "span"
            tok.attrs = {"class": "rv-anchor", "data-anchor": name, "tabindex": "0"}
            if name not in out.used_anchors:
                out.used_anchors.append(name)
            _close(children, i).tag = "span"
        elif href == "!intrinsic":
            name = _link_text(children, i)
            url = ctx.lookup(name)
            if url is None:
                ctx.report.warn(f"{ctx.where}:{line}: intrinsic {name!r} is not in any vendor table")
                tok.tag = "code"
                tok.attrs = {}
                _close(children, i).tag = "code"
            else:
                tok.attrs = {"class": "rv-intrinsic", "href": url, "target": "_blank", "rel": "noopener"}


def _quiz_html(source: str, line: int, ctx: RenderContext) -> str:
    try:
        data = yaml.safe_load(source) or {}
    except yaml.YAMLError as e:
        raise BuildError(f"{ctx.where}:{line}: quiz block is not valid YAML: {e}") from e
    questions = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(questions, list) or not questions:
        raise BuildError(f"{ctx.where}:{line}: quiz block needs a non-empty 'questions' list")
    parts = ['<section class="rv-quiz">', "<h2>Knowledge check</h2>", "<form>"]
    for qi, q in enumerate(questions):
        n = qi + 1
        if not isinstance(q, dict) or not isinstance(q.get("q"), str):
            raise BuildError(f"{ctx.where}:{line}: quiz question {n} needs a 'q' string")
        choices = q.get("choices")
        if not isinstance(choices, list) or len(choices) < 2:
            raise BuildError(f"{ctx.where}:{line}: quiz question {n} needs at least two choices")
        answer = q.get("answer")
        if not isinstance(answer, int) or isinstance(answer, bool) or not 0 <= answer < len(choices):
            raise BuildError(f"{ctx.where}:{line}: quiz question {n} answer must be an index into choices")
        parts.append(f'<fieldset class="rv-q" data-answer="{answer}"><legend>{n}. {html.escape(q["q"])}</legend>')
        for ci, choice in enumerate(choices):
            parts.append(f'<label><input type="radio" name="q{qi}" value="{ci}"> {html.escape(str(choice))}</label>')
        parts.append('<p class="rv-q-feedback" hidden></p></fieldset>')
    parts += [
        '<button type="submit">Check answers</button>',
        '<p class="rv-quiz-score" hidden></p>',
        "</form>",
        "</section>",
    ]
    return "\n".join(parts) + "\n"


def render_markdown(body: str, ctx: RenderContext) -> RenderedLesson:
    out = RenderedLesson(html="")
    md = MarkdownIt("commonmark").enable("table")

    def core_rewrite(state) -> None:
        for block in state.tokens:
            if block.type == "inline" and block.children:
                _rewrite_links(block.children, _line(block, 1), ctx, out)
                for child in block.children:
                    if child.type == "image":
                        child.map = block.map

    md.core.ruler.push("rv_links", core_rewrite)

    # add_render_rule binds each function as a method of the renderer, hence `self` first.
    default_code_inline = md.renderer.rules.get("code_inline")
    default_fence = md.renderer.rules.get("fence")
    default_image = md.renderer.rules.get("image")

    def code_inline(self, tokens, idx, options, env):
        content = tokens[idx].content
        url = ctx.lookup(content)
        if url is None:
            if default_code_inline:
                return default_code_inline(tokens, idx, options, env)
            return f"<code>{html.escape(content)}</code>"
        return (
            f'<a class="rv-intrinsic" href="{html.escape(url)}" target="_blank" rel="noopener">'
            f"<code>{html.escape(content)}</code></a>"
        )

    def fence(self, tokens, idx, options, env):
        tok = tokens[idx]
        if tok.info.strip() == "quiz":
            out.quiz_count += 1
            return _quiz_html(tok.content, _line(tok, 1), ctx)
        return default_fence(tokens, idx, options, env)

    def image(self, tokens, idx, options, env):
        tok = tokens[idx]
        src = tok.attrGet("src") or ""
        if src.endswith(".dot"):
            stem = posixpath.splitext(posixpath.basename(src))[0]
            line = _line(tok, 1)
            if stem not in ctx.diagrams:
                raise BuildError(f"{ctx.where}:{line}: diagram {stem!r} ({src}) not found")
            if stem not in out.used_diagrams:
                out.used_diagrams.append(stem)
            alt = html.escape(tok.content)
            return (
                f'<figure class="rv-diagram" id="diagram-{stem}" data-diagram="{stem}">'
                f"{ctx.diagrams[stem]}<figcaption>{alt}</figcaption></figure>"
            )
        return default_image(tokens, idx, options, env)

    md.add_render_rule("code_inline", code_inline)
    md.add_render_rule("fence", fence)
    md.add_render_rule("image", image)

    tokens = md.parse(body)
    out.html = md.renderer.render(tokens, md.options, {})
    return out
