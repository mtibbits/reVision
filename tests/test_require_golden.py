"""The RV_REQUIRE_GOLDEN gate, run against an inner pytest session.

Inner runs pass `-p no:playwright`: pytest-playwright errors inside a nested session.
The inner test file sits at tests/test_golden.py so its nodeid is the one the gate requires.
"""

import os

import pytest

GATE_CONFTEST = 'pytest_plugins = ["tests.require_golden"]\n'
SKIPS = "import pytest\n\ndef test_minimal_matches_golden():\n    pytest.skip('x')\n"
PASSES = "def test_minimal_matches_golden():\n    pass\n"
ABSENT = "def test_other():\n    pass\n"


def _run(pytester: pytest.Pytester, src: str) -> pytest.RunResult:
    pytester.makeconftest(GATE_CONFTEST)
    pytester.mkdir("tests")
    pytester.makepyfile(**{"tests/test_golden": src})
    return pytester.runpytest("-p", "no:playwright")


def test_gate_fails_when_golden_skips(pytester, monkeypatch):
    monkeypatch.setenv("RV_REQUIRE_GOLDEN", "1")
    r = _run(pytester, SKIPS)
    assert r.ret != 0
    out = r.stdout.str()
    assert "RV_REQUIRE_GOLDEN=1" in out and "test_minimal_matches_golden" in out


def test_gate_fails_when_golden_absent(pytester, monkeypatch):
    monkeypatch.setenv("RV_REQUIRE_GOLDEN", "1")
    r = _run(pytester, ABSENT)
    assert r.ret != 0
    lines = [ln for ln in r.outlines if ln.strip()]
    assert lines[-1].startswith("RV_REQUIRE_GOLDEN=1") and "observed: not run" in lines[-1]


def test_gate_is_wired_into_this_suite(pytestconfig):
    """tests/conftest.py loads the gate, and on GitHub Actions (CI=true) test.yml's env registers it."""
    assert pytestconfig.pluginmanager.has_plugin("tests.require_golden")
    if os.environ.get("CI") == "true":
        assert pytestconfig.pluginmanager.get_plugin("rv-require-golden") is not None


XPASSES = "import pytest\n\n@pytest.mark.xfail\ndef test_minimal_matches_golden():\n    pass\n"
MODULE_SKIP = "import pytest\n\npytest.skip('x', allow_module_level=True)\n\ndef test_minimal_matches_golden():\n    pass\n"
BROKEN = "import no_such_module_rv\n\ndef test_minimal_matches_golden():\n    pass\n"


@pytest.mark.parametrize(("src", "observed"), [(XPASSES, "call xfail/xpass"), (MODULE_SKIP, "collect skipped")])
def test_gate_fails_on_xpass_and_module_skip(pytester, monkeypatch, src, observed):
    monkeypatch.setenv("RV_REQUIRE_GOLDEN", "1")
    r = _run(pytester, src)
    assert r.ret == pytest.ExitCode.TESTS_FAILED
    out = r.stdout.str()
    assert "RV_REQUIRE_GOLDEN=1" in out and observed in out


def test_gate_keeps_a_more_specific_exit_code(pytester, monkeypatch):
    """A collection error already fails the run with its own code; the gate does not turn it into 1."""
    monkeypatch.setenv("RV_REQUIRE_GOLDEN", "1")
    r = _run(pytester, BROKEN)
    assert r.ret == pytest.ExitCode.INTERRUPTED


def test_gate_passes_when_golden_passes(pytester, monkeypatch):
    """CONTROL: the gate is not over-eager."""
    monkeypatch.setenv("RV_REQUIRE_GOLDEN", "1")
    r = _run(pytester, PASSES)
    assert r.ret == 0


def test_gate_is_inert_without_env(pytester, monkeypatch):
    """CONTROL: without the env (CI sets it job-wide, so delete it first) a skip stays a skip."""
    monkeypatch.delenv("RV_REQUIRE_GOLDEN", raising=False)
    r = _run(pytester, SKIPS)
    assert r.ret == 0
    r.assert_outcomes(skipped=1)
