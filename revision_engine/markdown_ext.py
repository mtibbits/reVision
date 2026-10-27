"""Markdown rendering with the reVision extensions.

Extensions, all plain CommonMark syntax so other renderers degrade gracefully:
  [phrase](@anchor)        anchor phrase -> <span class="rv-anchor" data-anchor=...>
  [name](!intrinsic)       vendor link   -> <a class="rv-intrinsic" href=...>
  `name` (inline code)     auto-linked when the name is in a vendor table, except inside another
                           link's text (Markdown or raw <a>), where it renders as plain <code>; an
                           anchor phrase is a <span>, so a span in one still links. Spans whose
                           name is in no table are recorded on RenderedLesson.unlinked_code
  ![alt](diagrams/x.dot)   inline pre-rendered SVG in a <figure class="rv-diagram">
  ```quiz ... ```          page-local knowledge check widget; code spans in its text render as
                           plain <code>, never vendor-linked; choices are shuffled in the browser
                           unless a question sets `shuffle: false` (data-fixed-order) or has
                           two choices; any key outside _QUESTION_KEYS (or _QUIZ_KEYS, at quiz
                           level) fails the build; a choice YAML loads as a boolean (unquoted
                           `yes`, `on`, ...) renders as True/False with a warning
"""

from __future__ import annotations

import html
import posixpath
from dataclasses import dataclass, field
from typing import Callable

import yaml
from markdown_it import MarkdownIt
from markdown_it.common.utils import escapeHtml, isLinkClose, isLinkOpen
from markdown_it.rules_inline import backtick
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
    line_offset: int = 0  # lines preceding the body in lesson.md (front matter), for file-relative error lines


@dataclass
class RenderedLesson:
    html: str
    used_anchors: list[str] = field(default_factory=list)
    used_diagrams: list[str] = field(default_factory=list)
    quiz_count: int = 0
    unlinked_code: list[tuple[int, str]] = field(default_factory=list)  # (file line, span text)


def _vendor_attrs(url: str) -> dict[str, str]:
    return {"class": "rv-intrinsic", "href": url, "target": "_blank", "rel": "noopener"}


def _line(token: Token, fallback: int, ctx: RenderContext) -> int:
    body_line = token.map[0] + 1 if token.map else fallback
    return body_line + ctx.line_offset


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
    # A code span in another link's text must not render its own vendor <a> (no <a> inside an <a>):
    # "code" renders it as plain <code>, "text" as its bare escaped text (the link itself became <code>).
    # Markdown links don't nest. Raw inline <a ...> and </a> are separate html_inline tokens around the
    # link text; an unclosed <a> runs to the end of the inline block (a browser would carry it further).
    link_stamp: str | None = None
    in_raw_a = False
    for i, tok in enumerate(children):
        if tok.type == "code_inline":
            stamp = link_stamp or ("code" if in_raw_a else None)
            if stamp:
                tok.meta["rv_in_link"] = stamp
            continue
        if tok.type == "html_inline":
            if isLinkOpen(tok.content):
                in_raw_a = True
            elif isLinkClose(tok.content):
                in_raw_a = False
            continue
        if tok.type == "link_close":
            link_stamp = None
            continue
        if tok.type != "link_open":
            continue
        link_stamp = "code"
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
            link_stamp = None  # an anchor phrase is a <span>, so a span in one still links
        elif href == "!intrinsic":
            name = _link_text(children, i)
            url = ctx.lookup(name)
            if url is None:
                ctx.report.warn(f"{ctx.where}:{line}: intrinsic {name!r} is not in any vendor table")
                tok.tag = "code"
                tok.attrs = {}
                _close(children, i).tag = "code"
                link_stamp = "text"
            else:
                tok.attrs = _vendor_attrs(url)


# Quiz text accepts code spans only: raw HTML, emphasis, links, entities and backslash escapes show
# as written, and a code span is never a vendor link (an <a> inside a choice's <label> would take
# the click meant for the radio button).
_quiz_text = MarkdownIt("zero").enable("backticks").renderInline

# The keys _quiz_html reads; any other key fails the build, so a misspelled or misplaced
# `shuffle: false` cannot silently leave a question shuffled (#60).
_QUIZ_KEYS: tuple[str, ...] = ("questions",)
_QUESTION_KEYS: tuple[str, ...] = ("q", "choices", "answer", "shuffle")


def _unknown_keys(mapping: dict, accepted: tuple[str, ...]) -> list:
    # Source order; keys may be non-strings (YAML 1.1 loads `on:` as True).
    return [k for k in mapping if k not in accepted]


def _unknown_keys_message(what: str, keys: list, accepted: tuple[str, ...]) -> str:
    noun = "unknown key" if len(keys) == 1 else "unknown keys"
    return f"{what} has {noun} {', '.join(repr(k) for k in keys)} (accepted: {', '.join(accepted)})"


