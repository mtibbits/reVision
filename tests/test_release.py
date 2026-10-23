"""tools/release.py decides when CI tags and releases a version bump, and finds its notes.

Fixture versions use the implausible 9.8.x family, so this file never carries the engine's
version (tests/test_release_doc.py).
"""

from __future__ import annotations

import json
import subprocess

import pytest
import yaml

from tests.ci_pins import ROOT
from tests.test_release_doc import INSTALL_RE
from tools.release import (
    INSTALL_BLOCK,
    NOTHING,
    Decision,
    ReleaseError,
    annotation,
    decide,
    main,
    release_exists,
    release_notes,
    release_pull,
)

H = "a" * 40
O = "b" * 40


def test_decide_bump_tags_and_releases():
    assert decide("9.8.7", "9.8.8", {"v9.8.7": O}, H) == Decision("9.8.8", True, True)


def test_decide_unchanged_does_nothing():
    assert decide("9.8.8", "9.8.8", {"v9.8.8": O}, H) == NOTHING


@pytest.mark.parametrize(
    "after", ["9.8.8.dev0", "9.8.8rc1", "9.8.8.post1", "9.8.8+local", "9.8", "9.8.8.0", "09.8.8"]
)
def test_decide_non_final_does_nothing(after):
    assert decide("9.8.7", after, {}, H) == NOTHING


def test_decide_dev_to_final_releases():
    assert decide("9.8.8.dev0", "9.8.8", {"v9.8.7": O}, H) == Decision("9.8.8", True, True)


def test_decide_tag_on_head_releases_only():
    assert decide("9.8.7", "9.8.8", {"v9.8.8": H}, H) == Decision("9.8.8", False, True)


def test_decide_tag_on_other_commit_errors():
    with pytest.raises(ReleaseError, match=r"v9\.8\.8 already tags .*never moves a tag"):
        decide("9.8.7", "9.8.8", {"v9.8.8": O}, H)


def test_decide_down_from_before_errors():
    with pytest.raises(
        ReleaseError, match=r"went down: 9\.8\.6 is below 9\.8\.7 \(the version before this push\)"
    ):
        decide("9.8.7", "9.8.6", {}, H)


def test_decide_down_from_tag_errors():
    with pytest.raises(ReleaseError, match=r"below 9\.9\.0 \(tag v9\.9\.0\)"):
        decide("9.9.0.dev0", "9.8.8", {"v9.9.0": O}, H)


def test_decide_down_both_names_tag():
    with pytest.raises(ReleaseError, match=r"\(tag v9\.9\.0\)"):
        decide("9.9.1", "9.8.8", {"v9.9.0": O}, H)


def test_decide_compares_numerically():
    assert decide("9.8.9", "9.8.10", {"v9.8.9": O}, H) == Decision("9.8.10", True, True)


def test_decide_ignores_non_final_tags_for_floor():
    assert decide("9.8.7", "9.8.8", {"v9.9.0rc1": O}, H) == Decision("9.8.8", True, True)


def test_decide_missing_version_errors():
    with pytest.raises(ReleaseError, match=r"no project\.version.*#68"):
        decide("9.8.7", None, {}, H)


def test_release_exists_true():
    assert release_exists([{"tagName": "v9.8.8"}], "9.8.8")


def test_release_exists_false():
    assert not release_exists([{"tagName": "v9.8.7"}], "9.8.8")


def test_release_exists_counts_drafts():
    assert release_exists([{"tagName": "v9.8.8", "isDraft": True}], "9.8.8")


def _pull(number, merged_at="2026-01-01T00:00:00Z", base="main", body=""):
    return {"number": number, "merged_at": merged_at, "base": {"ref": base}, "body": body}


def test_release_pull_picks_the_merged_main_pr():
    pulls = [_pull(7), _pull(8, merged_at=None), _pull(9, base="dev")]
    assert release_pull(pulls, H)["number"] == 7


def test_release_pull_none_errors():
    with pytest.raises(
        ReleaseError, match=r"no merged pull request into main found for .*RELEASING\.md step 5"
    ):
        release_pull([_pull(8, merged_at=None)], H)


def test_release_pull_several_errors():
    with pytest.raises(ReleaseError, match=r"#7, #8"):
        release_pull([_pull(7), _pull(8)], H)


BODY = ["## Summary", "x", "## Release notes", "### Fixes", "- thing (#9)", "## Testing", "y"]


def test_notes_extracts_section():
    out = release_notes("\n".join(BODY), "9.8.8", 12)
    assert out.startswith("### Fixes\n- thing (#9)")
    assert "Testing" not in out
    assert out.endswith(INSTALL_BLOCK.format(version="9.8.8"))


def test_install_block_matches_readme_install_line():
    assert INSTALL_RE.findall(INSTALL_BLOCK.format(version="9.8.8")) == ["9.8.8"]


