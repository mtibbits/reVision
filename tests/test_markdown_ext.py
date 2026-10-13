import pytest

from revision_engine.errors import BuildError, Report
from revision_engine.intrinsics import lookup
from revision_engine.markdown_ext import RenderContext, render_markdown


def ctx(**kw) -> RenderContext:
    base = dict(
        anchors={"add-fn": "k.h", "other": "z.h"},
        diagrams={"flow": '<svg class="rv-svg"></svg>'},
        lookup=lookup,
        report=Report(),
        where="L/lesson.md",
        lesson_file="k.h",
    )
    base.update(kw)
    return RenderContext(**base)


def test_anchor_reference_becomes_span():
    out = render_markdown("The [adder](@add-fn) loop.\n", ctx())
    assert '<span class="rv-anchor" data-anchor="add-fn" tabindex="0">adder</span>' in out.html
    assert out.used_anchors == ["add-fn"]


def test_unknown_anchor_is_error_with_line():
    with pytest.raises(BuildError, match=r"L/lesson\.md:3: unknown anchor 'nope'"):
        render_markdown("a\n\nsee [x](@nope)\n", ctx())


def test_line_offset_shifts_error_lines_to_file_numbering():
    with pytest.raises(BuildError, match=r"L/lesson\.md:7: unknown anchor 'nope'"):
        render_markdown("a\n\nsee [x](@nope)\n", ctx(line_offset=4))


def test_anchor_in_other_file_rejected():
    with pytest.raises(BuildError, match=r"anchor 'other' resolves in 'z\.h' but this lesson shows 'k\.h'"):
        render_markdown("[x](@other)\n", ctx())


def test_intrinsic_reference_links_out():
    out = render_markdown("Use [_mm256_fmadd_ps](!intrinsic) here.\n", ctx())
    assert '<a class="rv-intrinsic" href="https://www.intel.com/' in out.html
    assert 'target="_blank" rel="noopener">_mm256_fmadd_ps</a>' in out.html


def test_unknown_intrinsic_reference_warns_and_renders_code():
    c = ctx()
    out = render_markdown("Use [foo_bar](!intrinsic).\n", c)
    assert "<code>foo_bar</code>" in out.html and "rv-intrinsic" not in out.html
    assert c.report.warnings == ["L/lesson.md:1: intrinsic 'foo_bar' is not in any vendor table"]


def test_bare_code_autolinks_known_intrinsic_only():
    out = render_markdown("`vmlaq_f32` and `printf`\n", ctx())
    assert '<a class="rv-intrinsic" href="https://developer.arm.com/' in out.html
    assert "<code>printf</code>" in out.html


def test_bare_code_autolinks_riscv_intrinsic():
    out = render_markdown("`__riscv_vfmacc_tu` and `__riscv_vfmacc_vv_f32m8`\n", ctx())
    assert (
        '<a class="rv-intrinsic" href="https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/'
        "policy_funcs/overloaded_intrinsic_funcs/04_vector_floating-point_intrinsics.html"
        '#policy-variant-overloadedvector-single-width-floating-point-fused-multiply-add" '
        'target="_blank" rel="noopener"><code>__riscv_vfmacc_tu</code></a>'
    ) in out.html
    assert "<code>__riscv_vfmacc_vv_f32m8</code>" in out.html
    assert out.html.count("rv-intrinsic") == 1


def test_dot_image_inlines_diagram():
    out = render_markdown("![Call flow](diagrams/flow.dot)\n", ctx())
    assert '<figure class="rv-diagram" id="diagram-flow" data-diagram="flow">' in out.html
    assert '<svg class="rv-svg"></svg>' in out.html and "<figcaption>Call flow</figcaption>" in out.html
    assert out.used_diagrams == ["flow"]


def test_missing_diagram_is_error():
    with pytest.raises(BuildError, match=r"L/lesson\.md:1: diagram 'nope' .*not found"):
        render_markdown("![x](diagrams/nope.dot)\n", ctx())


QUIZ = """```quiz
questions:
  - q: Why eight lanes?
    choices: [Dependency chain, Register width, Both]
    answer: 2
  - q: Second?
    choices: [A, B]
    answer: 0
```
"""


def test_quiz_fence_renders_widget():
    out = render_markdown(QUIZ, ctx())
    assert out.quiz_count == 1
    assert '<section class="rv-quiz">' in out.html
    assert 'data-answer="2"' in out.html and 'name="q1"' in out.html
    assert '<input type="radio" name="q0" value="2">' in out.html
    assert "Check answers" in out.html


def test_quiz_validation():
    bad = "```quiz\nquestions:\n  - q: x\n    choices: [only]\n    answer: 3\n```\n"
    with pytest.raises(BuildError, match=r"L/lesson\.md:1: quiz question 1 needs at least two choices"):
        render_markdown(bad, ctx())


def test_ordinary_markdown_still_works():
    out = render_markdown("# H\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```c\nint x;\n```\n", ctx())
    assert "<h1>H</h1>" in out.html and "<table>" in out.html
    assert '<pre><code class="language-c">' in out.html


def test_unlinked_code_spans_are_recorded_with_lines():
    body = "\n".join(
        [
            "`vmlaq_f32` and `printf`",  # 1: linked span absent, unlinked present
            "",
            "first `a",  # 3: wrapped span opens here
            "b` mid",  # 4
            "then `c`",  # 5: the span after a wrapped one
            "",
            "hard  ",  # 7: hardbreak
            "break `d`",  # 8
            "",
            "> quote `e`",  # 10: blockquote
            "",
            "- item `f`",  # 12: list item
            "",
            "# Heading `g`",  # 14: heading
            "",
            "[`unknown_x`](!intrinsic) and [`nope`](https://example.com)",  # 16: link text
            "",
            "![`alt_only`](x.png)",  # 18: image alt, excluded
            "",
            "```c",  # 20-22: fence, excluded
            "x = `in_fence`;",
            "```",
            "",
            "    `indented`",  # 24: indented code block, excluded
        ]
    ) + "\n"
    c = ctx()
    out = render_markdown(body, c)
    assert out.unlinked_code == [
        (1, "printf"),
        (3, "a b"),
        (5, "c"),
        (8, "d"),
        (10, "e"),
        (12, "f"),
        (14, "g"),
        (16, "unknown_x"),
        (16, "nope"),
    ]
    assert c.report.warnings == ["L/lesson.md:16: intrinsic 'unknown_x' is not in any vendor table"]


def test_unlinked_code_spans_include_table_body_cells():
    out = render_markdown("| h |\n|---|\n| `cell` |\n", ctx())
    assert out.unlinked_code == [(3, "cell")]


def test_unlinked_code_skips_quiz_fence():
    quiz = QUIZ.replace("Why eight lanes?", "Why `in_quiz` lanes?")
    assert "`in_quiz`" in quiz
    out = render_markdown(quiz, ctx())
    assert out.quiz_count == 1
    assert out.unlinked_code == []


def test_unlinked_code_lines_shift_by_line_offset():
    out = render_markdown("`x`\n", ctx(line_offset=5))
    assert out.unlinked_code == [(6, "x")]


def test_unlinked_code_recording_leaves_html_unchanged():
    out = render_markdown("`vmlaq_f32` and `printf`\n", ctx())
    assert "<code>printf</code>" in out.html
    assert out.html.count("rv-intrinsic") == 1
