"""xfail_browser: a strict xfail in the named browsers only, refused at collection when malformed."""

from __future__ import annotations

import sys

import pytest

from tests.browser.marks import browser_xfail, engine_platform
from tests.ci_pins import ROOT

pytest_plugins = ["pytester"]

CONFTEST = f'import sys\nsys.path.insert(0, {str(ROOT)!r})\npytest_plugins = ["tests.browser.marks"]\n'


def test_marks_only_the_named_browser():
    mark = browser_xfail(("webkit",), "x (#9)", "webkit", raises=AssertionError)
    assert mark is not None
    assert mark.mark.name == "xfail"
    assert mark.mark.kwargs == {"strict": True, "reason": "x (#9)", "raises": AssertionError}
    assert browser_xfail(("webkit",), "x (#9)", "firefox", raises=AssertionError) is None
    assert browser_xfail(("webkit",), "x (#9)", "chromium", raises=AssertionError) is None


def test_platforms_narrow_the_mark_to_those_platforms():
    def mark(platform):
        return browser_xfail(("webkit",), "x (#9)", "webkit", platforms=("win32",), platform=platform)

    assert mark("win32") is not None
    assert mark("linux") is None
    assert mark("darwin") is None
    assert browser_xfail(("webkit",), "x (#9)", "firefox", platforms=("win32",), platform="win32") is None


@pytest.mark.parametrize(
    ("platforms", "msg"),
    [
        (("windows",), "unknown platform 'windows'; expected one of darwin, linux, win32"),
        ((), "platforms names no platform"),
        ("win32", "platforms must be a tuple of platform names"),
    ],
)
def test_platform_refusals(platforms, msg):
    with pytest.raises(ValueError) as e:
        browser_xfail(("webkit",), "x (#9)", "chromium", platforms=platforms)
    assert str(e.value) == msg


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


@pytest.mark.parametrize("raises", ["AssertionError", int, (AssertionError, "x")])
def test_raises_refusals(raises):
    with pytest.raises(ValueError) as e:
        browser_xfail(("webkit",), "x (#9)", "chromium", raises=raises)
    assert str(e.value) == "raises must be an exception type or a tuple of them"


def test_raises_accepts_a_tuple_of_exceptions():
    mark = browser_xfail(("webkit",), "x (#9)", "webkit", raises=(AssertionError, TimeoutError))
    assert mark.mark.kwargs["raises"] == (AssertionError, TimeoutError)


def test_engine_platform_counts_webkit_wsl_as_linux(monkeypatch):
    # Pretend to be Windows, so the channel rule bites on a Linux host too.
    monkeypatch.setattr(sys, "platform", "win32")

    class Config:
        def __init__(self, channel):
            self.channel = channel

        def getoption(self, name, default=None):
            assert name == "--browser-channel"
            return self.channel

    assert engine_platform(Config("webkit-wsl")) == "linux"
    assert engine_platform(Config(None)) == "win32"
    assert engine_platform(Config("msedge")) == "win32"


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


@pytest.mark.parametrize(("here", "xfailed"), [(True, 1), (False, 0)])
def test_hook_marks_only_on_the_named_platforms(pytester, here, xfailed):
    other = "linux" if sys.platform != "linux" else "win32"
    platform = sys.platform if here else other
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(
        f"""
        import pytest

        @pytest.mark.xfail_browser("webkit", platforms=({platform!r},), reason="r (#9)")
        def test_x(browser_name):
            assert browser_name == "chromium" or not {here!r}
        """
    )
    result = pytester.runpytest_subprocess("-rxX", "--browser", "chromium", "--browser", "webkit")
    result.assert_outcomes(passed=2 - xfailed, xfailed=xfailed)


def test_webkit_wsl_channel_counts_as_linux(pytester):
    # Playwright's webkit-wsl channel runs the Linux WebKit build from a Windows host.
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.xfail_browser("webkit", platforms=("linux",), reason="r (#9)")
        def test_x(browser_name):
            assert False
        """
    )
    result = pytester.runpytest_subprocess("-rxX", "--browser", "webkit", "--browser-channel", "webkit-wsl")
    result.assert_outcomes(xfailed=1)


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
