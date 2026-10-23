"""tools/release.py decides when CI tags and releases a version bump, and finds its notes.

Fixture versions use the implausible 9.8.x family, so this file never carries the engine's
version (tests/test_release_doc.py).
"""

from __future__ import annotations

import pytest

from tools.release import NOTHING, Decision, ReleaseError, decide

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
