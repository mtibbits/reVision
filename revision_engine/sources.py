"""Snapshot source files from the working tree and identify the commit being built."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from revision_engine.config import RepoConfig
from revision_engine.errors import BuildError


@dataclass(frozen=True)
class SourceFile:
    path: str
    text: str
    lines: tuple[str, ...]


def read_source(root: Path, rel: str) -> SourceFile:
    root = root.resolve()
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise BuildError(f"source path {rel!r} is outside the repository") from None
    if not target.is_file():
        raise BuildError(f"source file not found: {rel}")
    raw = target.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise BuildError(f"source file is not UTF-8: {rel} ({e})") from e
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    body = text[:-1] if text.endswith("\n") else text
    lines = tuple(body.split("\n")) if body else ()
    return SourceFile(path=rel.replace("\\", "/"), text=text, lines=lines)


def git_commit(root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return None
    if out.returncode != 0:
        return None
    sha = out.stdout.strip()
    return sha if len(sha) == 40 else None


def short(commit: str) -> str:
    return commit[:7]


def file_url(repo: RepoConfig, commit: str, rel: str) -> str:
    base = repo.url.rstrip("/")
    if repo.host == "gitlab":
        return f"{base}/-/blob/{commit}/{rel}"
    return f"{base}/blob/{commit}/{rel}"
