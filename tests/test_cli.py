import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from revision_engine import __version__
from revision_engine.cli import main
from revision_engine.config import DEFAULT_VOICE


def test_version_flag_prints_version(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_subcommand_prints_help_and_fails(capsys):
    assert main([]) == 2
    assert "rv2" in capsys.readouterr().err


REPO = Path(__file__).resolve().parents[1]
PROJECT_VOICE = "en_US-amy-low"
FIXED = "0123456789abcdef0123456789abcdef01234567"


def test_build_command_writes_site(minimal_example, tmp_path, capsys):
    src = tmp_path / "m"
    shutil.copytree(minimal_example, src)
    out = tmp_path / "site"
    assert main(["build", "--root", str(src), "--output", str(out), "--commit", FIXED]) == 0
    assert (out / "intro/hello/index.html").is_file()
    assert "2 pages" in capsys.readouterr().out


def test_check_command_reports_error_and_exit_1(minimal_example, tmp_path, capsys):
    src = tmp_path / "m"
    shutil.copytree(minimal_example, src)
    (src / "docs/revision/chapters/01-intro/lessons/02-quiet/anchors.yaml").write_text(
        "add-fn:\n  match: nothing\n", encoding="utf-8"
    )
    assert main(["check", "--root", str(src), "--commit", FIXED]) == 1
    err = capsys.readouterr().err
    assert "error:" in err and "no line contains 'nothing'" in err


def test_narrate_silent_regenerates_cues(minimal_example, tmp_path):
    src = tmp_path / "m"
    shutil.copytree(minimal_example, src)
    lesson = src / "docs/revision/chapters/01-intro/lessons/01-hello"
    (lesson / "cues.json").unlink()
    assert main(["narrate", str(lesson), "--silent"]) == 0
    assert (lesson / "cues.json").is_file()


def _set_project_voice(src: Path, voice: str) -> None:
    cfg = src / "revision.yaml"
    text = cfg.read_text(encoding="utf-8")
    assert text.count("voice: en_US-lessac-medium") == 1
    cfg.write_text(text.replace("voice: en_US-lessac-medium", f"voice: {voice}"), encoding="utf-8", newline="\n")


def _narrate_cli(lesson: Path, voices: Path, *extra: str) -> subprocess.CompletedProcess:
    """Run `rv2 narrate` in a subprocess, so a traceback is observed, not assumed."""
    return subprocess.run(
        [sys.executable, "-m", "revision_engine.cli", "narrate", str(lesson), *extra],
        env={**os.environ, "RV2_VOICES": str(voices)},
        capture_output=True,
        text=True,
        cwd=REPO,
    )


def test_narrate_without_model_reports_missing_voice_file(src, tmp_path, monkeypatch, capsys):
    _set_project_voice(src, PROJECT_VOICE)
    assert PROJECT_VOICE != DEFAULT_VOICE
    monkeypatch.setenv("RV2_VOICES", str(tmp_path / "none"))
    lesson = src / "docs/revision/chapters/01-intro/lessons/01-hello"
    assert main(["narrate", str(lesson)]) == 1
    assert f"voice '{PROJECT_VOICE}': no model at" in capsys.readouterr().err


def test_narrate_reports_malformed_project_yaml_without_traceback(src, tmp_path):
    (src / "revision.yaml").write_text("narration: [unclosed" + chr(10), encoding="utf-8")
    r = _narrate_cli(src / "docs/revision/chapters/01-intro/lessons/01-hello", tmp_path / "none")
    assert r.returncode == 1
    assert r.stderr.startswith("error: ")
    assert "revision.yaml: invalid YAML:" in r.stderr
    assert "Traceback" not in r.stderr


def _voices_beside_outside_model(tmp_path: Path) -> Path:
    """An empty voices dir, with a model planted at <voices>/../outside/x.onnx."""
    voices = tmp_path / "voices"
    voices.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.onnx").write_bytes(b"x")
    (outside / "x.onnx.json").write_text('{"audio": {"sample_rate": 22050}}', encoding="utf-8")
    return voices


def test_narrate_rejects_path_voice_from_cli(src, tmp_path):
    lesson = src / "docs/revision/chapters/01-intro/lessons/01-hello"
    r = _narrate_cli(lesson, _voices_beside_outside_model(tmp_path), "--voice", "../outside/x")
    assert r.returncode == 1
    assert r.stderr.startswith("error: --voice: voice '../outside/x' is not a voice name")
    assert "Traceback" not in r.stderr
    assert r.stderr.count("\n") == 1


def test_narrate_rejects_path_voice_from_project(src, tmp_path):
    _set_project_voice(src, "../outside/x")
    r = _narrate_cli(src / "docs/revision/chapters/01-intro/lessons/01-hello", _voices_beside_outside_model(tmp_path))
    assert r.returncode == 1
    assert r.stderr.startswith("error: ")
    assert "revision.yaml (narration.voice): voice '../outside/x' is not a voice name" in r.stderr
    assert "Traceback" not in r.stderr
    assert r.stderr.count("\n") == 1


def test_narrate_silent_ignores_voice_rule(src):
    """Born green: --silent never locates a model, so the voice rule does not apply."""
    lesson = src / "docs/revision/chapters/01-intro/lessons/01-hello"
    assert main(["narrate", str(lesson), "--silent", "--voice", "../x"]) == 0
    assert json.loads((lesson / "cues.json").read_text(encoding="utf-8"))["voice"] == "../x"


LESSONS = "docs/revision/chapters/01-intro/lessons"
OK = f"ok: all checks passed at commit {FIXED[:7]}\n"


def _append(src: Path, lesson: str, text: str, marker: str) -> tuple[str, int]:
    """Append text to a lesson; return its repo-relative lesson.md path and the 1-based line holding marker."""
    rel = f"{LESSONS}/{lesson}/lesson.md"
    md = src / rel
    md.write_text(md.read_text(encoding="utf-8") + text, encoding="utf-8", newline="\n")
    lines = md.read_text(encoding="utf-8").splitlines()
    return rel, next(i for i, line in enumerate(lines, start=1) if marker in line)


def _with_bogus_intrinsic(src: Path) -> str:
    rel, n = _append(src, "02-quiet", "\nUse [_mm_bogus_ps](!intrinsic).\n", "_mm_bogus_ps")
    return f"{rel}:{n}: intrinsic '_mm_bogus_ps' is not in any vendor table"


def _with_unlinked_span(src: Path, span: str = "printf") -> str:
    text = f"\nCall `{span}` to show it.\n\n```c\nx = `in_fence`;\n```\n"
    rel, n = _append(src, "01-hello", text, f"Call `{span}`")
    return f"unlinked: {rel}:{n}: {span!r}"


@pytest.fixture
def src(minimal_example, tmp_path):
    dst = tmp_path / "m"
    shutil.copytree(minimal_example, dst)
    return dst


def _check(src: Path, *flags: str) -> int:
    return main(["check", "--root", str(src), "--commit", FIXED, *flags])


def test_check_strict_passes_with_zero_warnings(src, capsys):
    assert _check(src, "--strict") == 0
    out, err = capsys.readouterr()
    assert out == OK
    assert err == ""


def test_check_strict_fails_on_one_warning(src, capsys):
    w = _with_bogus_intrinsic(src)
    assert _check(src, "--strict") == 1
    out, err = capsys.readouterr()
    assert out == f"warning: {w}\n1 warning(s)\n"
    assert err == "error: --strict: 1 warning(s)\n"


def test_check_without_strict_still_exits_0_on_warning(src, capsys):
    w = _with_bogus_intrinsic(src)
    assert _check(src) == 0
    out, err = capsys.readouterr()
    assert out == OK + f"warning: {w}\n1 warning(s)\n"
    assert err == ""


def test_check_list_unlinked_lists_only_unlinked_spans(src, capsys):
    u = _with_unlinked_span(src)
    assert _check(src, "--list-unlinked") == 0
    out, err = capsys.readouterr()
    assert out == OK + u + "\n1 unlinked code span(s)\n"
    assert err == ""


def test_check_without_list_unlinked_prints_no_listing(src, capsys):
    _with_unlinked_span(src)
    assert _check(src) == 0
    out, err = capsys.readouterr()
    assert out == OK
    assert err == ""


def test_check_list_unlinked_with_no_spans_prints_only_ok(src, capsys):
    assert _check(src, "--list-unlinked") == 0
    out, err = capsys.readouterr()
    assert out == OK
    assert err == ""


def test_check_list_unlinked_does_not_trip_strict(src, capsys):
    u = _with_unlinked_span(src)
    assert _check(src, "--strict", "--list-unlinked") == 0
    out, err = capsys.readouterr()
    assert out == OK + u + "\n1 unlinked code span(s)\n"
    assert err == ""


def test_check_strict_and_list_unlinked_with_warning(src, capsys):
    w = _with_bogus_intrinsic(src)
    u = _with_unlinked_span(src)
    assert _check(src, "--strict", "--list-unlinked") == 1
    out, err = capsys.readouterr()
    assert out == u + "\n1 unlinked code span(s)\n" + f"warning: {w}\n1 warning(s)\n"
    assert err == "error: --strict: 1 warning(s)\n"


def test_check_help_documents_new_flags(capsys):
    with pytest.raises(SystemExit) as e:
        main(["check", "--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "--strict" in out and "--list-unlinked" in out


def test_check_list_unlinked_survives_unencodable_stdout(src, monkeypatch):
    _with_unlinked_span(src, span="\u2192")
    buf = io.BytesIO()
    stream = io.TextIOWrapper(buf, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stream)
    assert _check(src, "--list-unlinked") == 0
    stream.flush()
    assert "'\\u2192'" in buf.getvalue().decode("cp1252")


def test_check_strict_verdict_follows_report_in_merged_log(src):
    # CI merges stdout (block-buffered on a pipe) with stderr: the verdict must follow its warnings.
    w = _with_bogus_intrinsic(src)
    r = subprocess.run(
        [sys.executable, "-m", "revision_engine.cli", "check", "--root", str(src), "--commit", FIXED, "--strict"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=REPO,
    )
    assert r.returncode == 1
    assert r.stdout == f"warning: {w}\n1 warning(s)\nerror: --strict: 1 warning(s)\n"


needs_dot = pytest.mark.skipif(shutil.which("dot") is None, reason="graphviz dot not installed")
FLOW = f"{LESSONS}/01-hello/diagrams/flow.dot"


def _link_node(src: Path, node: str, attr: str) -> str:
    """Add attr to a flow.dot node; return the warning a link on an anchored node gives."""
    dot = src / FLOW
    text = dot.read_text(encoding="utf-8")
    assert text.count(f'id="{node}"') == 1
    dot.write_text(text.replace(f'id="{node}"', f'id="{node}", {attr}'), encoding="utf-8", newline="\n")
    return f"{FLOW}: node '{node}' is an anchor; its link is removed"


def _svg_group(html: str, node: str) -> str:
    """The SVG node group for node: its open tag up to the next node/edge group, or </svg>."""
    head = f'<g id="{node}" class="node'
    assert html.count(head) == 1
    start = html.index(head)
    end = html.index("</svg>", start)
    for m in re.finditer(r"<g\b[^>]*>", html[start + len(head) : end]):
        cls = re.search(r'(?<![\w-])class="([^"]*)"', m.group(0))
        if cls and {"node", "edge"}.intersection(cls.group(1).split()):
            return html[start : start + len(head) + m.start()]
    return html[start:end]


@needs_dot
def test_check_warns_on_link_on_anchored_node(src, capsys):
    w = _link_node(src, "add-fn", 'URL="https://example.com/add"')
    assert _check(src) == 0
    out, err = capsys.readouterr()
    assert out == OK + f"warning: {w}\n1 warning(s)\n"
    assert err == ""


@needs_dot
def test_check_strict_fails_on_link_on_anchored_node(src, capsys):
    w = _link_node(src, "add-fn", 'URL="https://example.com/add"')
    assert _check(src, "--strict") == 1
    out, err = capsys.readouterr()
    assert out == f"warning: {w}\n1 warning(s)\n"
    assert err == "error: --strict: 1 warning(s)\n"


@needs_dot
def test_check_no_warning_for_tooltip_only_anchored_node(src, capsys):
    _link_node(src, "add-fn", 'tooltip="adds"')
    assert _check(src, "--strict") == 0
    assert capsys.readouterr().out == OK


@needs_dot
def test_check_no_warning_for_link_on_non_anchored_node(src, capsys):
    _link_node(src, "printf-node", 'URL="https://example.com/printf"')
    assert _check(src, "--strict") == 0
    assert capsys.readouterr().out == OK


@needs_dot
def test_build_strips_anchored_link_and_keeps_free_link(src, tmp_path, capsys):
    w = _link_node(src, "add-fn", 'URL="https://example.com/add"')
    _link_node(src, "printf-node", 'href="https://example.com/printf"')
    out = tmp_path / "site"
    assert main(["build", "--root", str(src), "--output", str(out), "--commit", FIXED]) == 0
    html = (out / "intro/hello/index.html").read_text(encoding="utf-8")
    g = _svg_group(html, "add-fn")
    assert 'data-anchor="add-fn"' in g
    assert "example.com/add" not in g and "href=" not in g
    assert 'xlink:href="https://example.com/printf"' in _svg_group(html, "printf-node")
    assert f"warning: {w}\n" in capsys.readouterr().out