def test_notes_crlf_body():
    out = release_notes("\r\n".join(BODY), "9.8.8", 12)
    assert out == release_notes("\n".join(BODY), "9.8.8", 12)
    assert "\r" not in out


def test_notes_fence_and_subheads_kept():
    body = "\n".join(
        ["## Release notes", "### New", "```bash", "## not a heading", "```", "- done", "## End"]
    )
    out = release_notes(body, "9.8.8", 12)
    assert "### New" in out
    assert "## not a heading" in out
    assert "- done" in out


def test_notes_inline_triple_backticks_open_no_fence():
    body = "\n".join(["## Release notes", "```rv2 build``` is faster", "## Testing", "- internal"])
    out = release_notes(body, "9.8.8", 12)
    assert out.startswith("```rv2 build``` is faster\n\nInstall:")
    assert "internal" not in out


def test_notes_tilde_inside_backtick_fence_kept():
    body = "\n".join(["## Release notes", "```", "~~~", "## still code", "```", "- after", "## End"])
    out = release_notes(body, "9.8.8", 12)
    assert "~~~\n## still code" in out
    assert "- after" in out


def test_notes_heading_inside_earlier_fence_ignored():
    body = "\n".join(
        ["```markdown", "## Release notes", "- template", "```", "## Release notes", "- real"]
    )
    out = release_notes(body, "9.8.8", 12)
    assert out.startswith("- real\n")
    assert "template" not in out


def test_notes_ends_at_h1():
    out = release_notes("\n".join(["## Release notes", "- real", "# Appendix", "z"]), "9.8.8", 12)
    assert out.startswith("- real\n")
    assert "Appendix" not in out


def test_notes_heading_case_and_spacing():
    assert release_notes("##  Release Notes  \n- real", "9.8.8", 12).startswith("- real\n")


MISSING = (
    r"PR #12 has no '## Release notes' section; add one to its description and re-run this job"
)


def test_notes_missing_section_errors():
    with pytest.raises(ReleaseError, match=MISSING):
        release_notes("## Summary\nx", "9.8.8", 12)


def test_notes_empty_section_errors():
    with pytest.raises(ReleaseError, match=MISSING):
        release_notes("## Release notes\n\n  \n## Testing\ny", "9.8.8", 12)


def test_notes_null_body_errors():
    with pytest.raises(ReleaseError, match=MISSING):
        release_notes(None, "9.8.8", 12)


def _git(*args: str) -> str:
    cmd = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args]
    return subprocess.run(cmd, check=True, capture_output=True, encoding="utf-8").stdout.strip()


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """A repo with commit A at 9.8.7 (annotated tag v9.8.7) and commit B bumping to 9.8.8."""
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.chdir(root)
    _git("init", "-q", "-b", "main")
    pyproject = root / "pyproject.toml"
    pyproject.write_text('[project]\nversion = "9.8.7"\n', encoding="utf-8", newline="\n")
    _git("add", "pyproject.toml")
    _git("commit", "-q", "-m", "A")
    a = _git("rev-parse", "HEAD")
    _git("tag", "-a", "v9.8.7", "-m", "v9.8.7")
    pyproject.write_text('[project]\nversion = "9.8.8"\n', encoding="utf-8", newline="\n")
    _git("commit", "-q", "-am", "B")
    b = _git("rev-parse", "HEAD")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
    return a, b


def _out(tmp_path) -> str:
    return (tmp_path / "out").read_text(encoding="utf-8")


def test_cli_decide_bump_writes_outputs(git_repo, tmp_path):
    a, b = git_repo
    assert main(["decide", "--before", a, "--after", b]) == 0
    assert _out(tmp_path) == "version=9.8.8\ntag=true\nrelease=true\n"


def test_cli_decide_peels_annotated_tags(git_repo, tmp_path):
    a, b = git_repo
    _git("tag", "-a", "v9.8.8", "-m", "v9.8.8", b)
    assert main(["decide", "--before", a, "--after", b]) == 0
    assert _out(tmp_path) == "version=9.8.8\ntag=false\nrelease=true\n"


def test_cli_decide_without_github_output_prints(git_repo, monkeypatch, capsys):
    a, b = git_repo
    monkeypatch.delenv("GITHUB_OUTPUT")
    assert main(["decide", "--before", a, "--after", b]) == 0
    assert capsys.readouterr().out == "version=9.8.8\ntag=true\nrelease=true\n"


def test_cli_unknown_before_fails_loudly(git_repo, tmp_path, capsys):
    _, b = git_repo
    assert main(["decide", "--before", "0" * 40, "--after", b]) == 1
    first = capsys.readouterr().err.splitlines()[0]
    assert first.startswith("::error::cannot read pyproject.toml at 0000")
    assert "RELEASING.md steps 4-5" in first
    assert not (tmp_path / "out").exists()


