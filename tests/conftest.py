from __future__ import annotations

from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def minimal_example() -> Path:
    return EXAMPLES / "minimal"


class RepoPath(type(Path())):
    """A Path that can also write files relative to itself. Python 3.12+ allows subclassing."""

    def write(self, rel: str, text: str) -> Path:
        p = self / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        return p


@pytest.fixture
def repo(tmp_path: Path) -> RepoPath:
    """Build a throwaway content repository with a valid revision.yaml and an empty curriculum."""
    r = RepoPath(tmp_path)
    r.write(
        "revision.yaml",
        "site:\n  title: T\n  base_url: ''\nrepo:\n  url: https://github.com/x/y\n  host: github\n"
        "content: docs/revision\noutput: public\nnarration:\n  voice: en_US-lessac-medium\n",
    )
    r.write("docs/revision/curriculum.yaml", "chapters: []\n")
    return r
