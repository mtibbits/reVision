"""tools/release.py decides when CI tags and releases a version bump, and finds its notes.

Fixture versions use the implausible 9.8.x family, so this file never carries the engine's
version (tests/test_release_doc.py).
"""

from __future__ import annotations

import io
import json
import subprocess
import tarfile
import zipfile

import pytest
import yaml

from tests.ci_pins import ROOT
from tests.test_ci_constraints import _tokens
from tests.test_release_doc import INSTALL_RE
from tools.release import (
    INSTALL_BLOCK,
    NOTHING,
    Decision,
    ReleaseError,
    annotation,
    check_dist,
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


def test_cli_decide_unchanged_emits_nothing(git_repo, tmp_path):
    _, b = git_repo
    (tmp_path / "repo" / "other.txt").write_text("x\n", encoding="utf-8")
    _git("add", "other.txt")
    _git("commit", "-q", "-m", "C")
    c = _git("rev-parse", "HEAD")
    assert main(["decide", "--before", b, "--after", c]) == 0
    assert _out(tmp_path) == "version=\ntag=false\nrelease=false\n"


def test_cli_decide_after_not_a_commit_fails_loudly(git_repo, tmp_path, capsys):
    a, b = git_repo
    tree = _git("rev-parse", f"{b}^{{tree}}")
    assert main(["decide", "--before", a, "--after", tree]) == 1
    assert capsys.readouterr().err.startswith(f"::error::cannot resolve {tree} to a commit")
    assert not (tmp_path / "out").exists()


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


WHEEL = "revision_engine-{v}-py3-none-any.whl"
SDIST = "revision_engine-{v}.tar.gz"


def _metadata(name: str, version: str) -> bytes:
    # A non-ASCII description, as README makes it, so the reader must decode UTF-8.
    head = f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n"
    return (head + "\nreVision — docs\n").encode()


def _dist(
    tmp_path,
    version,
    *,
    meta_version=None,
    name="revision-engine",
    extra=(),
    wheel_meta=None,
    sdist_meta=None,
):
    """A dist/ directory holding a minimal wheel and sdist built for `version`."""
    d = tmp_path / "dist"
    d.mkdir()
    meta = _metadata(name, meta_version or version)
    with zipfile.ZipFile(d / WHEEL.format(v=version), "w") as z:
        if wheel_meta is not False:
            z.writestr(f"revision_engine-{version}.dist-info/METADATA", wheel_meta or meta)
    with tarfile.open(d / SDIST.format(v=version), "w:gz") as t:
        data = sdist_meta or meta
        info = tarfile.TarInfo(f"revision_engine-{version}/PKG-INFO")
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))
    for e in extra:
        (d / e).write_bytes(b"")
    return d


def test_check_dist_accepts_matching_files(tmp_path):
    d = _dist(tmp_path, "9.8.8")
    assert check_dist(str(d), "9.8.8") == [WHEEL.format(v="9.8.8"), SDIST.format(v="9.8.8")]


@pytest.mark.parametrize("version", ["9.8.8.dev0", "9.8.8+gabc1234", "9.8.8rc1", "9.8"])
def test_check_dist_rejects_non_final(tmp_path, version):
    d = _dist(tmp_path, version)
    with pytest.raises(ReleaseError, match="not a final release version"):
        check_dist(str(d), version)


@pytest.mark.parametrize("built", ["9.8.8.dev0", "9.8.8+gabc1234"])
def test_check_dist_rejects_non_final_build(tmp_path, built):
    d = _dist(tmp_path, built)
    with pytest.raises(ReleaseError, match=r"the build is not version 9\.8\.8"):
        check_dist(str(d), "9.8.8")


def test_check_dist_rejects_another_version(tmp_path):
    d = _dist(tmp_path, "9.8.7")
    with pytest.raises(ReleaseError, match=r"the build is not version 9\.8\.8") as e:
        check_dist(str(d), "9.8.8")
    assert "revision_engine-9.8.7" in str(e.value)


def test_check_dist_rejects_extra_file(tmp_path):
    d = _dist(tmp_path, "9.8.8", extra=("revision_engine-9.8.8-py3-none-any.whl.asc",))
    with pytest.raises(ReleaseError, match="expected"):
        check_dist(str(d), "9.8.8")