def test_cli_exists_writes_output(git_repo, tmp_path):
    releases = tmp_path / "releases.json"
    releases.write_text(json.dumps([{"tagName": "v9.8.8"}]), encoding="utf-8")
    assert main(["exists", "--version", "9.8.8", "--releases", str(releases)]) == 0
    assert _out(tmp_path) == "exists=true\n"


def _pulls_file(tmp_path, body: str):
    pulls = tmp_path / "pulls.json"
    pulls.write_text(json.dumps([_pull(12, body=body)]), encoding="utf-8")
    return str(pulls)


def test_cli_notes_prints_notes(tmp_path, capsys):
    pulls = _pulls_file(tmp_path, "## Release notes\r\n- thing (#9)\r\n")
    assert main(["notes", "--version", "9.8.8", "--sha", H, "--pulls", pulls]) == 0
    out = capsys.readouterr().out
    assert out.startswith("- thing (#9)\n")
    assert '@v9.8.8"' in out


def test_cli_notes_error_goes_to_stderr(tmp_path, capsys):
    pulls = _pulls_file(tmp_path, "## Summary\nx")
    assert main(["notes", "--version", "9.8.8", "--sha", H, "--pulls", pulls]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("::error::PR #12 has no '## Release notes' section")
    assert captured.out == ""


def test_annotation_escapes_newlines():
    assert annotation("a\nb%c\r\n") == "::error::a%0Ab%25c"


def test_cli_decide_resolves_a_short_after_sha(git_repo, tmp_path):
    a, b = git_repo
    _git("tag", "-a", "v9.8.8", "-m", "v9.8.8", b)
    assert main(["decide", "--before", a[:7], "--after", b[:7]]) == 0
    assert _out(tmp_path) == "version=9.8.8\ntag=false\nrelease=true\n"


WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _needs(job: dict) -> list[str]:
    needs = job.get("needs", [])
    return [needs] if isinstance(needs, str) else list(needs)


def _needs_closure(jobs: dict, name: str) -> set[str]:
    """Every job that `name` waits on, directly or through another job."""
    seen: set[str] = set()
    todo = _needs(jobs[name])
    while todo:
        n = todo.pop()
        if n not in seen:
            seen.add(n)
            todo.extend(_needs(jobs[n]))
    return seen


def _upstream(jobs: dict) -> set[str]:
    """The jobs that release must wait on: all but those that themselves wait on release."""
    return {n for n in jobs if n != "release" and "release" not in _needs_closure(jobs, n)}


def _release_runs() -> list[str]:
    return [step["run"] for step in _workflow()["jobs"]["release"]["steps"] if "run" in step]


def test_release_job_runs_only_for_pushes_to_main_here():
    condition = _workflow()["jobs"]["release"]["if"]
    assert "github.event_name == 'push'" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    assert "github.repository == 'mtibbits/reVision'" in condition
    assert condition.count(" && ") == 2
    assert "||" not in condition


def test_release_job_needs_every_other_job():
    jobs = _workflow()["jobs"]
    assert set(_needs(jobs["release"])) == _upstream(jobs)


def test_needs_rule_allows_a_downstream_job():
    jobs = dict(_workflow()["jobs"], publish={"needs": "release", "steps": []})
    assert _upstream(jobs) == {"test", "browsers"}


def test_only_release_job_can_write():
    workflow = _workflow()
    assert workflow["permissions"] == {"contents": "read"}
    jobs = workflow["jobs"]
    assert jobs["release"]["permissions"] == {"contents": "write", "pull-requests": "read"}
    assert [n for n in jobs if n != "release" and "permissions" in jobs[n]] == []


def test_release_job_interpolates_nothing_into_shell():
    runs = _release_runs()
    assert runs
    assert [run for run in runs if "${{" in run] == []


def test_release_job_fetches_full_history():
    steps = _workflow()["jobs"]["release"]["steps"]
    checkout = next(s for s in steps if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["fetch-depth"] == 0


def test_release_job_tag_message_and_title():
    runs = _release_runs()
    tag = next(run for run in runs if "git" in run and " tag -a " in run)
    create = next(run for run in runs if "gh release create" in run)
    assert '-m "reVision engine v$VERSION"' in tag
    assert '--title "reVision engine v$VERSION"' in create
    assert "--verify-tag" in create
    assert [run for run in runs if "--force" in run or " -f " in run] == []


@pytest.mark.parametrize("heading", [" ## Testing", "   # Testing", "##\tTesting", "##"])
def test_notes_ends_at_any_level_one_or_two_heading(heading):
    out = release_notes("\n".join(["## Release notes", "- real", heading, "- internal"]), "9.8.8", 12)
    assert out.startswith("- real\n\nInstall:")
    assert "internal" not in out
