import json
import re
import shutil

import pytest

from revision_engine.build import build
from revision_engine.errors import BuildError

FIXED = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture
def example_copy(minimal_example, tmp_path):
    dst = tmp_path / "minimal"
    shutil.copytree(minimal_example, dst)
    return dst


def test_builds_pages_index_and_site_json(example_copy, tmp_path):
    out = tmp_path / "out"
    result = build(example_copy, output=out, commit=FIXED)
    assert (out / "intro" / "hello" / "index.html").is_file()
    assert (out / "intro" / "quiet" / "index.html").is_file()
    assert (out / "index.html").read_text(encoding="utf-8").count("intro/hello/") >= 1
    site = json.loads((out / "site.json").read_text(encoding="utf-8"))
    assert site["title"] == "reVision minimal example"
    assert site["chapters"][0]["lessons"][0]["href"] == "intro/hello/"
    assert result.commit == FIXED and len(result.pages) == 2


def test_page_contents(example_copy, tmp_path):
    out = tmp_path / "out"
    build(example_copy, output=out, commit=FIXED)
    page = (out / "intro" / "hello" / "index.html").read_text(encoding="utf-8")
    assert "0123456" in page and f"https://github.com/mtibbits/reVision/blob/{FIXED}/src/hello.c" in page
    assert page.count('class="rv-line"') == 15
    data = json.loads(re.search(r'<script type="application/json" id="rv-data">(.*?)</script>', page, re.S).group(1))
    assert data["anchors"]["add-fn"] == {"start": 5, "end": 8}
    assert data["start"] == "add-fn"
    assert [v["name"] for v in data["variants"]] == ["add-fn", "main-fn"]
    assert data["cues"][2]["show"] == ["main-fn", "call-site"]
    assert 'data-anchor="add-expr"' in page and 'data-diagram="flow"' in page and "rv-quiz" in page
    assert 'src="media/narration.wav"' in page
    assert (out / "intro" / "hello" / "media" / "narration.wav").is_file()
    assert re.search(r'href="\.\./\.\./assets/styles\.[0-9a-f]{8}\.css"', page)
    assert re.search(r'src="\.\./\.\./assets/app\.[0-9a-f]{8}\.js"', page)


def test_lesson_without_media_collapses_pane(example_copy, tmp_path):
    out = tmp_path / "out"
    build(example_copy, output=out, commit=FIXED)
    page = (out / "intro" / "quiet" / "index.html").read_text(encoding="utf-8")
    assert re.search(r'<section class="rv-media" id="rv-media" hidden', page)
    data = json.loads(re.search(r'id="rv-data">(.*?)</script>', page, re.S).group(1))
    assert data["cues"] is None and data["start"] is None


def test_check_only_writes_nothing(example_copy, tmp_path):
    out = tmp_path / "out"
    build(example_copy, output=out, commit=FIXED, check_only=True)
    assert not out.exists()


def test_missing_cues_json_tells_author_to_narrate(example_copy, tmp_path):
    (example_copy / "docs/revision/chapters/01-intro/lessons/01-hello/cues.json").unlink()
    with pytest.raises(BuildError, match=r"01-hello: narration\.yaml present but cues\.json missing; run 'rv2 narrate"):
        build(example_copy, output=tmp_path / "out", commit=FIXED)


def test_cue_show_must_be_known_anchor(example_copy, tmp_path):
    cues_path = example_copy / "docs/revision/chapters/01-intro/lessons/01-hello/cues.json"
    cues = json.loads(cues_path.read_text(encoding="utf-8"))
    cues["segments"][0]["show"] = ["ghost"]
    cues_path.write_text(json.dumps(cues), encoding="utf-8")
    with pytest.raises(BuildError, match=r"cues\.json: segment 1 shows unknown anchor 'ghost'"):
        build(example_copy, output=tmp_path / "out", commit=FIXED)


def test_start_anchor_must_exist(example_copy, tmp_path):
    md = example_copy / "docs/revision/chapters/01-intro/lessons/02-quiet/lesson.md"
    md.write_text(
        md.read_text(encoding="utf-8").replace("file: src/hello.c\n", "file: src/hello.c\nstart: nope\n"),
        encoding="utf-8",
    )
    with pytest.raises(BuildError, match=r"02-quiet/lesson\.md: start anchor 'nope' is not defined"):
        build(example_copy, output=tmp_path / "out", commit=FIXED)


def test_refuses_to_clear_repository_root(example_copy):
    with pytest.raises(BuildError, match="output folder must be inside the repository and not the repository itself"):
        build(example_copy, output=example_copy, commit=FIXED)


def test_requires_commit_when_not_git(example_copy, tmp_path, monkeypatch):
    monkeypatch.setattr("revision_engine.build.git_commit", lambda root: None)
    with pytest.raises(BuildError, match="not a git repository; pass --commit"):
        build(example_copy, output=tmp_path / "out")
