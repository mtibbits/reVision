"""RV_REQUIRE_GOLDEN=1: fail the session unless the golden test ran and passed exactly once.

CI sets it job-wide, so a skipped golden test fails the job instead of passing it silently.
Only the value "1" enables it. The gate counts passed call-phase reports for one exact
nodeid rather than looking for a skip, because a skip, a module-level skip, a deselect, a
rename or a deletion all mean the same thing: the test did not pass. An xfail or xpass is
not a pass either.

tests/conftest.py loads it through pytest_plugins, and tests/test_require_golden.py loads
this same module into inner pytester sessions, so the suite and its test share one predicate.
Each session gets its own _GoldenGate, so inner sessions do not mix with the outer one.
"""

from __future__ import annotations

import os

import pytest

REQUIRED_FILE = "tests/test_golden.py"
REQUIRED = f"{REQUIRED_FILE}::test_minimal_matches_golden"


class _GoldenGate:
    def __init__(self) -> None:
        self.observed: list[str] = []

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        if report.nodeid == REQUIRED_FILE and report.outcome != "passed":
            self.observed.append(f"collect {report.outcome}")

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.nodeid != REQUIRED:
            return
        outcome = "xfail/xpass" if hasattr(report, "wasxfail") else report.outcome
        self.observed.append(f"{report.when} {outcome}")

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        if self.observed.count("call passed") == 1:
            return
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        seen = ", ".join(self.observed) or "not run"
        msg = f"RV_REQUIRE_GOLDEN=1: {REQUIRED} must run and pass exactly once; observed: {seen}"
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_line(msg, red=True)
        else:
            session.config.get_terminal_writer().line(msg, red=True)


def pytest_configure(config: pytest.Config) -> None:
    if os.environ.get("RV_REQUIRE_GOLDEN") == "1":
        config.pluginmanager.register(_GoldenGate(), "rv-require-golden")
