import subprocess

import pytest

from revision_engine.config import RepoConfig
from revision_engine.errors import BuildError
from revision_engine.sources import file_url, git_commit, read_source, short


def test_reads_file_and_splits_lines(repo):
    repo.write("src/a.c", "int x;\nint y;\n")
    s = read_source(repo, "src/a.c")
    assert s.path == "src/a.c"
    assert s.lines == ("int x;", "int y;")


def test_crlf_and_missing_trailing_newline_normalized(repo):
    (repo / "src").mkdir()
    (repo / "src" / "b.c").write_bytes(b"int x;\r\nint y;")
    s = read_source(repo, "src/b.c")
    assert s.text == "int x;\nint y;"
    assert s.lines == ("int x;", "int y;")


def test_missing_file_is_build_error(repo):
    with pytest.raises(BuildError, match="source file not found: src/nope.c"):
        read_source(repo, "src/nope.c")


def test_path_outside_root_rejected(repo):
    with pytest.raises(BuildError, match="outside the repository"):
        read_source(repo, "../etc/passwd")


def test_git_commit_none_when_not_a_repo(tmp_path):
    assert git_commit(tmp_path) is None


def test_git_commit_reads_head(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "f").write_text("x")
    subprocess.run(["git", "add", "f"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "m"], cwd=tmp_path, check=True
    )
    c = git_commit(tmp_path)
    assert c is not None and len(c) == 40


def test_file_url_github_and_gitlab():
    c = "a" * 40
    assert file_url(RepoConfig("https://github.com/x/y", "github"), c, "k/f.h") == f"https://github.com/x/y/blob/{c}/k/f.h"
    assert file_url(RepoConfig("https://gl/x/y/", "gitlab"), c, "k/f.h") == f"https://gl/x/y/-/blob/{c}/k/f.h"
    assert short(c) == "aaaaaaa"
