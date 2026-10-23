"""tools/release.py decides when CI tags and releases a version bump, and finds its notes.

Fixture versions use the implausible 9.8.x family, so this file never carries the engine's
version (tests/test_release_doc.py).
"""

from __future__ import annotations

import pytest

from tools.release import (
    INSTALL_BLOCK,
    NOTHING,
    Decision,
    ReleaseError,
    decide,
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
