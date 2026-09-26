import hashlib
import shutil
from pathlib import Path

from revision_engine.build import build

FIXED = "0123456789abcdef0123456789abcdef01234567"


def tree_hashes(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_two_builds_are_byte_identical(minimal_example, tmp_path):
    src = tmp_path / "m"
    shutil.copytree(minimal_example, src)
    build(src, output=tmp_path / "a", commit=FIXED)
    build(src, output=tmp_path / "b", commit=FIXED)
    assert tree_hashes(tmp_path / "a") == tree_hashes(tmp_path / "b")