def test_check_dist_rejects_missing_sdist(tmp_path):
    d = _dist(tmp_path, "9.8.8")
    (d / SDIST.format(v="9.8.8")).unlink()
    with pytest.raises(ReleaseError, match="expected"):
        check_dist(str(d), "9.8.8")


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_check_dist_rejects_metadata_version(tmp_path, kind):
    wrong = _metadata("revision-engine", "9.8.7")
    d = _dist(tmp_path, "9.8.8", **{f"{kind}_meta": wrong})
    with pytest.raises(ReleaseError, match=r"declares Version '9\.8\.7', expected '9\.8\.8'"):
        check_dist(str(d), "9.8.8")


def test_check_dist_rejects_metadata_name(tmp_path):
    d = _dist(tmp_path, "9.8.8", name="revision-engine-x")
    with pytest.raises(ReleaseError, match="declares Name"):
        check_dist(str(d), "9.8.8")


def test_check_dist_rejects_missing_member(tmp_path):
    d = _dist(tmp_path, "9.8.8", wheel_meta=False)
    with pytest.raises(ReleaseError, match=r"has no revision_engine-9\.8\.8\.dist-info/METADATA"):
        check_dist(str(d), "9.8.8")


def test_cli_dist_ok(tmp_path, capsys):
    d = _dist(tmp_path, "9.8.8")
    assert main(["dist", "--version", "9.8.8", "--dir", str(d)]) == 0
    assert capsys.readouterr().out == (
        "checked revision_engine-9.8.8-py3-none-any.whl\nchecked revision_engine-9.8.8.tar.gz\n"
    )


def test_cli_dist_error_goes_to_stderr(tmp_path, capsys):
    d = _dist(tmp_path, "9.8.7")
    assert main(["dist", "--version", "9.8.8", "--dir", str(d)]) == 1
    assert capsys.readouterr().err.startswith("::error::")


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


def test_only_release_and_upload_jobs_hold_permissions():
    workflow = _workflow()
    assert workflow["permissions"] == {"contents": "read"}
    jobs = workflow["jobs"]
    assert jobs["release"]["permissions"] == {"contents": "write", "pull-requests": "read"}
    assert jobs["testpypi"]["permissions"] == {"id-token": "write"}
    assert jobs["pypi"]["permissions"] == {"id-token": "write"}
    assert {n for n in jobs if "permissions" in jobs[n]} == {"release", "testpypi", "pypi"}


def _runs(job: dict) -> list[str]:
    return [step["run"] for step in job["steps"] if "run" in step]


def test_release_path_interpolates_nothing_into_shell():
    jobs = _workflow()["jobs"]
    path = ["release"] + [n for n in jobs if "release" in _needs_closure(jobs, n)]
    for name in ("release", "dist", "smoke"):
        assert name in path and _runs(jobs[name]), name
    assert [(n, run) for n in path for run in _runs(jobs[n]) if "${{" in run] == []


VERSION_OUT = "${{ needs.release.outputs.version }}"
UPLOAD_JOBS = ["dist", "testpypi", "smoke", "pypi"]


def _step(job: dict, prefix: str) -> dict:
    return next(s for s in job["steps"] if s.get("uses", "").startswith(prefix))


def test_release_job_outputs_the_version():
    assert _workflow()["jobs"]["release"]["outputs"] == {
        "version": "${{ steps.decide.outputs.version }}"
    }


def test_upload_chain_order():
    jobs = _workflow()["jobs"]
    assert _needs(jobs["dist"]) == ["release"]
    assert _needs(jobs["testpypi"]) == ["dist"]
    assert set(_needs(jobs["smoke"])) == {"release", "testpypi"}
    assert len(_needs(jobs["smoke"])) == 2
    assert set(_needs(jobs["pypi"])) == {"release", "dist", "smoke"}
    assert len(_needs(jobs["pypi"])) == 3
    assert {"test", "browsers", "release", "dist", "testpypi", "smoke"} <= _needs_closure(
        jobs, "pypi"
    )
    assert [n for n in jobs if "pypi" in _needs_closure(jobs, n)] == []


def test_dist_runs_only_for_a_release_version():
    assert _workflow()["jobs"]["dist"]["if"] == "needs.release.outputs.version != ''"


