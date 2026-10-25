"""CI's constraints file pins every package whose output the golden test hashes.

The static tests run everywhere. The two runtime tests run only under RV_REQUIRE_GOLDEN=1
(CI), so a contributor who has not installed CI's pins stays green.
"""

from __future__ import annotations

import ast
import os
import shlex
from importlib.metadata import PackageNotFoundError

import pytest
import yaml

from tests.ci_pins import (
    CONSTRAINTS,
    INSTALL_CMD,
    ROOT,
    pin_mismatches,
    read_pins,
    runtime_closure,
    runtime_dependencies,
)
from tests.require_golden import REQUIRED_FILE

CI_ONLY = pytest.mark.skipif(
    os.environ.get("RV_REQUIRE_GOLDEN") != "1",
    reason="CI-only (RV_REQUIRE_GOLDEN=1 unset); to match CI locally: " + INSTALL_CMD,
)
TEST_WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
DEMO_WORKFLOW = ROOT / ".github" / "workflows" / "demo.yml"
SEPARATORS = {"&&", "||", ";", "|", "|&"}


def test_pins_cover_the_runtime_dependencies():
    missing = sorted(runtime_dependencies() - set(read_pins()))
    assert not missing, f"runtime dependencies not pinned in {CONSTRAINTS.name}: {missing}"


def test_read_pins_parses_and_rejects(tmp_path):
    good = tmp_path / "good.txt"
    good.write_text("# header\n\njinja2==3.1\npygments==2.21.0\n", encoding="utf-8")
    assert read_pins(good) == {"jinja2": "3.1", "pygments": "2.21.0"}
    bom = tmp_path / "bom.txt"
    bom.write_text("\ufeffjinja2==3.1\n", encoding="utf-8")
    assert read_pins(bom) == {"jinja2": "3.1"}

    cases = [
        ("pygments>=2.21\n", "expected name==version"),
        ("Pygments==2.21.0\n", "write the name as pygments"),
        ("pygments==2.21.0\npygments==2.21.0\n", "duplicate pin"),
        ("pygments==2.21.*\n", "invalid version"),
    ]
    for i, (text, msg) in enumerate(cases):
        bad = tmp_path / f"bad{i}.txt"
        bad.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError, match=msg):
            read_pins(bad)


def test_pin_mismatches_reports_installed_and_missing():
    pins = {"a": "1.0", "b": "2.0", "c": "3.1"}
    installed = {"a": "1.0", "b": "2.1", "c": "3.1.0"}
    assert pin_mismatches(pins, installed.__getitem__) == ["b 2.1 installed, CI pins 2.0"]

    def version(name: str) -> str:
        if name == "a":
            raise PackageNotFoundError(name)
        return installed[name]

    assert pin_mismatches(pins, version)[0] == "a not installed, CI pins 1.0"


def _commands(run: str) -> list[list[str]]:
    """Split a workflow `run` string into commands, each a list of shell tokens."""
    commands: list[list[str]] = []
    for line in run.splitlines():
        lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        current: list[str] = []
        for token in lexer:
            if token in SEPARATORS:
                commands.append(current)
                current = []
            else:
                current.append(token)
        commands.append(current)
    return [c for c in commands if c]


def _has_adjacent(tokens: list[str], first: str, second: str) -> bool:
    return any(a == first and b == second for a, b in zip(tokens, tokens[1:]))


def test_test_workflow_installs_with_the_constraints():
    workflow = yaml.safe_load(TEST_WORKFLOW.read_text(encoding="utf-8"))
    installs = [
        tokens
        for job in workflow["jobs"].values()
        for step in job["steps"]
        for tokens in _commands(step.get("run", ""))
        if _has_adjacent(tokens, "pip", "install")
    ]
    assert installs, f"no pip install command found in {TEST_WORKFLOW.name}"
    for tokens in installs:
        assert _has_adjacent(tokens, "-c", CONSTRAINTS.name), (
            f"{TEST_WORKFLOW.name}: {shlex.join(tokens)!r} does not pass -c {CONSTRAINTS.name}"
        )


