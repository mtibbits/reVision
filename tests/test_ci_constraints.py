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
SEPARATORS = {"&&", "||", ";", "|"}


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
            run = step.get("run", "")
            for tokens in _commands(run):
                for flag, engine in zip(tokens, tokens[1:]):
                    if flag != "--browser":
                        continue
                    if not engine.startswith("${{"):
                        engines.add(engine)
                    elif "--browser ${{ matrix.browser }}" in run:
                        engines.update(job["strategy"]["matrix"]["browser"])
    assert engines == {"chromium", "firefox", "webkit"}
    # The golden gate stays on the required `test` job, which stays one un-matrixed check.
    browsers = jobs.get("browsers", {})
    for env in [workflow.get("env"), browsers.get("env"), *(s.get("env") for s in browsers.get("steps", []))]:
        assert "RV_REQUIRE_GOLDEN" not in (env or {})
    assert "test" in jobs
    assert "strategy" not in jobs["test"]


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
