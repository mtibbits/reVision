import re

import pytest
import yaml

from revision_engine.errors import BuildError, Report
from revision_engine.intrinsics import lookup
from revision_engine.markdown_ext import RenderContext, render_markdown
from tests.ci_pins import ROOT


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


def test_backticked_intrinsic_reference_matches_bare_code_span():
    a = render_markdown("[`vmlaq_f32`](!intrinsic)\n", ctx()).html
    b = render_markdown("`vmlaq_f32`\n", ctx()).html
    assert a == b
    assert a.count("<a ") == 1


@pytest.mark.parametrize("name", ["not_in_any_table", "it's"])
def test_backticked_unknown_intrinsic_reference_renders_one_code(name):
    c = ctx()
    html = render_markdown(f"[`{name}`](!intrinsic)\n", c).html
    assert html.count("<code>") == 1
    assert "<code><code>" not in html
    assert f"<code>{name}</code>" in html
    assert "rv-intrinsic" not in html
    assert c.report.warnings == [f"L/lesson.md:1: intrinsic {name!r} is not in any vendor table"]


@pytest.mark.parametrize("src", ["[`vmlaq_f32`](https://example.com/x)", "[see `vmlaq_f32`](https://example.com/x)"])
def test_code_span_inside_url_link_is_plain_code(src):
    html = render_markdown(src + "\n", ctx()).html
    assert html.count("<a ") == 1
    assert "rv-intrinsic" not in html
    assert '<a href="https://example.com/x">' in html
    assert "<code>vmlaq_f32</code>" in html


def test_code_span_in_emphasis_inside_link_is_plain_code():
    html = render_markdown("[**`vmlaq_f32`**](!intrinsic)\n", ctx()).html
    assert html.count("<a ") == 1
    assert "<strong><code>vmlaq_f32</code></strong>" in html


def test_known_code_span_inside_unknown_intrinsic_reference_is_text():
    # The unknown link is already reported; its known span does not keep a vendor link inside the <code>.
    c = ctx()
    html = render_markdown("[`vmlaq_f32` overview](!intrinsic)\n", c).html
    assert "<code>vmlaq_f32 overview</code>" in html
    assert html.count("<a ") == 0
    assert c.report.warnings == ["L/lesson.md:1: intrinsic 'vmlaq_f32 overview' is not in any vendor table"]


def test_code_span_inside_raw_html_link_is_plain_code():
    html = render_markdown('<a href="https://example.com/x">`vmlaq_f32`</a>\n', ctx()).html
    assert html.count("<a ") == 1
    assert "rv-intrinsic" not in html
    # <abbr> is not <a>: its span still links.
    html = render_markdown("<abbr>`vmlaq_f32`</abbr>\n", ctx()).html
    assert '<abbr><a class="rv-intrinsic"' in html


def test_code_span_inside_anchor_phrase_stays_vendor_link():
    html = render_markdown("[`vmlaq_f32`](@add-fn)\n", ctx()).html
    assert (
        '<span class="rv-anchor" data-anchor="add-fn" tabindex="0">'
        '<a class="rv-intrinsic" href="https://developer.arm.com/'
    ) in html
    assert html.count("<a ") == 1


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


def _quiz_with_shuffle(line: str) -> str:
    return "```quiz\nquestions:\n  - q: Which?\n    choices: [a, b, c]\n    answer: 0\n" + line + "```\n"


def test_quiz_shuffle_false_marks_fieldset():
    out = render_markdown(_quiz_with_shuffle("    shuffle: false\n"), ctx())
    assert '<fieldset class="rv-q" data-answer="0" data-fixed-order>' in out.html


def test_quiz_default_emits_no_order_marker():
    out = render_markdown(QUIZ, ctx())
    assert "data-fixed-order" not in out.html
    # The static page, as a reader without JavaScript sees it, lists choices in the authored order.
    fieldsets = out.html.split("<fieldset")[1:]
    assert [re.findall(r'value="(\d+)"', fs) for fs in fieldsets] == [["0", "1", "2"], ["0", "1"]]


def test_quiz_shuffle_true_is_the_default():
    explicit = render_markdown(_quiz_with_shuffle("    shuffle: true\n"), ctx())
    assert explicit.html == render_markdown(_quiz_with_shuffle(""), ctx()).html


def test_quiz_shuffle_must_be_boolean():
    with pytest.raises(BuildError, match=r"L/lesson\.md:1: quiz question 1 shuffle must be true or false"):
        render_markdown(_quiz_with_shuffle("    shuffle: 'false'\n"), ctx())


QUIZ_YAML_ERROR = "quiz block is not valid YAML"


