"""xfail_browser: a strict xfail in the named browsers only, refused at collection when malformed."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.browser.marks import browser_xfail

pytest_plugins = ["pytester"]

ROOT = Path(__file__).resolve().parents[1]

CONFTEST = f"""
import sys
sys.path.insert(0, {str(ROOT)!r})
from tests.browser.marks import apply_browser_marks

def pytest_configure(config):
    config.addinivalue_line("markers", "xfail_browser(*names, reason, raises=None): strict xfail")

def pytest_collection_modifyitems(items):
    apply_browser_marks(items)
"""


def test_marks_only_the_named_browser():
    mark = browser_xfail(("webkit",), "x (#9)", "webkit", raises=AssertionError)
    assert mark is not None
    assert mark.mark.name == "xfail"
    assert mark.mark.kwargs == {"strict": True, "reason": "x (#9)", "raises": AssertionError}
    assert browser_xfail(("webkit",), "x (#9)", "firefox", raises=AssertionError) is None
    assert browser_xfail(("webkit",), "x (#9)", "chromium", raises=AssertionError) is None


@pytest.mark.parametrize(
    ("names", "reason", "msg"),
    [
        (("safari",), "x (#9)", "unknown browser 'safari'; expected one of chromium, firefox, webkit"),
        ((), "x (#9)", "names no browser"),
        (("chromium", "firefox", "webkit"), "x (#9)", "marks every engine; fix or skip the test instead"),
        (("webkit",), None, 'needs reason="... (#N)" as a keyword'),
        (("webkit",), "no issue", "reason must name its tracking issue as #N"),
    ],
)
def test_refusals(names, reason, msg):
    with pytest.raises(ValueError) as e:
        browser_xfail(names, reason, "chromium")
    assert str(e.value) == msg


def test_hook_marks_only_that_browser_leg(pytester):
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.xfail_browser("webkit", reason="r (#9)")
        def test_x(browser_name):
            assert browser_name == "chromium"
        """
    )
    # pytest-playwright parametrizes browser_name from --browser; requesting it launches no browser.
    result = pytester.runpytest_subprocess("-rxX", "--browser", "chromium", "--browser", "webkit")
    result.assert_outcomes(passed=1, xfailed=1)


@pytest.mark.parametrize(
    ("mark", "args", "msg"),
    [
        ('xfail_browser(reason="r (#9)")', "browser_name", "names no browser"),
        ('xfail_browser("webkit", "r (#9)")', "browser_name", 'needs reason="... (#N)" as a keyword'),
        ('xfail_browser("webkit", reason="r (#9)")', "", "the test takes no browser"),
    ],
)
def test_hook_refuses(pytester, mark, args, msg):
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(f"import pytest\n\n@pytest.mark.{mark}\ndef test_x({args}):\n    pass\n")
    result = pytester.runpytest_subprocess("--browser", "chromium")
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    err = result.stderr.str()
    assert "xfail_browser on " in err
    assert msg in err