def test_browser_tests_run_in_every_engine():
    workflow = yaml.safe_load(TEST_WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    engines: set[str] = set()
    for job in jobs.values():
        for step in job["steps"]:
            for tokens in _commands(step.get("run", "")):
                for i, flag in enumerate(tokens[:-1]):
                    if flag != "--browser":
                        continue
                    if tokens[i + 1 : i + 4] == ["${{", "matrix.browser", "}}"]:
                        engines.update(job["strategy"]["matrix"]["browser"])
                    elif not tokens[i + 1].startswith("${{"):
                        engines.add(tokens[i + 1])
    assert engines == {"chromium", "firefox", "webkit"}
    # The golden gate stays on the required `test` job, which stays one un-matrixed check.
    assert jobs["test"]["env"]["RV_REQUIRE_GOLDEN"] == "1"
    assert "strategy" not in jobs["test"]
    others = [job for name, job in jobs.items() if name != "test"]
    envs = [workflow.get("env")] + [e for job in others for e in [job.get("env"), *(s.get("env") for s in job["steps"])]]
    for env in envs:
        assert "RV_REQUIRE_GOLDEN" not in (env or {})


def test_demo_workflow_checks_before_building():
    workflow = yaml.safe_load(DEMO_WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["build"]
    steps = job["steps"]
    name = DEMO_WORKFLOW.name
    cmds = [_commands(step.get("run", "")) for step in steps]
    checks = [i for i, cs in enumerate(cmds) if any(c[:2] == ["rv2", "check"] and "--strict" in c for c in cs)]
    builds = [i for i, cs in enumerate(cmds) if any(c[:2] == ["rv2", "build"] for c in cs)]
    assert len(checks) == 1, f"{name}: expected exactly one `rv2 check --strict` step, found {len(checks)}"
    assert len(builds) == 1, f"{name}: expected exactly one `rv2 build` step, found {len(builds)}"
    [check_i], [build_i] = checks, builds
    # One command only, so `|| true`, `| tee` or `;` cannot swallow the check's exit status.
    assert len(cmds[check_i]) == 1, f"{name}: the check step must run one command, not {cmds[check_i]}"
    assert check_i < build_i, f"{name}: the strict check must run before rv2 build"
    assert "continue-on-error" not in steps[check_i], f"{name}: the check step must not continue on error"
    assert "if" not in steps[check_i], f"{name}: the check step must not be conditional"
    assert "continue-on-error" not in job, f"{name}: the build job must not continue on error"
    build_cmd = next(c for c in cmds[build_i] if c[:2] == ["rv2", "build"])
    for tokens in (cmds[check_i][0], build_cmd):
        assert _has_adjacent(tokens, "--root", "examples/minimal"), f"{name}: the check must gate the root that is built"


def test_install_command_is_documented_verbatim():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # Every home of the command, so one stale copy cannot hide behind a correct one.
    # Keyed on the install target, not the flags, so `-U -e` or `--editable` cannot slip by.
    homes = [line for line in readme.splitlines() if '".[dev]"' in line]
    assert homes, 'README.md has no `".[dev]"` install command'
    stale = [line for line in homes if INSTALL_CMD not in line]
    assert not stale, f"README.md lines without INSTALL_CMD verbatim: {stale}"
    # Parsed, not imported, so test_golden.py is not collected twice.
    golden = ast.parse((ROOT / REQUIRED_FILE).read_text(encoding="utf-8"))
    assert INSTALL_CMD in (ast.get_docstring(golden) or ""), (
        f"{REQUIRED_FILE}'s docstring does not carry INSTALL_CMD verbatim"
    )


@CI_ONLY
def test_installed_versions_match_the_pins():
    assert pin_mismatches() == []


@CI_ONLY
def test_installed_closure_equals_the_pins():
    closure, pinned = runtime_closure(), set(read_pins())
    assert closure == pinned, (
        f"installed but not pinned: {sorted(closure - pinned)}; "
        f"pinned but not in the runtime closure: {sorted(pinned - closure)}"
    )