def _quiz_html(source: str, line: int, ctx: RenderContext) -> str:
    try:
        data = yaml.safe_load(source) or {}
    except yaml.YAMLError as e:
        raise BuildError(f"{ctx.where}:{line}: quiz block is not valid YAML: {e}") from e
    if isinstance(data, dict):
        unknown = _unknown_keys(data, _QUIZ_KEYS)
        if unknown:
            # #57 adds `shuffle` to _QUIZ_KEYS, which drops this hint; #57 and #66 add their keys there.
            hint = "; 'shuffle' goes on each question" if "shuffle" in unknown else ""
            raise BuildError(f"{ctx.where}:{line}: {_unknown_keys_message('quiz block', unknown, _QUIZ_KEYS)}{hint}")
    questions = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(questions, list) or not questions:
        raise BuildError(f"{ctx.where}:{line}: quiz block needs a non-empty 'questions' list")
    # Browsers otherwise restore checked answers (Firefox after a reload, all three engines after Back; #46); the quiz
    # forgets by design. Fixed here, not by form.reset() in app.js: restore timing may vary by engine (unmeasured).
    parts = ['<section class="rv-quiz">', "<h2>Knowledge check</h2>", '<form autocomplete="off">']
    for qi, q in enumerate(questions):
        n = qi + 1
        if isinstance(q, dict):
            unknown = _unknown_keys(q, _QUESTION_KEYS)
            if unknown:
                raise BuildError(f"{ctx.where}:{line}: {_unknown_keys_message(f'quiz question {n}', unknown, _QUESTION_KEYS)}")
        if not isinstance(q, dict) or not isinstance(q.get("q"), str):
            raise BuildError(f"{ctx.where}:{line}: quiz question {n} needs a 'q' string")
        choices = q.get("choices")
        if not isinstance(choices, list) or len(choices) < 2:
            raise BuildError(f"{ctx.where}:{line}: quiz question {n} needs at least two choices")
        answer = q.get("answer")
        if not isinstance(answer, int) or isinstance(answer, bool) or not 0 <= answer < len(choices):
            raise BuildError(f"{ctx.where}:{line}: quiz question {n} answer must be an index into choices")
        shuffle = q.get("shuffle", True)
        if not isinstance(shuffle, bool):
            raise BuildError(f"{ctx.where}:{line}: quiz question {n} shuffle must be true or false")
        # `< 3` mirrors app.js (`labels.length < 3`); test_quiz_two_choice_threshold_matches_app_js pins it.
        if q.get("shuffle") is True and len(choices) < 3:
            ctx.report.warn(
                f"{ctx.where}:{line}: quiz question {n} has two choices, which always keep their order; "
                "shuffle: true has no effect"
            )
        # #73: YAML 1.1 loads an unquoted yes/no/on/off/true/false as a bool; it still renders as True/False.
        for ci, choice in enumerate(choices):
            if isinstance(choice, bool):
                ctx.report.warn(
                    f"{ctx.where}:{line}: quiz question {n} choice {ci + 1} shows as {choice}: YAML reads an unquoted "
                    f"yes, no, on, off, true or false as a boolean; quote the choice to show it as written, "
                    f"or write '{choice}' to keep {choice}"
                )
        fixed = "" if shuffle else " data-fixed-order"
        parts.append(f'<fieldset class="rv-q" data-answer="{answer}"{fixed}><legend>{n}. {_quiz_text(q["q"])}</legend>')
        for ci, choice in enumerate(choices):
            parts.append(f'<label><input type="radio" name="q{qi}" value="{ci}"> {_quiz_text(str(choice))}</label>')
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

    # Stamp each code span with its line within the inline block, so the unlinked listing can
    # report the span's own line (a span can sit several lines into a paragraph, or wrap).
    def backticks(state, silent) -> bool:
        pos, count = state.pos, len(state.tokens)
        ok = backtick(state, silent)
        if len(state.tokens) > count:  # only a matched span pushes; push flushes pending text first
            state.tokens[-1].meta["rv_line"] = state.src.count("\n", 0, pos)
        return ok

    md.inline.ruler.at("backticks", backticks)

    def core_rewrite(state) -> None:
        for block in state.tokens:
            if block.type == "inline" and block.children:
                line = _line(block, 1, ctx)
                _rewrite_links(block.children, line, ctx, out)
                # Top level only: alt-text tokens nest in image.children and render as plain text.
                for child in block.children:
                    if child.type == "image":
                        child.map = block.map
                    elif child.type == "code_inline" and ctx.lookup(child.content) is None:
                        out.unlinked_code.append((line + child.meta.get("rv_line", 0), child.content))

    md.core.ruler.push("rv_links", core_rewrite)

    # add_render_rule binds each function as a method of the renderer, hence `self` first.
    default_code_inline = md.renderer.rules.get("code_inline")
    default_fence = md.renderer.rules.get("fence")
    default_image = md.renderer.rules.get("image")

    def code_inline(self, tokens, idx, options, env):
        content = tokens[idx].content
        in_link = tokens[idx].meta.get("rv_in_link")
        if in_link == "text":
            return escapeHtml(content)
        code = default_code_inline(tokens, idx, options, env)
        url = None if in_link else ctx.lookup(content)
        if url is None:
            return code
        attrs = "".join(f' {k}="{escapeHtml(v)}"' for k, v in _vendor_attrs(url).items())
        return f"<a{attrs}>{code}</a>"

    def fence(self, tokens, idx, options, env):
        tok = tokens[idx]
        if tok.info.strip() == "quiz":
            out.quiz_count += 1
            return _quiz_html(tok.content, _line(tok, 1, ctx), ctx)
        return default_fence(tokens, idx, options, env)

    def image(self, tokens, idx, options, env):
        tok = tokens[idx]
        src = tok.attrGet("src") or ""
        if src.endswith(".dot"):
            stem = posixpath.splitext(posixpath.basename(src))[0]
            line = _line(tok, 1, ctx)
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
