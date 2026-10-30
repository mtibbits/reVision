"""Layout with a long source file: the code pane must scroll, not the page."""

from __future__ import annotations

import pytest

from .conftest import build_example, open_lesson, serve

LONG_LINES = 600


@pytest.fixture(scope="module")
def long_site_url(tmp_path_factory):
    def edit(src):
        body = "\n".join(f"    x += {i};" for i in range(LONG_LINES - 4))
        (src / "src" / "long.c").write_text(f"int f(int x)\n{{\n{body}\n    return x;\n}}\n", encoding="utf-8")
        lesson = src / "docs/revision/chapters/01-intro/lessons/03-long"
        lesson.mkdir()
        (lesson / "lesson.md").write_text(
            "---\ntitle: Long\nfile: src/long.c\nstart: ret\n---\n# Long\n\nThe [return](@ret) is at the end.\n",
            encoding="utf-8",
        )
        (lesson / "anchors.yaml").write_text("ret:\n  match: 'return x;'\n", encoding="utf-8")
        cur = src / "docs/revision/curriculum.yaml"
        cur.write_text(
            cur.read_text(encoding="utf-8").rstrip("\n")
            + "\n      - slug: long\n        title: Long\n        path: chapters/01-intro/lessons/03-long\n",
            encoding="utf-8",
        )

    with serve(build_example(tmp_path_factory, "long", edit=edit)) as url:
        yield url


@pytest.mark.parametrize("width", [1400, 700])
def test_long_file_scrolls_inside_code_pane(page, long_site_url, width):
    page.set_viewport_size({"width": width, "height": 800})
    open_lesson(page, long_site_url + "intro/long/")
    metrics = page.evaluate(
        "(() => { const b = document.querySelector('.rv-code-body');"
        " return { bodyScrollH: b.scrollHeight, bodyClientH: b.clientHeight, bodyTop: b.scrollTop,"
        " mainH: document.querySelector('.rv-main').getBoundingClientRect().height,"
        " docH: document.documentElement.scrollHeight }; })()"
    )
    assert metrics["bodyScrollH"] > metrics["bodyClientH"], metrics  # the code body is the scroller
    assert metrics["mainH"] <= 800, metrics  # nothing grows past the viewport
    assert metrics["docH"] <= 800, metrics
    assert metrics["bodyTop"] > 0, metrics  # the start anchor near the end was scrolled into view