def test_dist_builds_the_tag_and_checks_it():
    job = _workflow()["jobs"]["dist"]
    assert _step(job, "actions/checkout@")["with"]["ref"] == f"refs/tags/v{VERSION_OUT}"
    steps = job["steps"]
    build = next(i for i, s in enumerate(steps) if s.get("run") == "python -m build")
    check = next(
        i
        for i, s in enumerate(steps)
        if s.get("run") == 'python tools/release.py dist --version "$VERSION" --dir dist'
    )
    upload = next(
        i for i, s in enumerate(steps) if s.get("uses", "").startswith("actions/upload-artifact@")
    )
    assert build < check < upload
    assert steps[check]["env"] == {"VERSION": VERSION_OUT}


@pytest.mark.parametrize("name", ["testpypi", "pypi"])
def test_upload_jobs_run_no_repository_code(name):
    job = _workflow()["jobs"][name]
    # pypi's one run step is the digest check, which runs only coreutils.
    steps = [s for s in job["steps"] if not (name == "pypi" and s is _digest_check(job))]
    prefixes = [s["uses"].split("@")[0] + "@" for s in steps]
    assert prefixes == ["actions/download-artifact@", "pypa/gh-action-pypi-publish@"]
    assert [s for s in steps if "run" in s] == []
    assert job["environment"] == name
    publish = steps[1].get("with", {})
    assert "skip-existing" not in publish
    if name == "testpypi":
        assert publish == {"repository-url": "https://test.pypi.org/legacy/"}
    else:
        assert "repository-url" not in publish


def _digest_check(job: dict) -> dict:
    (step,) = [s for s in job["steps"] if "run" in s]
    return step


def test_pypi_publishes_only_the_files_dist_hashed():
    # smoke runs code from TestPyPI; the files pypi uploads must be the ones dist built.
    jobs = _workflow()["jobs"]
    dist = jobs["dist"]
    assert dist["outputs"] == {
        "wheel-sha256": "${{ steps.digests.outputs.wheel }}",
        "sdist-sha256": "${{ steps.digests.outputs.sdist }}",
    }
    ids = [s.get("id") for s in dist["steps"]]
    upload = next(
        i for i, s in enumerate(dist["steps"]) if s.get("uses", "").startswith("actions/upload")
    )
    assert ids.index("digests") < upload
    digests = dist["steps"][ids.index("digests")]
    assert "sha256sum" in digests["run"] and "GITHUB_OUTPUT" in digests["run"]
    steps = jobs["pypi"]["steps"]
    check = _digest_check(jobs["pypi"])
    assert check["env"] == {
        "VERSION": VERSION_OUT,
        "WHEEL_SHA256": "${{ needs.dist.outputs.wheel-sha256 }}",
        "SDIST_SHA256": "${{ needs.dist.outputs.sdist-sha256 }}",
    }
    tokens = _tokens(check["run"])
    assert {"sha256sum", "--strict", "-c"} <= set(tokens)
    assert "python" not in check["run"]
    order = [s.get("uses", "run").split("@")[0] for s in steps]
    assert order == ["actions/download-artifact", "run", "pypa/gh-action-pypi-publish"]


def test_jobs_running_third_party_code_drop_checkout_credentials():
    jobs = _workflow()["jobs"]
    for name in ("dist", "smoke"):
        assert _step(jobs[name], "actions/checkout@")["with"]["persist-credentials"] is False
    assert _step(jobs["dist"], "actions/upload-artifact@")["with"]["overwrite"] is True


def test_upload_jobs_run_on_linux():
    jobs = _workflow()["jobs"]
    assert {n: jobs[n]["runs-on"] for n in UPLOAD_JOBS} == dict.fromkeys(UPLOAD_JOBS, "ubuntu-24.04")


def test_smoke_installs_the_testpypi_build():
    job = _workflow()["jobs"]["smoke"]
    assert "permissions" not in job
    (run,) = _runs(job)
    tokens = _tokens(run)
    pairs = set(zip(tokens, tokens[1:]))
    assert ("--index-url", "https://test.pypi.org/simple/") in pairs
    assert ("--extra-index-url", "https://pypi.org/simple/") in pairs
    assert "revision-engine==$VERSION" in tokens
    assert '--version)" = "rv2 $VERSION"' in run


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
