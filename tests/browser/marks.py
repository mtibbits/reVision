"""xfail_browser: a strict xfail in the named browsers only, naming the issue that tracks the failure."""

from __future__ import annotations

import re

import pytest

ENGINES = ("chromium", "firefox", "webkit")
ISSUE = re.compile(r"#\d+")


def browser_xfail(names, reason, browser, raises=None):
    """The strict xfail mark for browser when names include it, else None; a malformed mark raises ValueError.

    Validation comes first, so a bad mark is refused in every leg, not only the named ones."""
    if not isinstance(reason, str):
        raise ValueError('needs reason="... (#N)" as a keyword')
    for name in names:
        if name not in ENGINES:
            raise ValueError(f"unknown browser {name!r}; expected one of {', '.join(ENGINES)}")
    if not names:
        raise ValueError("names no browser")
    if set(names) == set(ENGINES):
        raise ValueError("marks every engine; fix or skip the test instead")
    if not ISSUE.search(reason):
        raise ValueError("reason must name its tracking issue as #N")
    if browser not in names:
        return None
    kwargs = {"strict": True, "reason": reason}
    if raises is not None:
        kwargs["raises"] = raises
    return pytest.mark.xfail(**kwargs)


def apply_browser_marks(items) -> None:
    """Turn each item's xfail_browser marker into a strict xfail for its own browser leg; refuse malformed marks."""
    for item in items:
        for m in item.iter_markers("xfail_browser"):
            callspec = getattr(item, "callspec", None)
            try:
                if callspec is None or "browser_name" not in callspec.params:
                    raise ValueError("the test takes no browser")
                mark = browser_xfail(m.args, m.kwargs.get("reason"), callspec.params["browser_name"], m.kwargs.get("raises"))
            except ValueError as e:
                raise pytest.UsageError(f"xfail_browser on {item.nodeid}: {e}") from None
            if mark is not None:
                item.add_marker(mark)
