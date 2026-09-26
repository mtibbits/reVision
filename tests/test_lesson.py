import pytest

from revision_engine.errors import BuildError
from revision_engine.lesson import load_lesson


def test_parses_front_matter_and_body(tmp_path):
    p = tmp_path / "lesson.md"
    p.write_text(
        "---\ntitle: T\nsummary: S\nfile: k.h\nstart: a\nmedia: media/n.wav\n---\n# Hi\n\nbody\n", encoding="utf-8"
    )
    doc = load_lesson(p, "L/lesson.md")
    assert (doc.title, doc.summary, doc.file, doc.start, doc.media, doc.voice) == (
        "T", "S", "k.h", "a", "media/n.wav", None,
    )
    assert doc.body == "# Hi\n\nbody\n"


def test_missing_front_matter_is_error(tmp_path):
    p = tmp_path / "lesson.md"
    p.write_text("no front matter\n", encoding="utf-8")
    with pytest.raises(BuildError, match=r"L/lesson\.md: front matter must start with '---' on line 1"):
        load_lesson(p, "L/lesson.md")


def test_required_keys(tmp_path):
    p = tmp_path / "lesson.md"
    p.write_text("---\ntitle: T\n---\nbody\n", encoding="utf-8")
    with pytest.raises(BuildError, match=r"L/lesson\.md: front matter key 'file' is required"):
        load_lesson(p, "L/lesson.md")


def test_summary_defaults_empty(tmp_path):
    p = tmp_path / "lesson.md"
    p.write_text("---\ntitle: T\nfile: f\n---\n", encoding="utf-8")
    assert load_lesson(p, "x").summary == ""