@pytest.mark.parametrize(
    "body",
    [
        "questions:\n  - q: `x` first?\n    choices: [a, b]\n    answer: 0\n",
        "questions:\n  - q: Which?\n    choices: [`a`, b]\n    answer: 0\n",
        "questions:\n  - q: Which?\n    choices:\n      - `a`\n      - b\n    answer: 0\n",
    ],
    ids=["q", "flow-choice", "block-choice"],
)
def test_quiz_unquoted_leading_backtick_is_yaml_error(body):
    with pytest.raises(BuildError, match=r"L/lesson\.md:1: " + re.escape(QUIZ_YAML_ERROR)):
        render_markdown("```quiz\n" + body + "```\n", ctx())


def test_quiz_code_span_in_question_renders_code():
    body = "```quiz\nquestions:\n  - q: 'How many floats does `_mm256_fmadd_ps` multiply?'\n    choices: [four, eight]\n    answer: 1\n```\n"
    out = render_markdown(body, ctx())
    assert "<legend>1. How many floats does <code>_mm256_fmadd_ps</code> multiply?</legend>" in out.html
    assert "rv-intrinsic" not in out.html
    assert out.unlinked_code == []


def test_quiz_code_span_in_choice_renders_code():
    body = "```quiz\nquestions:\n  - q: Which adds?\n    choices: ['`vaddq_f32`', plain]\n    answer: 0\n```\n"
    out = render_markdown(body, ctx())
    assert '<input type="radio" name="q0" value="0"> <code>vaddq_f32</code></label>' in out.html
    assert "rv-intrinsic" not in out.html


def test_quiz_raw_html_is_escaped():
    body = "```quiz\nquestions:\n  - q: \"<script>alert(1)</script>?\"\n    choices: ['<b>bold</b>', '`<i>`']\n    answer: 0\n```\n"
    out = render_markdown(body, ctx())
    assert "<legend>1. &lt;script&gt;alert(1)&lt;/script&gt;?</legend>" in out.html
    assert "<script" not in out.html
    assert "<b>" not in out.html
    assert "&lt;b&gt;bold&lt;/b&gt;" in out.html
    assert "<code>&lt;i&gt;</code>" in out.html


def test_quiz_plain_text_renders_as_before():
    body = "```quiz\nquestions:\n  - q: Which is the program's \"main\" & <entry>?\n    choices: [5, add]\n    answer: 0\n```\n"
    out = render_markdown(body, ctx())
    # The one intended byte change: an apostrophe is no longer written as &#x27;.
    assert "<legend>1. Which is the program's &quot;main&quot; &amp; &lt;entry&gt;?</legend>" in out.html
    assert '<input type="radio" name="q0" value="0"> 5</label>' in out.html


def test_quiz_other_markup_shows_as_written():
    fence = r"""questions:
  - q: '*em* _u_ [see](@add-fn) a \* b &amp; &copy; lone ` tick \x'
    choices: ['a\`b` c', plain]
    answer: 0
"""
    q = yaml.safe_load(fence)["questions"][0]
    assert q["q"] == r"*em* _u_ [see](@add-fn) a \* b &amp; &copy; lone ` tick \x"
    assert q["choices"][0] == r"a\`b` c"
    out = render_markdown("```quiz\n" + fence + "```\n", ctx())
    assert r"<legend>1. *em* _u_ [see](@add-fn) a \* b &amp;amp; &amp;copy; lone ` tick \x</legend>" in out.html
    assert r'value="0"> a\<code>b</code> c</label>' in out.html
    assert "<em>" not in out.html
    assert "rv-anchor" not in out.html
    assert out.used_anchors == []


def _readme_lesson_section() -> str:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    start = readme.index("## Writing a lesson")
    return " ".join(readme[start : readme.index("\n## ", start)].split())


def test_readme_documents_quiz_markup():
    section = _readme_lesson_section().lower()
    assert "code span" in section
    assert "quote" in section
    assert QUIZ_YAML_ERROR.lower() in section


def test_readme_quiz_quoting_example_keeps_backslashes():
    # The README's quoting example, with a backslash in its code span, must show it as written.
    q_line = re.search(r"`` (q: .*?) ``", _readme_lesson_section()).group(1)
    q_line = q_line.replace("`vaddq_f32`", r"`\n`")
    out = render_markdown("```quiz\nquestions:\n  - " + q_line + "\n    choices: [a, b]\n    answer: 0\n```\n", ctx())
    assert r"<code>\n</code>" in out.html


def test_readme_documents_quiz_shuffle():
    # The README's opt-out, used as written, must keep a question's authored order.
    m = re.search(r"`(shuffle: false)`", _readme_lesson_section())
    assert m
    out = render_markdown(_quiz_with_shuffle("    " + m.group(1) + "\n"), ctx())
    assert "data-fixed-order" in out.html


def test_quiz_single_quoted_doubled_apostrophe():
    body = "```quiz\nquestions:\n  - q: '`main` is the program''s entry?'\n    choices: [yes, no]\n    answer: 0\n```\n"
    out = render_markdown(body, ctx())
    assert "<legend>1. <code>main</code> is the program's entry?</legend>" in out.html


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
