"""Decide whether a push to main tags and releases the engine, and build the release notes.

CI's release job (.github/workflows/test.yml) calls this as a CLI; RELEASING.md step 4
describes it. Every decision lives here, so unit tests cover it. Stdlib only: the job runs it
without installing anything.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
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


# Found with fullmatch on a line's strip(), so case and spacing do not matter.
NOTES_HEADING_RE = re.compile(r"##\s+release notes", re.IGNORECASE)
INSTALL_BLOCK = (
    "Install:\n\n```bash\n"
    'pip install "revision-engine @ git+https://github.com/mtibbits/reVision@v{version}"\n'
    "```\n"
)


def release_exists(releases: list[dict], version: str) -> bool:
    """Whether `gh release list --json tagName` lists the version's release. Drafts count."""
    return any(r["tagName"] == "v" + version for r in releases)


def release_pull(pulls: list[dict], sha: str) -> dict:
    """The one merged pull request into main among `commits/{sha}/pulls`."""
    merged = [p for p in pulls if p.get("merged_at") and p["base"]["ref"] == "main"]
    if not merged:
        raise ReleaseError(
            f"no merged pull request into main found for {sha[:12]}; create the release by "
            "hand: RELEASING.md step 5."
        )
    if len(merged) > 1:
        numbers = ", ".join(f"#{p['number']}" for p in merged)
        raise ReleaseError(
            f"several merged pull requests found for {sha[:12]}: {numbers}; create the release "
            "by hand: RELEASING.md step 5."
        )
    return merged[0]


def _fenced(lines: list[str]) -> list[bool]:
    """Which lines are code-fence lines or inside a fence (backticks or tildes, 3 or more)."""
    out = []
    fence = ""
    for line in lines:
        if fence:
            out.append(True)
            stripped = line.strip()
            if stripped.startswith(fence) and stripped == fence[0] * len(stripped):
                fence = ""
            continue
        m = re.match(r"(`{3,}|~{3,})", line.lstrip())
        if m:
            fence = m.group(1)
        out.append(bool(m))
    return out


def release_notes(body: str | None, version: str, number: int) -> str:
    """The `## Release notes` section of the PR description, followed by the install block.

    The section runs to the next `#` or `##` heading outside a code fence. The body is only
    ever data: CI writes the result to a file for `gh release create --notes-file`.
    """
    lines = (body or "").splitlines()
    fenced = _fenced(lines)
    start = next(
        (
            i + 1
            for i, line in enumerate(lines)
            if not fenced[i] and NOTES_HEADING_RE.fullmatch(line.strip())
        ),
        None,
    )
    section: list[str] = []
    if start is not None:
        for i in range(start, len(lines)):
            if not fenced[i] and lines[i].startswith(("# ", "## ")):
                break
            section.append(lines[i])
    while section and not section[0].strip():
        section.pop(0)
    while section and not section[-1].strip():
        section.pop()
    text = "\n".join(section)
    if not text:
        raise ReleaseError(
            f"PR #{number} has no '## Release notes' section; add one to its description and "
            "re-run this job, or create the release by hand: RELEASING.md step 5."
        )
    return text + "\n\n" + INSTALL_BLOCK.format(version=version)


def annotation(message: str) -> str:
    """A GitHub Actions error annotation, escaped so the whole message stays on one line."""
    escaped = message.strip().replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return "::error::" + escaped


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, encoding="utf-8")


def _version_at(sha: str) -> str | None:
    shown = _git("show", f"{sha}:pyproject.toml")
    if shown.returncode != 0:
        raise ReleaseError(
            f"cannot read pyproject.toml at {sha}: {shown.stderr.strip()}; is the commit "
            "fetched? Tag and release by hand: RELEASING.md steps 4-5."
        )
    return tomllib.loads(shown.stdout).get("project", {}).get("version")


def _commit(sha: str) -> str:
    """The full SHA, so it compares equal to the commits that tags point at."""
    return _git("rev-parse", "--verify", f"{sha}^{{commit}}").stdout.strip()


def _tags() -> dict[str, str]:
    """Tag name -> the commit it points at, with annotated tags peeled."""
    listed = _git(
        "for-each-ref", "refs/tags", "--format=%(refname:strip=2) %(objectname) %(*objectname)"
    )
    if listed.returncode != 0:
        raise ReleaseError(f"cannot list tags: {listed.stderr.strip()}")
    tags = {}
    for line in listed.stdout.splitlines():
        name, *objects = line.split()
        tags[name] = objects[-1]
    return tags


def _load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _flag(value: bool) -> str:
    return "true" if value else "false"


def _emit(outputs: dict[str, str]) -> None:
    lines = "".join(f"{key}={value}\n" for key, value in outputs.items())
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(lines)
    else:
        sys.stdout.write(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("decide", help="whether this push tags and releases (git only)")
    p.add_argument("--before", required=True)
    p.add_argument("--after", required=True)
    p = commands.add_parser("exists", help="whether the version's release exists")
    p.add_argument("--version", required=True)
    p.add_argument("--releases", required=True, help="output of gh release list --json tagName")
    p = commands.add_parser("notes", help="print the release notes from the release PR")
    p.add_argument("--version", required=True)
    p.add_argument("--sha", required=True)
    p.add_argument("--pulls", required=True, help="output of gh api commits/{sha}/pulls")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    try:
        if args.command == "decide":
            before, after = _version_at(args.before), _version_at(args.after)
            d = decide(before, after, _tags(), _commit(args.after))
            _emit({"version": d.version or "", "tag": _flag(d.tag), "release": _flag(d.release)})
        elif args.command == "exists":
            _emit({"exists": _flag(release_exists(_load(args.releases), args.version))})
        else:
            pull = release_pull(_load(args.pulls), args.sha)
            sys.stdout.write(release_notes(pull["body"], args.version, pull["number"]))
    except ReleaseError as e:
        print(annotation(str(e)), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
