import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from revision_engine import __version__
from revision_engine.cli import main


def test_version_flag_prints_version(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_subcommand_prints_help_and_fails(capsys):
    assert main([]) == 2
    assert "rv2" in capsys.readouterr().err


REPO = Path(__file__).resolve().parents[1]
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


def test_narrate_without_model_reports_missing_voice_file(minimal_example, tmp_path, monkeypatch, capsys):
    src = tmp_path / "m"
    shutil.copytree(minimal_example, src)
    monkeypatch.setenv("RV2_VOICES", str(tmp_path / "none"))
    lesson = src / "docs/revision/chapters/01-intro/lessons/01-hello"
    assert main(["narrate", str(lesson)]) == 1
    assert "voice 'en_US-lessac-medium': no model at" in capsys.readouterr().err


def test_narrate_reports_malformed_project_yaml_without_traceback(minimal_example, tmp_path):
    src = tmp_path / "m"
    shutil.copytree(minimal_example, src)
    (src / "revision.yaml").write_text("narration: [unclosed" + chr(10), encoding="utf-8")
    lesson = src / "docs/revision/chapters/01-intro/lessons/01-hello"
    r = subprocess.run(
        [sys.executable, "-m", "revision_engine.cli", "narrate", str(lesson)],
        env={**os.environ, "RV2_VOICES": str(tmp_path / "none")},
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert r.returncode == 1
    assert r.stderr.startswith("error: ")
    assert "revision.yaml: invalid YAML:" in r.stderr
    assert "Traceback" not in r.stderr
