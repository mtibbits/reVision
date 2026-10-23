"""Decide whether a push to main tags and releases the engine, and build the release notes.

CI's release job (.github/workflows/test.yml) calls this as a CLI; RELEASING.md step 4
describes it. Every decision lives here, so unit tests cover it. Stdlib only: the job runs it
without installing anything.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

# A final release: three canonical numbers, used with fullmatch. Anything else (.devN, rcN,
# .postN, +local, two or four parts, leading zeros) is not a release.
FINAL_RE = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")


class ReleaseError(Exception):
    """A push the job must not act on silently. The message names the remedy."""


@dataclass(frozen=True)
class Decision:
    version: str | None  # None when nothing is released
    tag: bool  # push a new tag
    release: bool  # a release is due for this version (existence is checked separately)


NOTHING = Decision(None, False, False)


def _key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def decide(before: str | None, after: str | None, tags: Mapping[str, str], head: str) -> Decision:
    """Decide from the push's project.version before and after, and the tags (name -> commit)."""
    if after is None:
        raise ReleaseError(
            f"pyproject.toml has no project.version at {head}; this workflow reads the version "
            "literal there (see #68). Tag and release by hand: RELEASING.md steps 4-5."
        )
    if after == before or not FINAL_RE.fullmatch(after):
        return NOTHING
    tag = "v" + after
    if tag in tags:
        if tags[tag] == head:
            return Decision(after, tag=False, release=True)
        raise ReleaseError(
            f"{tag} already tags {tags[tag][:12]}, not {head[:12]}; the workflow never moves a "
            f"tag. Check which commit should carry {tag} (RELEASING.md step 4)."
        )
    finals = [name[1:] for name in tags if name.startswith("v") and FINAL_RE.fullmatch(name[1:])]
    if finals:
        floor = max(finals, key=_key)
        if _key(after) < _key(floor):
            raise ReleaseError(
                f"version went down: {after} is below {floor} (tag v{floor}); fix the version "
                "in pyproject.toml."
            )
    if before is not None and FINAL_RE.fullmatch(before) and _key(after) < _key(before):
        raise ReleaseError(
            f"version went down: {after} is below {before} (the version before this push); fix "
            "the version in pyproject.toml."
        )
    return Decision(after, tag=True, release=True)
